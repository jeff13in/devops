FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY rag ./rag
COPY data ./data
COPY tests/test_ingestor.py ./tests/test_ingestor.py
COPY tests/test_rag_agent.py ./tests/test_rag_agent.py
COPY tests/test_database.py ./tests/test_database.py
COPY database ./database
COPY scripts/validate_rag.py ./scripts/validate_rag.py

RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

CMD ["uvicorn", "rag.main:app", "--host", "0.0.0.0", "--port", "8001"]
