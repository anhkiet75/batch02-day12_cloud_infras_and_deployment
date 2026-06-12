# Final Project — Long Châu AI Triage Agent

Productionize agent **Long Châu AI Triage Middleware** (sản phẩm nhóm Day-06, dùng
**LLM thật qua OpenAI**) theo toàn bộ concept Day-12: Docker → Cloud → Security → Scaling.

## Agent làm gì
Trợ lý nhà thuốc Long Châu phân loại (triage) câu hỏi của khách rồi xử lý phù hợp:
- **factual** → AI trả lời thông tin chung về thuốc + gợi ý sản phẩm (search Long Châu).
- **advisory_gather** → AI hỏi thêm để đủ ngữ cảnh tư vấn.
- **advisory_handoff** → tóm tắt hội thoại, chuyển **dược sĩ** người thật.
- **out_of_scope** → từ chối câu hỏi ngoài dược phẩm / nguy hiểm.
- **crisis** → phát hiện ý định tự hại → chặn cứng, đưa hotline.

**Safety gate** (rule-based) chạy TRƯỚC AI: crisis + high-risk (bệnh nền, tương tác thuốc,
thai kỳ...) ép sang dược sĩ. **LLM** gọi OpenAI khi có `OPENAI_API_KEY`; không có key thì
chạy **stub heuristic** (safety gate vẫn hoạt động).

## Production checklist
- [x] Config 12-factor từ environment (`app/config.py`)
- [x] Multi-stage Dockerfile, non-root, **~272 MB** (< 500 MB)
- [x] API key auth (`app/auth.py`) — thiếu/sai key → 401
- [x] Rate limiting fixed-window (`app/rate_limiter.py`) — 10 req/min → 429
- [x] Cost guard theo tháng (`app/cost_guard.py`) — vượt budget → 402
- [x] `GET /health` (liveness) + `GET /ready` (readiness, check store)
- [x] Graceful shutdown (SIGTERM)
- [x] Stateless: history trong store Redis/in-memory (`app/store.py`)
- [x] Structured JSON logging
- [x] Streaming `POST /ask/stream` + Streamlit UI (`ui/`)
- [x] Deploy config: `railway.toml`, `render.yaml`

## Endpoints
| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness (check store + llm mode) |
| POST | `/ask` | Triage 1 lần (JSON: answer, route, handoff_summary, products) |
| POST | `/ask/stream` | Triage + **streaming** chunked text (header `X-Agent-Route`) |

## Cấu trúc
```
06-lab-complete/
├── app/
│   ├── main.py          # FastAPI: endpoints (+/ask/stream) + lifecycle
│   ├── config.py        # 12-factor settings (OpenAI + auth + rate + cost)
│   ├── triage.py        # Orchestrator: crisis -> safety gate -> classify -> route
│   ├── safety_gate.py   # Rule-based: crisis / high-risk / injection
│   ├── prompts.py       # System prompts (classifier, factual, gather, handoff)
│   ├── llm_client.py    # OpenAI Chat Completions (provider-agnostic base URL)
│   ├── longchau_search.py # Tìm sản phẩm trên nhathuoclongchau.com.vn
│   ├── auth.py          # API key -> user_id
│   ├── rate_limiter.py  # Fixed-window rate limit
│   ├── cost_guard.py    # Monthly budget guard
│   └── store.py         # Redis hoặc in-memory (cùng interface)
├── ui/                  # Streamlit chat UI (image riêng)
├── Dockerfile           # Multi-stage (API)
├── docker-compose.yml   # nginx + agent(scale) + redis + ui
├── nginx.conf / railway.toml / render.yaml
├── requirements.txt / .env.example / .dockerignore
└── check_production_ready.py
```

## Chạy local
```bash
cp .env.example .env.local      # set AGENT_API_KEY (+ OPENAI_API_KEY nếu muốn AI thật)
docker compose up --scale agent=3   # nginx LB + 3 agent + redis + ui(8501)

curl http://localhost/health
curl http://localhost/ask -X POST \
  -H "X-API-Key: <key>" -H "Content-Type: application/json" \
  -d '{"question": "Paracetamol có công dụng gì?"}'
```

Single container (không Redis — in-memory store):
```bash
docker build -t longchau-agent:prod .
docker run -p 8000:8000 -e AGENT_API_KEY=secret -e OPENAI_API_KEY=sk-... longchau-agent:prod
```

## Giao diện Streamlit (chat + streaming)
```bash
cd ui && pip install -r requirements.txt
export AGENT_API_URL=https://vinbank-production-agent-production.up.railway.app
streamlit run streamlit_app.py     # http://localhost:8501
```
Nhập **API Key** ở sidebar → chat. Badge route (factual/advisory/handoff/crisis) hiện dưới mỗi câu trả lời.

## Kiểm tra production-ready
```bash
python check_production_ready.py    # -> 20/20 (100%)
```

Public URL deploy thực tế: xem [`../DEPLOYMENT.md`](../DEPLOYMENT.md).
