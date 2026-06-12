"""AI triage orchestrator — port từ Long Châu Triage (Day-06).

Flow: crisis check → safety gate (high-risk) → classify (LLM) →
      factual answer (+ product search) | advisory gather | advisory handoff.

Khác bản gốc:
- Bỏ ghi log ra file JSONL (chống stateless) → main.py log structured JSON thay thế.
- Thêm nhánh stub heuristic khi không có OPENROUTER_API_KEY → vẫn chạy/deploy được.
- Crisis (tự hại) chặn cứng trước, kèm hotline.
"""
from __future__ import annotations

from . import llm_client as llm
from . import prompts
from .config import settings
from .longchau_search import search_products
from .safety_gate import is_crisis, is_high_risk

CRISIS_REPLY = (
    "Mình rất lo cho bạn. Nếu bạn đang có ý định tự làm hại bản thân, hãy liên hệ ngay:\n"
    "• **Cấp cứu 115**\n"
    "• **Đường dây nóng Ngày Mai 096 306 1414**\n\n"
    "Bạn không đơn độc — hãy tìm người thân hoặc chuyên gia y tế hỗ trợ ngay nhé."
)


def _format_product_links(products: list[dict]) -> str:
    if not products:
        return ""
    lines = ["\n\n---\n🛒 **Sản phẩm tại Long Châu:**"]
    for p in products:
        lines.append(f"• [{p['name']}]({p['url']}) — {p['price']}")
    return "\n".join(lines)


def _stub(message: str, model_name: str) -> dict:
    """Heuristic khi chưa cấu hình OPENROUTER_API_KEY (không gọi LLM)."""
    msg = message.lower()
    factual_kw = ["tác dụng", "thành phần", "công dụng", "là gì", "giá", "mua", "tìm"]
    if any(k in msg for k in factual_kw):
        return {
            "route": "factual",
            "reply": ("Đây là thông tin chung về sản phẩm bạn hỏi. Dùng theo liều khuyến cáo, "
                      "đọc kỹ hướng dẫn trước khi dùng.\n\n_Nếu bạn đang điều trị bệnh cụ thể, "
                      "hãy hỏi dược sĩ để được tư vấn chính xác hơn._"),
            "reply_md": None, "products": [], "handoff_summary": None,
            "safety_gate_triggered": False, "model": model_name,
        }
    return {
        "route": "advisory_gather",
        "reply": ("Để tư vấn chính xác hơn, bạn cho mình biết đang dùng thuốc này để điều trị "
                  "bệnh gì và có đang dùng thuốc nào khác không?"),
        "reply_md": None, "products": [], "handoff_summary": None,
        "safety_gate_triggered": False, "model": model_name,
    }


async def triage(message: str, history: list[dict]) -> dict:
    """Trả về dict kết quả triage. Không raise — luôn có câu trả lời an toàn."""
    model_name = llm.get_model_name()

    # 0. Crisis (tự hại / tự tử) — chặn cứng, ưu tiên cao nhất.
    if is_crisis(message):
        return {
            "route": "crisis", "reply": CRISIS_REPLY, "reply_md": None, "products": [],
            "handoff_summary": "CRISIS: khách có dấu hiệu tự hại, cần can thiệp ngay.",
            "safety_gate_triggered": True, "model": model_name,
        }

    # Chưa cấu hình LLM thật -> stub heuristic (an toàn để deploy/chấm).
    if not settings.openai_api_key:
        return _stub(message, "stub")

    # 1. Safety gate — high-risk medical context: ép sang handoff dược sĩ.
    if is_high_risk(message):
        try:
            handoff_summary = await llm.chat([
                {"role": "system", "content": prompts.HANDOFF_SUMMARY_SYSTEM},
                *history, {"role": "user", "content": message},
            ])
        except Exception:
            handoff_summary = f"Khách hỏi: {message[:200]}. Cần tư vấn chuyên sâu."
        return {
            "route": "advisory_handoff",
            "reply": ("⚠️ Câu hỏi của bạn liên quan đến tình trạng sức khoẻ cụ thể và cần được "
                      "tư vấn bởi chuyên gia.\n\nĐang chuyển cho **dược sĩ** hỗ trợ bạn ngay."),
            "reply_md": None, "products": [], "handoff_summary": handoff_summary,
            "safety_gate_triggered": True, "model": model_name,
        }

    # 2. Classify (LLM JSON).
    try:
        classification = await llm.chat_json([
            {"role": "system", "content": prompts.CLASSIFIER_SYSTEM},
            *history, {"role": "user", "content": message},
        ])
        question_type = classification.get("type", "advisory")
        needs_context = classification.get("needs_context", True)
        drug_keyword = classification.get("drug_keyword") or None
        is_dangerous = classification.get("is_dangerous", False)
        show_products = classification.get("show_products", True)
    except Exception:
        question_type, needs_context = "advisory", True
        drug_keyword, is_dangerous, show_products = None, False, True

    # 2b. Out of scope — từ chối không gọi LLM trả lời.
    if question_type == "out_of_scope":
        if is_dangerous:
            reply = ("⚠️ Câu hỏi này nằm ngoài phạm vi tư vấn dược phẩm và có thể liên quan đến "
                     "tình huống khẩn cấp.\n\nVui lòng liên hệ **Cấp cứu 115** hoặc cơ sở y tế gần "
                     "nhất. Tôi không thể cung cấp thông tin này.")
        else:
            reply = ("Xin lỗi, câu hỏi này nằm ngoài phạm vi tư vấn dược phẩm. Tôi chỉ hỗ trợ các "
                     "câu hỏi liên quan đến thuốc và sức khoẻ.")
        return {
            "route": "out_of_scope", "reply": reply, "reply_md": None, "products": [],
            "handoff_summary": None, "safety_gate_triggered": False, "model": model_name,
        }

    # 3a. Factual → trả lời + tìm sản phẩm song song.
    if question_type == "factual":
        import asyncio

        answer_messages = [
            {"role": "system", "content": prompts.FACTUAL_ANSWER_SYSTEM},
            *history, {"role": "user", "content": message},
        ]
        if drug_keyword and show_products:
            results = await asyncio.gather(
                llm.chat(answer_messages),
                search_products(drug_keyword, max_results=3),
                return_exceptions=True,
            )
            reply = results[0] if not isinstance(results[0], Exception) else None
            products = results[1] if not isinstance(results[1], Exception) else []
            if reply is None:
                reply = "Xin lỗi, không thể tải thông tin lúc này. Vui lòng thử lại hoặc hỏi dược sĩ."
        else:
            try:
                reply = await llm.chat(answer_messages)
            except Exception:
                reply = "Xin lỗi, không thể tải thông tin lúc này. Vui lòng thử lại hoặc hỏi dược sĩ."
            products = []

        return {
            "route": "factual", "reply": reply,
            "reply_md": reply + _format_product_links(products),
            "products": products, "handoff_summary": None,
            "safety_gate_triggered": False, "model": model_name,
        }

    # 3b. Advisory + thiếu thông tin → hỏi thêm.
    if needs_context:
        try:
            reply = await llm.chat([
                {"role": "system", "content": prompts.GATHER_CONTEXT_SYSTEM},
                *history, {"role": "user", "content": message},
            ])
        except Exception:
            reply = ("Để tư vấn chính xác hơn, bạn cho mình biết đang điều trị bệnh gì và có đang "
                     "dùng thuốc nào khác không?")
        return {
            "route": "advisory_gather", "reply": reply, "reply_md": None, "products": [],
            "handoff_summary": None, "safety_gate_triggered": False, "model": model_name,
        }

    # 3c. Advisory + đủ thông tin → tóm tắt handoff cho dược sĩ.
    try:
        handoff_summary = await llm.chat([
            {"role": "system", "content": prompts.HANDOFF_SUMMARY_SYSTEM},
            *history, {"role": "user", "content": message},
        ])
    except Exception:
        handoff_summary = f"Khách hỏi: {message[:200]}. Cần tư vấn chuyên sâu."
    return {
        "route": "advisory_handoff",
        "reply": "Cảm ơn bạn đã cung cấp thông tin. Đang chuyển cho **dược sĩ** tư vấn chi tiết.",
        "reply_md": None, "products": [], "handoff_summary": handoff_summary,
        "safety_gate_triggered": False, "model": model_name,
    }
