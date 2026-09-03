# OpsBrain — Agentic DevOps Intelligence Platform

OpsBrain is an AI system that watches your infrastructure, searches runbooks,
and answers questions like *"why is the website slow?"* automatically — so a
DevOps engineer doesn't have to manually check 10 different tools when something
breaks.

---

## Architecture

```
User (CLI / Slack)
       │
       ▼
┌──────────────────┐
│   Orchestrator   │  ← LangGraph state machine, routes tasks, aggregates results
│   (port 8000)    │
└────────┬─────────┘
         │  HTTP (Stage 1: direct)   Kafka (Stage 2: async fan-out)
    ┌────┴──────────────────────────────────────┐
    ▼            ▼              ▼               ▼
┌────────┐  ┌──────────┐  ┌────────┐  ┌──────────────┐
│  RAG   │  │Monitoring│  │ Infra  │  │    Code      │
│ Agent  │  │  Agent   │  │ Agent  │  │    Agent     │
│ :8001  │  │  :8002   │  │ :8003  │  │    :8004     │
└───┬────┘  └────┬─────┘  └───┬────┘  └──────┬───────┘
    │            │            │              │
 pgvector    Prometheus     AWS/K8s        GitHub
 (docs/      + Grafana      + Terraform    + CI/CD
  runbooks)
```

### Agent responsibilities

| Agent | What it does | Stage |
|-------|-------------|-------|
| **Orchestrator** | Receives questions, routes to agents, synthesises answers | 2 |
| **RAG Agent** | Searches runbooks + docs via pgvector, answers via Gemini | **1 ✅** |
| **Monitoring Agent** | Queries Prometheus metrics and Grafana dashboards | 2 |
| **Infra Agent** | Checks AWS state, K8s pod health, Terraform plans | 2 |
| **Code Agent** | Reads GitHub PRs, GitHub Actions pipeline status | 2 |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI / Agents | LangGraph, LangChain, Gemini, Gemini embeddings |
| Backend | Python 3.11, FastAPI, Pydantic, Uvicorn |
| Vector DB | PostgreSQL 16 + pgvector |
| Message bus | Apache Kafka (local) / Amazon MSK (production) |
| Containers | Docker, Docker Compose |
| Orchestration | Kubernetes (EKS), Helm, ArgoCD |
| CI/CD | GitHub Actions → ECR → ArgoCD |
| Infrastructure | Terraform (VPC, EKS, RDS, S3, ECR) |
| Monitoring | Prometheus, Grafana, Loki, Tempo |
| Secrets | HashiCorp Vault / AWS Secrets Manager |

---

## Quick Start (Stage 1 — RAG Agent)

### Prerequisites
- Docker + Docker Compose
- A Google AI API key

### 1. Configure environment
```bash
cp .env.example .env
# Edit .env and set GOOGLE_API_KEY and POSTGRES_PASSWORD
```

### 2. Start services
```bash
docker compose up --build
```

### 3. Verify the service
```bash
curl -s http://localhost:8001/health | jq
```

Expected response:
```json
{"status": "ok"}
```

### 4. Load runbook data
The database schema is created automatically. Before asking questions, use the
ingestion pipeline to store embedded runbook chunks in `document_chunks`.

### 5. Ask a question
```bash
curl -s -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What should I do when CPU usage is high?"}' | jq
```

---

## API Reference (RAG Agent)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe |
| `POST` | `/query` | Ask a plain-English question |

**POST /query**
```json
{ "question": "Why is the API slow?", "top_k": 5 }
```

---

## Project Structure

```
opsbrain/
├── agents/
│   ├── rag/          ← Stage 1: fully implemented
│   ├── monitoring/   ← Stage 2: stub
│   ├── infra/        ← Stage 2: stub
│   └── code/         ← Stage 2: stub
├── orchestrator/     ← Stage 2: stub (routes to RAG for now)
├── shared/           ← Pydantic models, config, Kafka client
├── infra/terraform/  ← Full AWS infrastructure as code
├── k8s/              ← Kubernetes manifests for all agents
├── .github/workflows/← GitHub Actions CI/CD pipeline
├── docs/             ← Runbooks ingested by the RAG agent
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Development

### Add a new runbook
Drop any `.md` or `.txt` file into `docs/`, then re-run ingest:
```bash
curl -X POST http://localhost:8001/ingest -H "Content-Type: application/json" \
  -d '{"directory": "./docs"}'
```

### Run tests
```bash
pip install pytest
pytest tests/ -v
```

### Lint
```bash
pip install ruff
ruff check agents/ orchestrator/ shared/
```

---

## Roadmap

- [x] **Stage 1** — RAG Agent (runbook search, Q&A via GPT-4o)
- [ ] **Stage 2** — Orchestrator + all four agents live, Kafka fan-out
- [ ] **Stage 3** — Terraform deploy to AWS EKS, ArgoCD GitOps
- [ ] **Stage 4** — Prometheus/Grafana dashboards, Slack integration, CLI tool
