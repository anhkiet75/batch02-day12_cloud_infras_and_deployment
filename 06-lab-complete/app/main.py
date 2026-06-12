"""
VinBank Production Agent — Final project Day-12.

Agent gốc: VinBank customer-service assistant + guardrails (Day-11),
được productionize đầy đủ:
  ✅ Config 12-factor (environment variables)
  ✅ Structured JSON logging
  ✅ API Key authentication
  ✅ Rate limiting (per user)
  ✅ Cost guard (monthly budget per user)
  ✅ Input/output guardrails (injection, off-topic, secret redaction)
  ✅ Health check + Readiness probe
  ✅ Graceful shutdown (SIGTERM)
  ✅ Stateless design (conversation history trong store Redis/memory)
"""
import json
import logging
import signal
import time
from datetime import datetime, timezone

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .agent import answer as agent_answer
from .auth import verify_api_key
from .config import settings
from .cost_guard import check_budget
from .rate_limiter import check_rate_limit
from .store import backend, store

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":%(message)s}',
)
logger = logging.getLogger(__name__)


def log_event(**fields) -> None:
    """JSON structured log — 1 dòng/sự kiện, dễ ingest vào log aggregator."""
    logger.info(json.dumps(fields, ensure_ascii=False))


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)

START_TIME = time.time()
_is_ready = False
_in_flight = 0
_request_count = 0


# ── Lifecycle ───────────────────────────────────────────
@app.on_event("startup")
def on_startup() -> None:
    global _is_ready
    store.ping()
    _is_ready = True
    log_event(event="startup", store=backend,
              llm="gemini" if settings.google_api_key else "mock",
              env=settings.environment)


@app.on_event("shutdown")
def on_shutdown() -> None:
    global _is_ready
    _is_ready = False
    log_event(event="shutdown")


# ── Middleware: in-flight tracking + security headers + access log ──
@app.middleware("http")
async def observe(request: Request, call_next):
    global _in_flight, _request_count
    _in_flight += 1
    _request_count += 1
    started = time.time()
    try:
        response: Response = await call_next(request)
    finally:
        _in_flight -= 1
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    log_event(event="request", method=request.method, path=request.url.path,
              status=response.status_code,
              ms=round((time.time() - started) * 1000, 1))
    return response


# ── Models ──────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


class AskResponse(BaseModel):
    answer: str
    status: str
    user_id: str
    history_length: int
    model: str
    timestamp: str


# ── Endpoints ───────────────────────────────────────────
@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {"ask": "POST /ask (X-API-Key)", "health": "GET /health",
                      "ready": "GET /ready"},
    }


@app.get("/health", tags=["Operations"])
def health():
    """Liveness probe — container còn sống không."""
    return {
        "status": "ok",
        "version": settings.app_version,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    """Readiness probe — sẵn sàng nhận traffic không (store phải ping được)."""
    if not _is_ready:
        raise HTTPException(status_code=503, detail="Agent not ready")
    try:
        store.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Store unavailable") from exc
    return {"ready": True, "store": backend, "in_flight_requests": _in_flight}


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
def ask(
    body: AskRequest,
    user_id: str = Depends(verify_api_key),
    _rate_limit: None = Depends(check_rate_limit),
    _budget: None = Depends(check_budget),
):
    """Hỏi VinBank agent. Yêu cầu header `X-API-Key`. Stateless: history lưu ở store."""
    if not _is_ready:
        raise HTTPException(status_code=503, detail="Agent not ready")

    history_key = f"history:{user_id}"
    history = store.lrange(history_key, 0, -1)

    reply, status = agent_answer(body.question, history)

    store.rpush(history_key, f"user: {body.question}")
    store.rpush(history_key, f"assistant: {reply}")
    store.expire(history_key, 3600)

    log_event(event="agent_call", user=user_id, status=status,
              q_len=len(body.question))

    return AskResponse(
        answer=reply,
        status=status,
        user_id=user_id,
        history_length=len(history) + 2,
        model=settings.gemini_model if settings.google_api_key else "mock",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/ask/stream", tags=["Agent"])
def ask_stream(
    body: AskRequest,
    user_id: str = Depends(verify_api_key),
    _rate_limit: None = Depends(check_rate_limit),
    _budget: None = Depends(check_budget),
):
    """Như /ask nhưng trả lời theo kiểu streaming (chunked text/plain) cho UI chat.

    Câu trả lời được tính trọn vẹn (đi qua output guardrail) rồi mới stream từng từ
    -> giữ nguyên tính an toàn của guardrail, đồng thời cho trải nghiệm gõ dần.
    """
    if not _is_ready:
        raise HTTPException(status_code=503, detail="Agent not ready")

    history_key = f"history:{user_id}"
    history = store.lrange(history_key, 0, -1)
    reply, status = agent_answer(body.question, history)

    store.rpush(history_key, f"user: {body.question}")
    store.rpush(history_key, f"assistant: {reply}")
    store.expire(history_key, 3600)

    log_event(event="agent_call_stream", user=user_id, status=status,
              q_len=len(body.question))

    def token_generator():
        for word in reply.split(" "):
            yield word + " "
            time.sleep(0.04)

    return StreamingResponse(
        token_generator(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Agent-Status": status},
    )


# ── Graceful shutdown (SIGTERM từ orchestrator) ─────────
def shutdown_handler(signum, _frame) -> None:
    global _is_ready
    _is_ready = False
    log_event(event="signal", signal=signum, in_flight_requests=_in_flight)


signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
