# Day 12 Lab — Solution (Đáp án Codelab Part 1 → 5)

> Agent dùng cho Final Project (Part 6): **VinBank Production Agent** — port từ
> agent guardrails ở Day-11, productionize đầy đủ trong `06-lab-complete/`.

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

### Exercise 2.1 — Đọc Dockerfile
1. **Base image:** `python:3.11` (develop, full ~1GB) / `python:3.11-slim` (production).
2. **Working directory:** `/app` (hoặc `/build` ở stage builder).
3. **Tại sao COPY `requirements.txt` trước code?** Tận dụng **Docker layer cache**:
   layer cài deps chỉ rebuild khi `requirements.txt` đổi; sửa code không phải cài lại deps.
4. **CMD vs ENTRYPOINT:** `CMD` = lệnh mặc định, dễ override khi `docker run ... <cmd>`;
   `ENTRYPOINT` = cố định executable chính, các arg truyền vào nối sau nó.

### Exercise 2.3 — Multi-stage build & image size
- **Stage 1 (builder):** có pip + build tools, cài dependencies vào `~/.local`.
- **Stage 2 (runtime):** image slim sạch, **chỉ copy site-packages + source** từ builder
  → không mang theo build tools → image nhỏ và bề mặt tấn công ít hơn.

**Số đo thực tế (build trên máy lab):**
| Image | Kiểu build | Size |
|-------|-----------|------|
| `agent-develop` | single-stage `python:3.11` | **1.67 GB** |
| `vinbank-agent:prod` (Final Project) | multi-stage `python:3.11-slim` | **304 MB** |

→ Multi-stage giảm **~82%** dung lượng và đạt yêu cầu **< 500 MB**.

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
- Platform: **Railway** (Dockerfile). Config: `06-lab-complete/railway.toml`.
- Public URL & lệnh test: xem **`DEPLOYMENT.md`**.

---

## Part 4 — API Security

### Exercise 4.1–4.3 — Auth, Rate limit
- **API key** kiểm tra ở dependency `verify_api_key` (`app/auth.py`), header `X-API-Key`.
  Sai/thiếu key → **401**. Key → map ra `user_id` ổn định (sha256) để tính rate/budget theo user.
- **Rate limiting** (`app/rate_limiter.py`): **fixed-window 60s** bằng counter trên store
  (Redis `INCR` + `EXPIRE`). Vượt `RATE_LIMIT_PER_MINUTE` (mặc định 10) → **429** kèm `Retry-After`.
  Đã test: request thứ 11 trong 1 phút trả 429.
- **Rotate key:** đổi biến môi trường `AGENT_API_KEY` rồi redeploy — không sửa code.

### Exercise 4.4 — Cost guard
- `app/cost_guard.py`: mỗi request cộng `ESTIMATED_REQUEST_COST_USD` vào key tháng
  `budget:{user_id}:{YYYY-MM}` trên store. Tổng vượt `MONTHLY_BUDGET_USD` ($10) → **402**.
  Key tự `EXPIRE` ~32 ngày (tự reset sang tháng mới).

---

## Part 5 — Scaling & Reliability

### 5.1 Health & Readiness
- `GET /health` (liveness): luôn 200 nếu process sống.
- `GET /ready` (readiness): 200 chỉ khi app init xong **và** `store.ping()` OK, ngược lại **503**
  → LB ngừng route khi backend chưa sẵn sàng.

### 5.2 Graceful shutdown
- Bắt `SIGTERM`/`SIGINT` → set `_is_ready=False` (ngừng nhận traffic mới), log số request đang chạy;
  uvicorn `timeout_graceful_shutdown=30` cho request hiện tại hoàn tất.

### 5.3 Stateless design
- Không giữ conversation history trong RAM. Lưu trong **store** (`history:{user_id}`, list, TTL 1h).
  Có `REDIS_URL` → state dùng chung giữa các instance (stateless thật sự);
  không có Redis → fallback in-memory để vẫn chạy 1 container.

### 5.4 Load balancing
- `docker compose up --scale agent=3` → nginx (`nginx.conf`) phân tán qua `upstream agent_cluster`,
  có `proxy_next_upstream` failover khi 1 instance lỗi/timeout/503. Header `X-Served-By` để quan sát.

### 5.5 Test stateless
- Vì history nằm ở store dùng chung, kill 1 instance không mất hội thoại — instance khác đọc tiếp
  từ Redis bằng cùng `user_id`.

---

## Part 6 — Final Project
Xem **`06-lab-complete/`** (source) + **`DEPLOYMENT.md`** (URL).
`python check_production_ready.py` → **20/20 (100%)**.
