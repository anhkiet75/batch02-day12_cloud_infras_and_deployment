"""Guardrails — port từ Day-11 (input + output guardrails cho VinBank agent).

Input guardrail:  chặn prompt-injection và chủ đề bị cấm TRƯỚC khi gọi LLM.
Output guardrail: che (redact) secret/PII nếu lỡ lọt ra response.

Guardrails chạy độc lập với LLM, nên kể cả ở chế độ mock (không có API key) thì
lớp bảo vệ vẫn hoạt động — đây chính là phần "agent thật" được productionize.
"""
from __future__ import annotations

import re
import unicodedata

from .config import ALLOWED_TOPICS, BLOCKED_TOPICS


def normalize(text: str) -> str:
    """Lowercase + bỏ dấu tiếng Việt để khớp topic không phụ thuộc dấu.

    Vì sao cần: topic list không dấu ("chuyen tien"), còn user gõ có dấu
    ("chuyển tiền") -> nếu không chuẩn hoá sẽ false-reject câu hỏi banking hợp lệ.
    """
    text = text.lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")

# Các pattern prompt-injection phổ biến.
_INJECTION_PATTERNS = [
    r"ignore (all |the |previous |above )?(instructions|prompts?)",
    r"disregard (all |the |previous )?(instructions|rules)",
    r"reveal (the |your )?(system prompt|instructions|secret|password|api key)",
    r"what('?s| is) (the |your )?(system prompt|admin password|api key)",
    r"\bsystem prompt\b",
    r"\byou are now\b",
    r"\bact as\b.*\b(admin|root|developer mode)\b",
    r"\bdeveloper mode\b",
    r"bo qua.*(huong dan|chi dan|quy tac)",
    r"tiet lo.*(mat khau|api key|system prompt)",
]

# Secret/PII patterns dùng cho output redaction.
_SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9\-]{6,}",                       # API keys kiểu sk-...
    r"admin123",                                    # known seeded secret (Day-11)
    r"\bpassword\s+is\s+['\"]?[^\s'\"]+",         # "password is xxx"
    r"[a-z0-9.\-]+\.internal(:\d+)?",              # internal hostnames
    r"\b\d{12,19}\b",                               # số thẻ / số tài khoản dài
]

REFUSAL_MESSAGE = (
    "Xin lỗi, tôi chỉ hỗ trợ các câu hỏi về dịch vụ ngân hàng VinBank "
    "(tài khoản, giao dịch, lãi suất, thẻ, vay...). "
    "Tôi không thể trả lời yêu cầu này."
)


def check_input(question: str) -> tuple[bool, str]:
    """Trả về (allowed, reason). allowed=False -> chặn trước khi gọi LLM."""
    text = normalize(question)

    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, text):
            return False, "prompt_injection"

    for topic in BLOCKED_TOPICS:
        if topic in text:
            return False, "blocked_topic"

    # Topic relevance: nếu không chạm bất kỳ chủ đề banking nào -> off-topic.
    if not any(topic in text for topic in ALLOWED_TOPICS):
        return False, "off_topic"

    return True, "ok"


def sanitize_output(answer: str) -> str:
    """Che secret/PII nếu lọt vào câu trả lời."""
    cleaned = answer
    for pattern in _SECRET_PATTERNS:
        cleaned = re.sub(pattern, "[REDACTED]", cleaned, flags=re.IGNORECASE)
    return cleaned
