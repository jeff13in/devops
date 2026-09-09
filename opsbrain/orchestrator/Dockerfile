FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn pydantic httpx langgraph langchain-openai
COPY shared/         ./shared/
COPY orchestrator/   ./orchestrator/
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
