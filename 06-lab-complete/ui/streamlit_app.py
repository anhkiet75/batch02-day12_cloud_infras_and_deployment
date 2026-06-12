"""Streamlit chat UI cho Long Châu Triage Agent.

Gọi backend FastAPI (/ask/stream) và hiển thị câu trả lời gõ dần (st.write_stream),
kèm badge route (factual / advisory / handoff / out_of_scope / crisis).
UI tách riêng khỏi API container để image API vẫn slim.

Chạy:
    pip install -r requirements.txt
    streamlit run streamlit_app.py
"""
import os

import requests
import streamlit as st

def _normalize_url(url: str) -> str:
    """Thêm https:// nếu thiếu scheme (Render fromService.host trả về hostname trần)."""
    url = (url or "").strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


DEFAULT_API = _normalize_url(os.getenv(
    "AGENT_API_URL", "https://vinbank-production-agent-production.up.railway.app"
))

ROUTE_BADGE = {
    "factual": ("🟢 Factual", "Trả lời thông tin chung"),
    "advisory_gather": ("🟡 Advisory", "Đang hỏi thêm để tư vấn"),
    "advisory_handoff": ("🟠 Handoff", "Chuyển dược sĩ"),
    "out_of_scope": ("⚪ Out of scope", "Ngoài phạm vi dược"),
    "crisis": ("🔴 Crisis", "Cảnh báo an toàn"),
}

st.set_page_config(page_title="Long Châu AI Triage", page_icon="💊")

with st.sidebar:
    st.header("⚙️ Kết nối")
    api_url = _normalize_url(st.text_input("API URL", value=DEFAULT_API))
    api_key = st.text_input("API Key (X-API-Key)", type="password",
                            value=os.getenv("AGENT_API_KEY", ""))
    use_stream = st.toggle("Streaming", value=True)

    if st.button("🩺 Health check"):
        try:
            r = requests.get(f"{api_url}/health", timeout=10)
            st.success(r.json()) if r.ok else st.error(f"{r.status_code}: {r.text}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Không kết nối được: {exc}")

    if st.button("🗑️ Xoá hội thoại"):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.caption("Thử hỏi:")
    st.caption("• Paracetamol có công dụng gì?\n"
               "• Tôi bị tiểu đường, uống thêm ibuprofen được không?\n"
               "• Tôi muốn mua vitamin C")

st.title("💊 Long Châu AI Triage")
st.caption("Tư vấn thuốc thông minh • safety gate • auth • rate limit • streaming")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("route") and msg["route"] in ROUTE_BADGE:
            st.caption(ROUTE_BADGE[msg["route"]][0])
        st.markdown(msg["content"])


def _error_message(status_code: int, text: str) -> str:
    mapping = {
        401: "🔒 Sai hoặc thiếu API key.",
        402: "💸 Vượt ngân sách tháng (cost guard).",
        429: "⏳ Quá giới hạn request/phút (rate limit).",
        503: "🚧 Agent chưa sẵn sàng.",
    }
    return mapping.get(status_code, f"Lỗi {status_code}: {text[:200]}")


def stream_answer(question: str, route_holder: dict):
    """Yield từng chunk từ /ask/stream; lưu route từ header vào route_holder."""
    with requests.post(
        f"{api_url}/ask/stream",
        json={"question": question},
        headers={"X-API-Key": api_key},
        stream=True,
        timeout=60,
    ) as resp:
        route_holder["route"] = resp.headers.get("X-Agent-Route")
        if not resp.ok:
            yield _error_message(resp.status_code, resp.text)
            return
        resp.encoding = "utf-8"
        for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
            if chunk:
                yield chunk


def full_answer(question: str, route_holder: dict) -> str:
    resp = requests.post(
        f"{api_url}/ask",
        json={"question": question},
        headers={"X-API-Key": api_key},
        timeout=60,
    )
    if not resp.ok:
        return _error_message(resp.status_code, resp.text)
    data = resp.json()
    route_holder["route"] = data.get("route")
    return data.get("answer", "")


if prompt := st.chat_input("Hỏi về thuốc, công dụng, mua sản phẩm..."):
    if not api_key:
        st.warning("Nhập API Key ở sidebar trước nhé.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    route_holder: dict = {}
    with st.chat_message("assistant"):
        try:
            if use_stream:
                answer = st.write_stream(stream_answer(prompt, route_holder))
            else:
                answer = full_answer(prompt, route_holder)
                st.markdown(answer)
            route = route_holder.get("route")
            if route and route in ROUTE_BADGE:
                st.caption(f"{ROUTE_BADGE[route][0]} — {ROUTE_BADGE[route][1]}")
        except Exception as exc:  # noqa: BLE001
            answer = f"Không kết nối được API: {exc}"
            st.error(answer)
            route = None

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "route": route_holder.get("route")}
    )
