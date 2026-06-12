"""Production config — 12-Factor: tất cả lấy từ environment variables.

Agent gốc: VinBank customer-service assistant (port từ Day-11 Guardrails lab),
được productionize cho Day-12: auth + rate limit + cost guard + stateless Redis.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Server ──────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    environment: str = "development"
    debug: bool = False

    # ── App ─────────────────────────────────────────────
    app_name: str = "VinBank Production Agent"
    app_version: str = "1.0.0"

    # ── Storage (stateless design) ──────────────────────
    # Để trống -> tự fallback sang in-memory store (chạy 1 container không cần Redis).
    redis_url: str = ""

    # ── LLM (Gemini) ────────────────────────────────────
    # Không có key -> agent chạy ở chế độ mock deterministic (vẫn đủ guardrails).
    google_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"

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

# ── Banking domain knowledge (port từ Day-11 core/config.py) ──
ALLOWED_TOPICS = [
    "banking", "account", "transaction", "transfer", "loan", "interest",
    "savings", "credit", "deposit", "withdrawal", "balance", "payment",
    "tai khoan", "giao dich", "tiet kiem", "lai suat", "chuyen tien",
    "the tin dung", "so du", "vay", "ngan hang", "atm", "vinbank",
]

BLOCKED_TOPICS = [
    "hack", "exploit", "weapon", "drug", "illegal",
    "violence", "gambling", "bomb", "kill", "steal",
]
