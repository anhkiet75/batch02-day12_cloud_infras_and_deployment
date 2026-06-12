"""
Long Châu Triage Agent — Final project Day-12.

Agent gốc: **Long Châu AI Triage Middleware** (nhóm Day-06, LLM thật qua OpenRouter),
được productionize đầy đủ:
  ✅ Config 12-factor (environment variables)
  ✅ Structured JSON logging
  ✅ API Key authentication
  ✅ Rate limiting (per user)
  ✅ Cost guard (monthly budget per user)
  ✅ Safety gate + triage (crisis / high-risk / out-of-scope)
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

from .auth import verify_api_key
from .config import settings
from .cost_guard import check_budget
from .rate_limiter import check_rate_limit
from .store import backend, store
from .triage import triage

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":%(message)s}',
)
logger = logging.getLogger(__name__)

HISTORY_TURNS = 8   # số message gần nhất giữ lại làm context


def log_event(**fields) -> None:
    """JSON structured log — 1 dòng/sự kiện, dễ ingest vào log aggregator."""
    logger.info(json.dumps(fields, ensure_ascii=False))


def _llm_mode() -> str:
    return "openai" if settings.openai_api_key else "stub"


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
    log_event(event="startup", store=backend, llm=_llm_mode(),
              model=settings.llm_model, env=settings.environment)


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
    route: str
    safety_gate_triggered: bool
    handoff_summary: str | None = None
    products: list[dict] = []
    user_id: str
    history_length: int
    model: str
    timestamp: str


# ── Conversation history (stateless qua store) ──────────
def _load_history(user_id: str) -> list[dict]:
    raw = store.lrange(f"history:{user_id}", -HISTORY_TURNS, -1)
    history = []
    for item in raw:
        try:
            history.append(json.loads(item))
        except (json.JSONDecodeError, TypeError):
            continue
    return history


def _save_turn(user_id: str, question: str, reply: str) -> None:
    key = f"history:{user_id}"
    store.rpush(key, json.dumps({"role": "user", "content": question}, ensure_ascii=False))
    store.rpush(key, json.dumps({"role": "assistant", "content": reply}, ensure_ascii=False))
    store.expire(key, 3600)


async def _run_triage(user_id: str, question: str) -> dict:
    """Chạy triage + lưu history. Trả về dict kết quả."""
    if not _is_ready:
        raise HTTPException(status_code=503, detail="Agent not ready")
    history = _load_history(user_id)
    result = await triage(question, history)
    _save_turn(user_id, question, result.get("reply", ""))
    log_event(event="agent_call", user=user_id, route=result.get("route"),
              safety=result.get("safety_gate_triggered"), q_len=len(question))
    return result


# ── Endpoints ───────────────────────────────────────────
@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {"ask": "POST /ask (X-API-Key)", "stream": "POST /ask/stream",
                      "health": "GET /health", "ready": "GET /ready"},
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
    return {"ready": True, "store": backend, "llm": _llm_mode(),
            "in_flight_requests": _in_flight}


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask(
    body: AskRequest,
    user_id: str = Depends(verify_api_key),
    _rate_limit: None = Depends(check_rate_limit),
    _budget: None = Depends(check_budget),
):
    """Hỏi Long Châu triage agent. Header `X-API-Key`. Stateless: history lưu ở store."""
    result = await _run_triage(user_id, body.question)
    return AskResponse(
        answer=result.get("reply_md") or result.get("reply", ""),
        route=result.get("route", "unknown"),
        safety_gate_triggered=result.get("safety_gate_triggered", False),
        handoff_summary=result.get("handoff_summary"),
        products=result.get("products") or [],
        user_id=user_id,
        history_length=len(_load_history(user_id)),
        model=result.get("model", _llm_mode()),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/ask/stream", tags=["Agent"])
async def ask_stream(
    body: AskRequest,
    user_id: str = Depends(verify_api_key),
    _rate_limit: None = Depends(check_rate_limit),
    _budget: None = Depends(check_budget),
):
    """Như /ask nhưng stream câu trả lời (chunked text/plain) cho UI chat.

    Triage tính trọn kết quả (qua safety gate) rồi mới stream từng từ -> giữ an toàn,
    đồng thời cho trải nghiệm gõ dần. Route trả qua header `X-Agent-Route`.
    """
    result = await _run_triage(user_id, body.question)
    reply = result.get("reply_md") or result.get("reply", "")

    def token_generator():
        for word in reply.split(" "):
            yield word + " "
            time.sleep(0.03)

    return StreamingResponse(
        token_generator(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Agent-Route": result.get("route", "unknown")},
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
