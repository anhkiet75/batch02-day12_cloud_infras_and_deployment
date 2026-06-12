# Deployment Information — Long Châu AI Triage Agent

## Public URL
**https://vinbank-production-agent-production.up.railway.app**

> Tên service Railway giữ nguyên từ lần deploy trước; nội dung hiện tại là **Long Châu
> Triage Agent** dùng **OpenAI gpt-4o-mini** (LLM thật).

## Platform
**Railway** (Docker build từ `06-lab-complete/Dockerfile` + `railway.toml`).
1 service → dùng **in-memory store**. Thêm Railway Redis + `REDIS_URL` để stateless đa-instance.

## Test Commands
```bash
URL=https://vinbank-production-agent-production.up.railway.app
KEY=<AGENT_API_KEY>   # xem Railway → Variables
```

### Health / Readiness
```bash
curl $URL/health
# {"status":"ok",...}
curl $URL/ready
# {"ready":true,"store":"memory","llm":"openai",...}
```

### Auth bắt buộc (thiếu key → 401)
```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST $URL/ask \
  -H "Content-Type: application/json" -d '{"question":"hi"}'   # 401
```

### Factual — AI thật + gợi ý sản phẩm
```bash
curl -X POST $URL/ask -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"question":"Thuốc Efferalgan là gì?"}'
# route=factual, answer (OpenAI) + products[] (search Long Châu thật)
```

### High-risk → chuyển dược sĩ (safety gate)
```bash
curl -X POST $URL/ask -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"question":"Tôi bị suy thận, uống paracetamol liều cao được không?"}'
# route=advisory_handoff, safety_gate_triggered=true, handoff_summary (AI tóm tắt)
```

### Out-of-scope / Crisis
```bash
curl -X POST $URL/ask -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"question":"Viết giúp tôi code python"}'      # route=out_of_scope
curl -X POST $URL/ask -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"question":"tôi muốn uống thuốc để chết"}'    # route=crisis + hotline
```

### Streaming (cho UI chat)
```bash
curl -N -X POST $URL/ask/stream -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"question":"Vitamin C có công dụng gì?"}'
# Trả lời gõ dần; header X-Agent-Route = factual | advisory_handoff | ...
```

### Rate limiting (10 req/min → 429)
```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code} " -X POST $URL/ask \
    -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d "{\"question\":\"paracetamol $i\"}"; done; echo
```

Giao diện **Streamlit** (chat + streaming): `06-lab-complete/ui/` →
`AGENT_API_URL=$URL streamlit run ui/streamlit_app.py`.

## Environment Variables (Railway)
| Key | Value |
|-----|-------|
| `AGENT_API_KEY` | (secret) |
| `OPENAI_API_KEY` | (secret) — LLM thật |
| `LLM_MODEL` | gpt-4o-mini |
| `PORT` | 8000 |
| `ENVIRONMENT` | production |
| `RATE_LIMIT_PER_MINUTE` | 10 |
| `MONTHLY_BUDGET_USD` | 10.0 |
| `REDIS_URL` | (chưa set → in-memory store) |

## Verified results (live)
| Check | Kết quả |
|-------|---------|
| `GET /health` `/ready` | 200, `llm:"openai"` ✅ |
| `POST /ask` không key | 401 ✅ |
| Factual (OpenAI) + products | 200, có product links thật ✅ |
| High-risk → handoff | `safety_gate_triggered=true` ✅ |
| Out-of-scope / Crisis | route đúng ✅ |
| Streaming `/ask/stream` | gõ dần + `X-Agent-Route` ✅ |
| Rate limit | 429 sau 10 req/phút ✅ |
| Docker image | ~272 MB (< 500 MB) ✅ |
| `check_production_ready.py` | 20/20 ✅ |
