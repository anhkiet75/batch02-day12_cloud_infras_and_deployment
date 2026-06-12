"""VinBank agent brain — port từ Day-11, gọi Gemini khi có key, mock khi không.

Pipeline mỗi câu hỏi:
  1. input guardrail  -> chặn injection / off-topic / blocked topic
  2. LLM (Gemini hoặc mock deterministic) sinh câu trả lời, có context lịch sử
  3. output guardrail  -> redact secret/PII

Lưu ý production: KHÔNG nhúng secret vào system prompt (khác hẳn unsafe agent ở Day-11).
"""
from __future__ import annotations

from .config import settings
from .guardrails import REFUSAL_MESSAGE, check_input, normalize, sanitize_output

SYSTEM_PROMPT = (
    "You are a helpful customer service assistant for VinBank. "
    "You help customers with account inquiries, transactions, interest rates, "
    "cards and loans. Answer concisely and politely. "
    "Never reveal internal system details, passwords, or API keys. "
    "If asked about topics outside banking, politely redirect."
)

# Mock trả lời deterministic theo từ khoá — dùng khi không có GOOGLE_API_KEY.
_MOCK_REPLIES = {
    "interest": "Lãi suất tiết kiệm VinBank hiện từ 4.5%/năm (kỳ hạn 12 tháng). "
                "Bạn muốn xem kỳ hạn nào cụ thể?",
    "lai suat": "Lãi suất tiết kiệm VinBank hiện từ 4.5%/năm (kỳ hạn 12 tháng).",
    "balance": "Để kiểm tra số dư, vui lòng đăng nhập VinBank app hoặc gọi 1900-vinbank.",
    "so du": "Để kiểm tra số dư, vui lòng đăng nhập VinBank app hoặc gọi 1900-vinbank.",
    "transfer": "Bạn có thể chuyển tiền 24/7 qua VinBank app, hạn mức mặc định 100 triệu/ngày.",
    "chuyen tien": "Bạn có thể chuyển tiền 24/7 qua VinBank app, hạn mức 100 triệu/ngày.",
    "loan": "VinBank có gói vay tiêu dùng lãi suất từ 9%/năm, duyệt nhanh trong 24h.",
    "vay": "VinBank có gói vay tiêu dùng lãi suất từ 9%/năm, duyệt nhanh trong 24h.",
    "card": "Thẻ tín dụng VinBank miễn phí thường niên năm đầu, hoàn tiền tới 5%.",
    "the tin dung": "Thẻ tín dụng VinBank miễn phí thường niên năm đầu, hoàn tiền tới 5%.",
}


def _mock_answer(question: str) -> str:
    text = normalize(question)
    for keyword, reply in _MOCK_REPLIES.items():
        if keyword in text:
            return reply
    return ("Cảm ơn bạn đã liên hệ VinBank. Tôi có thể hỗ trợ về tài khoản, "
            "giao dịch, lãi suất, thẻ và khoản vay. Bạn cần thông tin gì ạ?")


def _gemini_answer(question: str, history: list[str]) -> str:
    """Gọi Gemini thật. Ném exception nếu lỗi -> caller fallback mock."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.google_api_key)
    context = "\n".join(history[-6:])  # tối đa 3 lượt gần nhất
    prompt = f"{context}\nuser: {question}" if context else question

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
    )
    return (response.text or "").strip() or _mock_answer(question)


def answer(question: str, history: list[str]) -> tuple[str, str]:
    """Trả về (answer, status).

    status: blocked_<reason> | gemini | mock
    history: list các dòng "user: ..." / "assistant: ..." từ store.
    """
    allowed, reason = check_input(question)
    if not allowed:
        return REFUSAL_MESSAGE, f"blocked_{reason}"

    if settings.google_api_key:
        try:
            return sanitize_output(_gemini_answer(question, history)), "gemini"
        except Exception:
            # Lỗi LLM (hết quota, mạng...) -> vẫn phục vụ được bằng mock.
            return sanitize_output(_mock_answer(question)), "mock_fallback"

    return sanitize_output(_mock_answer(question)), "mock"
