# Streamlit UI — image riêng, tách khỏi API để API container vẫn slim.
FROM python:3.11-slim

WORKDIR /ui

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY streamlit_app.py .

EXPOSE 8501

# Shell form để expand $PORT (Railway/Render cấp port động; local mặc định 8501).
# AGENT_API_URL inject qua env (trỏ API; trong compose là nginx).
CMD streamlit run streamlit_app.py \
    --server.address=0.0.0.0 \
    --server.port=${PORT:-8501} \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --browser.gatherUsageStats=false
