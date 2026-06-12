"""LLM client — OpenAI Chat Completions (mặc định), provider-agnostic qua base URL.

Dùng OpenAI thật với OPENAI_API_KEY. Có thể trỏ sang endpoint tương thích khác
(OpenRouter, Azure...) bằng LLM_BASE_URL mà không đổi code.
"""
import json

import httpx

from .config import settings


async def chat(messages: list[dict], json_mode: bool = False) -> str:
    """Gọi chat completions, trả về text content của assistant."""
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set")

    payload: dict = {"model": settings.llm_model, "messages": messages}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(settings.llm_base_url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def chat_json(messages: list[dict]) -> dict:
    """Gọi LLM và parse JSON. Trả {} nếu không parse được."""
    raw = await chat(messages, json_mode=True)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass
        return {}


def get_model_name() -> str:
    return settings.llm_model
