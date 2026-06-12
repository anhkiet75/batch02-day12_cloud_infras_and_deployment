# Deployment Information — Long Châu AI Triage Agent

## Public URLs (Render)
| Service | URL |
|---------|-----|
| **Chatbot UI (Streamlit)** | **https://longchau-chatbot-ui-h597.onrender.com** |
| **API (FastAPI)** | **https://longchau-triage-api-h597.onrender.com** |

> Mở **UI URL** để chat ngay (API URL + API key đã cấu hình sẵn trong UI).
> Render free: service **ngủ sau ~15 phút** không dùng → request đầu **cold-start ~30–60s**.

## Platform
**Render** — 2 web service Docker (API + UI), build từ `06-lab-complete/` và `06-lab-complete/ui/`.
LLM thật: **OpenAI `gpt-4o-mini`**. 1 service API → **in-memory store** (thêm Render Key Value + `REDIS_URL` để stateless đa-instance).

## Test Commands
```bash
API=https://longchau-triage-api-h597.onrender.com
KEY=<AGENT_API_KEY>    # giá trị đã set trong Render → service API → Environment
```

### Health / Readiness
```bash
curl $API/health       # {"status":"ok",...}
curl $API/ready        # {"ready":true,"store":"memory","llm":"openai",...}
```

### Auth bắt buộc (thiếu key → 401)
```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST $API/ask \
  -H "Content-Type: application/json" -d '{"question":"hi"}'   # 401
```

### Factual — AI thật + gợi ý sản phẩm
```bash
curl -X POST $API/ask -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"question":"Thuốc Efferalgan là gì?"}'
# route=factual, answer (OpenAI) + products[] (search Long Châu thật)
```

### High-risk → chuyển dược sĩ (safety gate)
```bash
curl -X POST $API/ask -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"question":"Tôi bị suy thận, uống paracetamol liều cao được không?"}'
# route=advisory_handoff, safety_gate_triggered=true, handoff_summary (AI tóm tắt)
```

### Out-of-scope / Crisis
```bash
curl -X POST $API/ask -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"question":"Viết giúp tôi code python"}'      # route=out_of_scope
curl -X POST $API/ask -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"question":"tôi muốn uống thuốc để chết"}'    # route=crisis + hotline
```

### Streaming (cho UI chat)
```bash
curl -N -X POST $API/ask/stream -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"question":"Vitamin C có công dụng gì?"}'
# Trả lời gõ dần; header X-Agent-Route = factual | advisory_handoff | ...
```

### Rate limiting (10 req/min → 429)
```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code} " -X POST $API/ask \
    -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d "{\"question\":\"paracetamol $i\"}"; done; echo
```

## Environment Variables (Render — service API)
| Key | Value |
|-----|-------|
| `AGENT_API_KEY` | (secret — chia sẻ cho UI) |
| `OPENAI_API_KEY` | (secret) — LLM thật |
| `LLM_MODEL` | gpt-4o-mini |
| `ENVIRONMENT` | production |
| `RATE_LIMIT_PER_MINUTE` | 10 |
| `MONTHLY_BUDGET_USD` | 10.0 |
| `REDIS_URL` | (chưa set → in-memory store) |

Service UI: `AGENT_API_URL` = URL API, `AGENT_API_KEY` = cùng key.

## Cách deploy (Render)
New → Web Service → chọn repo → **Runtime: Docker**, **Root Directory:** `06-lab-complete`
(API) / `06-lab-complete/ui` (UI) → set env vars → Create. Cấu hình mẫu: `06-lab-complete/render.yaml`.

## Verified results (live)
| Check | Kết quả |
|-------|---------|
| `GET /health` `/ready` | 200, `llm:"openai"` ✅ |
| `POST /ask` không key | 401 ✅ |
| UI Streamlit | 200 ✅ |
| Factual (OpenAI) + products | có product links thật ✅ |
| High-risk → handoff | `safety_gate_triggered=true` ✅ |
| Out-of-scope / Crisis | route đúng ✅ |
| Streaming `/ask/stream` | gõ dần + `X-Agent-Route` ✅ |
| Rate limit | 429 sau 10 req/phút ✅ |
| Docker image | ~272 MB (< 500 MB) ✅ |
| `check_production_ready.py` | 20/20 ✅ |

> Lưu ý: URL Railway cũ (`vinbank-production-agent-production...`) có thể tắt — bản chính thức nay chạy trên Render.
