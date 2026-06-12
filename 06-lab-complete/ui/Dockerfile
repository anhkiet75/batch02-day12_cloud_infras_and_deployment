# Streamlit UI — image riêng, tách khỏi API để API container vẫn slim.
FROM python:3.11-slim

WORKDIR /ui

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY streamlit_app.py .

EXPOSE 8501

# AGENT_API_URL inject qua env (mặc định trỏ service nginx trong compose).
CMD ["streamlit", "run", "streamlit_app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
