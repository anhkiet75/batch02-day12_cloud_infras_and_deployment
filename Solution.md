# Day 12 Lab — Solution (Đáp án Codelab Part 1 → 5)

> Agent dùng cho Final Project (Part 6): **Long Châu AI Triage Agent** — port từ
> sản phẩm nhóm Day-06 (LLM thật qua OpenAI), productionize đầy đủ trong `06-lab-complete/`.

---

## Part 1 — Localhost vs Production

### Exercise 1.1 — Anti-patterns trong `01-localhost-vs-production/develop/app.py`
1. **Hardcode API key** trong code (`OPENAI_API_KEY = "sk-..."`) → push GitHub là lộ.
2. **Hardcode DATABASE_URL kèm credentials** (`admin:password123@...`).
3. **Không có config management** — `DEBUG`, `MAX_TOKENS` cứng trong code, không đọc từ env.
4. **Dùng `print()` thay vì logging** chuẩn.
5. **Log ra cả secret** (`print(f"Using key: {OPENAI_API_KEY}")`).
6. **Không có `/health` endpoint** → platform không biết khi nào cần restart.
7. **Host = `localhost`** (chỉ truy cập nội bộ) thay vì `0.0.0.0`.
8. **Port cứng = 8000**, không đọc `$PORT` do platform inject.
9. **`reload=True` + `DEBUG=True`** — chỉ hợp dev, rủi ro/chậm ở production.
10. **Không có graceful shutdown** — request đang chạy bị cắt đột ngột.

### Exercise 1.3 — So sánh Develop vs Production
| Feature | Develop | Production | Tại sao quan trọng? |
|---------|---------|------------|---------------------|
| Config | Hardcode | Environment variables (12-factor) | Tách config khỏi code → an toàn, đổi môi trường không sửa code |
| Health check | Không có | `GET /health` + `GET /ready` | Platform/LB biết khi nào restart & khi nào route traffic |
| Logging | `print()` | Structured JSON logging | Máy đọc được, ingest vào log aggregator để debug/alert |
| Shutdown | Đột ngột | Graceful (SIGTERM) | Cho request đang xử lý hoàn tất trước khi container chết |
| Host/Port | `localhost:8000` cứng | `0.0.0.0:$PORT` | Container/cloud bind đúng interface và port được cấp |

---

## Part 2 — Docker

### Exercise 2.1 — Dockerfile questions
1. **Base image:** develop dùng `python:3.11`, production dùng `python:3.11-slim`.
2. **Working directory:** `/app` ở runtime, builder có thể dùng stage riêng.
3. **COPY `requirements.txt` trước code:** để tận dụng Docker layer cache, chỉ cài lại dependencies khi file requirements đổi.
4. **CMD vs ENTRYPOINT:** `CMD` là lệnh mặc định, có thể override; `ENTRYPOINT` là executable chính, args truyền thêm sẽ nối phía sau.

### Exercise 2.3 — Multi-stage build & image size
- **Stage 1 (builder):** có pip + build tools, cài dependencies vào `~/.local`.
- **Stage 2 (runtime):** image slim sạch, **chỉ copy site-packages + source** từ builder
  → không mang theo build tools → image nhỏ và bề mặt tấn công ít hơn.

**Số đo thực tế:**
| Image | Kiểu build | Size |
|-------|-----------|------|
| `myagent-develop` | single-stage `python:3.11` | **1.67 GB** |
| `mygent-advanced` | multi-stage `python:3.11-slim` | **262MB** |

→ Multi-stage giảm **~84%** dung lượng và đạt yêu cầu **< 500 MB**.

### Exercise 2.4 — Docker Compose stack
3 service: **nginx** (load balancer, cổng vào 80) → **agent** (n instance, scale được) →
**redis** (state dùng chung). nginx `upstream` tới `agent:8000`; agent đọc `REDIS_URL`
để lưu history/rate/budget → nhiều instance share chung state.

---

## Part 3 — Cloud Deployment

### Exercise 3.2 — `railway.toml` vs `render.yaml`
| | `railway.toml` | `render.yaml` |
|--|----------------|----------------|
| Phạm vi | Cấu hình build/deploy **1 app** | **Blueprint** mô tả nhiều service/hạ tầng |
| Builder | `builder = "DOCKERFILE"` | `runtime: docker` + `dockerfilePath` |
| Env vars | Set qua CLI/dashboard | Khai báo `envVars` ngay trong file (`sync:false`, `generateValue`) |
| Health check | `healthcheckPath` | `healthCheckPath` |
| Thêm dịch vụ (Redis…) | Tách riêng | Có thể khai báo chung blueprint |

Điểm chung: cả hai đều trỏ health check `/health`, có restart policy, deploy từ Docker.

### Exercise 3.1 — Deploy
```bash
curl https://keen-surprise-production-b717.up.railway.app/health
```

Response:

```json
{"status":"ok","uptime_seconds":3493.9,"platform":"Railway","timestamp":"2026-06-12T11:05:53.455111+00:00"}
```

Test agent endpoint:

```bash
curl https://keen-surprise-production-b717.up.railway.app/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question":"tes"}'
```

Response hợp lệ:

```json
{"question":"tes","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","platform":"Railway"}
```

### Exercise 3.2 — Compare `railway.toml` vs `render.yaml`
| Tiêu chí | `railway.toml` | `render.yaml` |
|---------|-----------------|---------------|
| Phạm vi | Cấu hình 1 app/service | Blueprint có thể mô tả nhiều services |
| Docker config | `builder = "DOCKERFILE"` | `runtime: docker` + `dockerfilePath` |
| Env vars | Set chủ yếu qua dashboard / CLI | Có thể khai báo trong `envVars` |
| Health check | `healthcheckPath` | `healthCheckPath` |
| Multi-service | Thường cấu hình tách rời | Có thể mô tả chung API + worker + redis |

Điểm chung:
- đều deploy từ Docker
- đều hỗ trợ health check
- đều phù hợp cho app FastAPI containerized

### Exercise 3.3 — Optional: GCP Cloud Run CI/CD
Trong repo có `03-cloud-deployment/production-cloud-run/cloudbuild.yaml` và `service.yaml`.

Ý chính:
- **Cloud Build** build image từ source
- push image lên registry
- **Cloud Run** deploy image serverless
- scale tự động theo traffic
- phù hợp khi muốn CI/CD chuẩn GCP

---

## Part 4 — API Security

### Exercise 4.1 — API key authentication
Trong `04-api-gateway/develop/app.py`:
- API key được check ở dependency `verify_api_key`
- client gửi key qua header `X-API-Key`
- thiếu hoặc sai key -> trả **401**
- rotate key bằng cách đổi giá trị key trong environment/config rồi restart hoặc redeploy

### Exercise 4.2 — JWT authentication
Trong `04-api-gateway/production/auth.py` và `app.py`:

Flow:
1. Gọi `POST /auth/token` với `username` và `password`
2. Server tạo JWT chứa `sub`, `role`, `iat`, `exp`
3. Client gọi `POST /ask` với header `Authorization: Bearer <token>`
4. Dependency `verify_token` decode và verify chữ ký + expiry
5. Token hết hạn -> **401**, token sai -> **403**

Ví dụ:

```bash
curl http://localhost:8000/auth/token -X POST \
  -H "Content-Type: application/json" \
  -d '{"username":"student","password":"demo123"}'
```

Sau đó dùng token:

```bash
curl http://localhost:8000/ask -X POST \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"question":"Explain JWT"}'
```

### Exercise 4.3 — Rate limiting
Trong lab advanced security:
- dùng **sliding window** rate limiting theo role/user
- user thường bị limit thấp hơn admin
- khi vượt ngưỡng -> trả **429**
- admin có limit cao hơn nên thực tế là cách “bypass” hợp lệ trong bài lab

### Exercise 4.4 — Cost guard
Cost guard theo dõi chi phí usage và dừng khi vượt ngân sách:
- check budget trước khi gọi model
- record usage sau khi xử lý request
- nếu vượt budget -> chặn request tiếp theo

Trong Final Project `06-lab-complete/app/cost_guard.py`:
- mỗi request cộng chi phí ước tính vào key tháng `budget:{user_id}:{YYYY-MM}`
- vượt `MONTHLY_BUDGET_USD` -> **402**
- key có `EXPIRE` để reset theo chu kỳ tháng

---

## Part 5 — Scaling & Reliability

### Exercise 5.1 — Health and readiness checks
- `GET /health`: liveness, process còn sống thì trả 200
- `GET /ready`: readiness, chỉ trả 200 khi app sẵn sàng và store ping OK; nếu chưa sẵn sàng thì trả 503

### Exercise 5.2 — Graceful shutdown
App bắt `SIGTERM` / `SIGINT`:
- dừng nhận traffic mới
- cho request đang chạy hoàn tất trong thời gian grace period
- log trạng thái shutdown

### Exercise 5.3 — Stateless design
- Không giữ conversation history trong RAM của từng instance
- History lưu trong store dùng key theo `user_id`
- Khi có `REDIS_URL`, nhiều instance dùng chung state qua Redis

Lưu ý:
- Trong `06-lab-complete` có fallback in-memory để chạy local 1 instance
- Với deployment nhiều instance để chấm stateless đúng nghĩa, cần bật Redis/shared store

### Exercise 5.4 — Run load-balanced stack

```bash
cd 05-scaling-reliability/production
docker compose up --scale agent=3
```

Kết quả:
- nginx load-balance qua nhiều instance agent
- nếu một instance lỗi, request vẫn có thể failover sang instance khác

### Exercise 5.5 — Test stateless design
Ý tưởng test:
1. Tạo conversation với cùng `user_id`
2. Kill một instance agent
3. Gửi request tiếp theo với cùng `user_id`
4. Nếu history vẫn còn, chứng tỏ state đang nằm ở shared store chứ không nằm trong RAM của instance bị kill

---

## Part 6 — Final Project

**Project:** `06-lab-complete/`  
**Tên agent:** Long Châu AI Triage Agent  
**Live deployment:** API `https://longchau-triage-api-h597.onrender.com`, UI `https://longchau-chatbot-ui-h597.onrender.com`

### Functional Requirements
- **Agent works:** API trả lời được nhiều route nghiệp vụ: `factual`, `advisory_gather`, `advisory_handoff`, `out_of_scope`, `crisis`
- **Conversation history:** lịch sử được lưu theo `user_id` trong store để giữ context qua nhiều request
- **Error handling:** request sai schema trả `422`; thiếu key trả `401`; vượt rate limit trả `429`; vượt budget trả `402`

Ví dụ endpoint chính:

```bash
curl -X POST https://longchau-triage-api-h597.onrender.com/ask \
  -H "X-API-Key: <key>" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","question":"Thuốc Efferalgan là gì?"}'
```

### Docker & Configuration
- Multi-stage Dockerfile trong `06-lab-complete/Dockerfile`
- Slim base image, non-root user, có health check
- Docker image production khoảng **272 MB**, đạt yêu cầu **< 500 MB**
- `docker-compose.yml` gồm `nginx + agent + redis + ui`
- Config lấy từ env qua `app/config.py`

Các env vars quan trọng:
- `AGENT_API_KEY`
- `OPENAI_API_KEY`
- `LLM_MODEL`
- `RATE_LIMIT_PER_MINUTE`
- `MONTHLY_BUDGET_USD`
- `REDIS_URL`

### Security
- **API key auth:** `app/auth.py`, header `X-API-Key`
- **Rate limiting:** `app/rate_limiter.py`, mặc định 10 req/min
- **Cost guard:** `app/cost_guard.py`, budget theo tháng
- **No hardcoded secrets:** secrets đọc từ environment, không hardcode trong source app production

### Reliability
- **Health check:** `GET /health`
- **Readiness check:** `GET /ready`
- **Graceful shutdown:** xử lý SIGTERM trong app lifecycle
- **Stateless design:** dùng store abstraction; khi có Redis thì state dùng chung cho nhiều instances

### Deployment
- Public API URL: `https://longchau-triage-api-h597.onrender.com`
- Public UI URL: `https://longchau-chatbot-ui-h597.onrender.com`
- Deployment config có cả `railway.toml` và `render.yaml`
- Environment variables được set trên platform cho API và UI services

### Verified Results
Theo kết quả deploy đã verify:
- `GET /health` và `GET /ready` -> 200
- `POST /ask` thiếu key -> 401
- rate limit -> 429 sau 10 request/phút
- streaming `/ask/stream` hoạt động
- image size ~272 MB

Checklist tự động:

```bash
cd 06-lab-complete
python check_production_ready.py
```

Kết quả:
- **20/20 checks passed**
- **100% production-ready**
