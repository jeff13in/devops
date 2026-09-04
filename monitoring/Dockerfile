FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY monitoring ./monitoring
COPY tests/test_monitoring_agent.py ./tests/test_monitoring_agent.py

RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8002

CMD ["uvicorn", "monitoring.main:app", "--host", "0.0.0.0", "--port", "8002"]
