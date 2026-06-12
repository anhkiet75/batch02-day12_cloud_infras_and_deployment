"""Production config — 12-Factor: tất cả lấy từ environment variables.

Agent gốc: **Long Châu AI Triage Middleware** (sản phẩm nhóm Day-06, dùng LLM thật
qua OpenRouter), được productionize cho Day-12: auth + rate limit + cost guard +
stateless Redis + health/readiness + graceful shutdown.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Server ──────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    environment: str = "development"
    debug: bool = False

    # ── App ─────────────────────────────────────────────
    app_name: str = "Long Chau Triage Agent"
    app_version: str = "1.0.0"

    # ── Storage (stateless design) ──────────────────────
    # Để trống -> fallback in-memory store (chạy 1 container không cần Redis).
    redis_url: str = ""

    # ── LLM (OpenAI) ────────────────────────────────────
    # Không có key -> agent chạy stub heuristic (vẫn đủ safety gate + triage cơ bản).
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    # Endpoint tương thích OpenAI; đổi để dùng OpenRouter/Azure mà không sửa code.
    llm_base_url: str = "https://api.openai.com/v1/chat/completions"

    # ── Security ────────────────────────────────────────
    agent_api_key: str = "dev-key-change-me"
    log_level: str = "INFO"

    # ── Rate limiting ───────────────────────────────────
    rate_limit_per_minute: int = 10

    # ── Cost guard ──────────────────────────────────────
    monthly_budget_usd: float = 10.0
    estimated_request_cost_usd: float = 0.1

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
