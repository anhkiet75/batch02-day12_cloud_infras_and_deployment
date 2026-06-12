# Final Project — VinBank Production Agent

Productionize agent **VinBank customer-service + Guardrails** (port từ Day-11) theo
toàn bộ concept Day-12: Docker → Cloud → Security → Scaling.

## Agent làm gì
Trợ lý ngân hàng VinBank trả lời câu hỏi về tài khoản, lãi suất, chuyển tiền, thẻ, vay.
Có **guardrails** thật:
- **Input guard:** chặn prompt-injection, chủ đề bị cấm, câu hỏi ngoài lĩnh vực banking → trả lời từ chối an toàn.
- **Output guard:** redact secret/PII (API key, mật khẩu, internal hostname, số thẻ) nếu lỡ lọt ra.
- **LLM:** gọi **Gemini** khi có `GOOGLE_API_KEY`; không có key thì chạy **mock deterministic** (guardrails vẫn hoạt động).

## Production checklist
- [x] Config 12-factor từ environment (`app/config.py`)
- [x] Multi-stage Dockerfile, non-root, **304 MB** (< 500 MB)
- [x] API key auth (`app/auth.py`) — thiếu/sai key → 401
- [x] Rate limiting fixed-window (`app/rate_limiter.py`) — 10 req/min → 429
- [x] Cost guard theo tháng (`app/cost_guard.py`) — vượt budget → 402
- [x] `GET /health` (liveness) + `GET /ready` (readiness, check store)
- [x] Graceful shutdown (SIGTERM)
- [x] Stateless: history trong store Redis/in-memory (`app/store.py`)
- [x] Structured JSON logging
- [x] Deploy config: `railway.toml`, `render.yaml`

## Cấu trúc
```
06-lab-complete/
├── app/
│   ├── main.py         # FastAPI: endpoints + lifecycle + middleware
│   ├── config.py       # 12-factor settings + banking topics
│   ├── agent.py        # Brain: guardrails -> Gemini/mock -> redact
│   ├── guardrails.py   # Input/output guardrails (port Day-11)
│   ├── auth.py         # API key -> user_id
│   ├── rate_limiter.py # Fixed-window rate limit
│   ├── cost_guard.py   # Monthly budget guard
│   └── store.py        # Redis hoặc in-memory (cùng interface)
├── Dockerfile          # Multi-stage
├── docker-compose.yml  # nginx + agent(scale) + redis
├── nginx.conf          # Load balancer
├── railway.toml / render.yaml
├── requirements.txt / .env.example / .dockerignore
└── check_production_ready.py
```

## Chạy local
```bash
cp .env.example .env.local      # set AGENT_API_KEY (và GOOGLE_API_KEY nếu muốn LLM thật)
docker compose up --scale agent=3   # nginx LB + 3 agent + redis

curl http://localhost/health
curl http://localhost/ask -X POST \
  -H "X-API-Key: <key>" -H "Content-Type: application/json" \
  -d '{"question": "Lãi suất tiết kiệm VinBank?"}'
```

Single container (không Redis — dùng in-memory store):
```bash
docker build -t vinbank-agent:prod .
docker run -p 8000:8000 -e AGENT_API_KEY=secret vinbank-agent:prod
```

## Kiểm tra production-ready
```bash
python check_production_ready.py    # -> 20/20 (100%)
```

Public URL deploy thực tế: xem [`../DEPLOYMENT.md`](../DEPLOYMENT.md).
