FROM python:3.11-alpine

WORKDIR /app

COPY agents/monitoring/demo_metrics.py ./demo_metrics.py

EXPOSE 9100
CMD ["python", "demo_metrics.py"]
