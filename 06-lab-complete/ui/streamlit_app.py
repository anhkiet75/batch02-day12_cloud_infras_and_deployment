"""Streamlit chat UI cho VinBank Production Agent.

Gọi backend FastAPI qua endpoint streaming /ask/stream và hiển thị câu trả lời
gõ dần (st.write_stream). UI tách riêng khỏi API container để image API vẫn slim.

Chạy:
    pip install -r requirements.txt
    streamlit run streamlit_app.py
"""
import os

import requests
import streamlit as st

DEFAULT_API = os.getenv(
    "AGENT_API_URL", "https://vinbank-production-agent-production.up.railway.app"
)

st.set_page_config(page_title="VinBank Agent", page_icon="🏦")

# ── Sidebar: cấu hình kết nối ────────────────────────────
with st.sidebar:
    st.header("⚙️ Kết nối")
    api_url = st.text_input("API URL", value=DEFAULT_API).rstrip("/")
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

st.title("🏦 VinBank Customer Agent")
st.caption("Trợ lý ngân hàng có guardrails • auth • rate limit • streaming")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Hiển thị lịch sử hội thoại (client-side, chỉ để xem).
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


def _error_message(status_code: int, text: str) -> str:
    mapping = {
        401: "🔒 Sai hoặc thiếu API key.",
        402: "💸 Vượt ngân sách tháng (cost guard).",
        429: "⏳ Quá giới hạn request/phút (rate limit).",
        503: "🚧 Agent chưa sẵn sàng.",
    }
    return mapping.get(status_code, f"Lỗi {status_code}: {text[:200]}")


def stream_answer(question: str):
    """Yield từng chunk text từ /ask/stream để dùng với st.write_stream."""
    with requests.post(
        f"{api_url}/ask/stream",
        json={"question": question},
        headers={"X-API-Key": api_key},
        stream=True,
        timeout=60,
    ) as resp:
        if not resp.ok:
            yield _error_message(resp.status_code, resp.text)
            return
        resp.encoding = "utf-8"
        for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
            if chunk:
                yield chunk


def full_answer(question: str) -> str:
    resp = requests.post(
        f"{api_url}/ask",
        json={"question": question},
        headers={"X-API-Key": api_key},
        timeout=60,
    )
    if not resp.ok:
        return _error_message(resp.status_code, resp.text)
    return resp.json().get("answer", "")


# ── Chat input ───────────────────────────────────────────
if prompt := st.chat_input("Hỏi về tài khoản, lãi suất, chuyển tiền..."):
    if not api_key:
        st.warning("Nhập API Key ở sidebar trước nhé.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            if use_stream:
                answer = st.write_stream(stream_answer(prompt))
            else:
                answer = full_answer(prompt)
                st.markdown(answer)
        except Exception as exc:  # noqa: BLE001
            answer = f"Không kết nối được API: {exc}"
            st.error(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
