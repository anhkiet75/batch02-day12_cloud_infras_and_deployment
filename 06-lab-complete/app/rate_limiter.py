"""Rate limiting — fixed window 60s per user, backed by shared store (Redis/memory)."""
from fastapi import Depends, HTTPException

from .auth import verify_api_key
from .config import settings
from .store import store


def check_rate_limit(user_id: str = Depends(verify_api_key)) -> None:
    key = f"rate:{user_id}"
    current = store.incr(key)

    if current == 1:
        store.expire(key, 60)

    if current > settings.rate_limit_per_minute:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} req/min",
            headers={"Retry-After": "60"},
        )
