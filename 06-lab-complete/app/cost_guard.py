"""Cost guard — giới hạn ngân sách theo user theo tháng (Redis key tự expire ~32 ngày)."""
from datetime import datetime, timezone

from fastapi import Depends, HTTPException

from .auth import verify_api_key
from .config import settings
from .store import store


def check_budget(user_id: str = Depends(verify_api_key)) -> None:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    key = f"budget:{user_id}:{month}"
    current = float(store.get(key) or 0)

    if current + settings.estimated_request_cost_usd > settings.monthly_budget_usd:
        raise HTTPException(status_code=402, detail="Monthly budget exceeded")

    store.incrbyfloat(key, settings.estimated_request_cost_usd)
    store.expire(key, 32 * 24 * 3600)
