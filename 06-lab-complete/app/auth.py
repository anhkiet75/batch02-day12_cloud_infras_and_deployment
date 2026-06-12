"""API key authentication. Map key -> user_id ổn định để rate-limit/cost theo user."""
import hashlib

from typing import Optional

from fastapi import Header, HTTPException

from .config import settings


def verify_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> str:
    # Thiếu key hoặc sai key đều trả 401 (không phải 422) cho rõ ràng.
    if not x_api_key or x_api_key != settings.agent_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    digest = hashlib.sha256(x_api_key.encode("utf-8")).hexdigest()[:12]
    return f"user-{digest}"
