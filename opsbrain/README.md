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

### 3. Ingest the sample runbook
```bash
curl -s -X POST http://localhost:8001/ingest \
  -H "Content-Type: application/json" \
  -d '{"directory": "/app/data"}' | jq
```

Expected response:
```json
{"documents_processed": 1, "chunks_stored": 1}
```

### 4. Ask a question
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
| `POST` | `/ingest` | Embed and store `.md` and `.txt` documents |
| `POST` | `/query` | Ask a plain-English question |

**POST /ingest**
```json
{ "directory": "/app/data" }
```

**POST /query**
```json
{ "question": "Why is the API slow?", "top_k": 5 }
```

---

## Run and Use the Agents

Start the available agents and database from the repository root:

```bash
docker compose up --build
```

The RAG Agent is available at `http://localhost:8001` and the Monitoring Agent
is available at `http://localhost:8002`. FastAPI's interactive API pages are
also useful while developing:

```text
http://localhost:8001/docs
http://localhost:8002/docs
```

### RAG Agent workflow

1. Confirm that the service is running:

```powershell
Invoke-RestMethod http://localhost:8001/health
```

2. Place `.md` or `.txt` runbooks in `data/`, then ingest them. The `data`
directory is mounted in the container as `/app/data`:

```powershell
$ingestBody = @{ directory = "/app/data" } | ConvertTo-Json
Invoke-RestMethod http://localhost:8001/ingest -Method Post -ContentType "application/json" -Body $ingestBody
```

3. Ask a runbook question:

```powershell
$questionBody = @{ question = "What should I do when CPU usage is high?"; top_k = 4 } | ConvertTo-Json
Invoke-RestMethod http://localhost:8001/query -Method Post -ContentType "application/json" -Body $questionBody
```

The query response includes an `answer`, the source documents used, whether the
answer is `grounded`, and the number of retrieved chunks.

### Monitoring Agent workflow

The Monitoring Agent's health endpoint verifies that its API is running and
shows the configured backend URLs:

```powershell
Invoke-RestMethod http://localhost:8002/health
```

This is the smoke test shown in the browser. The Prometheus, Grafana, and
Alertmanager routes require those services to be running separately. Before
testing them, set their reachable URLs in `.env`, then recreate the agent:

```dotenv
# Use these values when the backends run as Docker Compose services.
PROMETHEUS_BASE_URL=http://prometheus:9090
GRAFANA_BASE_URL=http://grafana:3000
ALERTMANAGER_BASE_URL=http://alertmanager:9093

# If the backends run on your Windows host, use host.docker.internal instead.
# PROMETHEUS_BASE_URL=http://host.docker.internal:9090
# GRAFANA_BASE_URL=http://host.docker.internal:3000
# ALERTMANAGER_BASE_URL=http://host.docker.internal:9093
GRAFANA_API_TOKEN=
```

```powershell
docker compose up --build -d monitoring-agent
```

Test Prometheus with a metric that exists in your environment. `up` is a good
first query because it is provided by Prometheus itself:

```powershell
$metricBody = @{ query = "up" } | ConvertTo-Json
Invoke-RestMethod http://localhost:8002/metrics/query -Method Post -ContentType "application/json" -Body $metricBody
```

Query a time range for CPU, memory, or an application metric by including
`start`, `end`, and `step`:

```powershell
$rangeBody = @{
  query = "rate(container_cpu_usage_seconds_total[5m])"
  start = (Get-Date).ToUniversalTime().AddMinutes(-15).ToString("o")
  end = (Get-Date).ToUniversalTime().ToString("o")
  step = "60s"
} | ConvertTo-Json
Invoke-RestMethod http://localhost:8002/metrics/query -Method Post -ContentType "application/json" -Body $rangeBody
```

Test alert reporting:

```powershell
Invoke-RestMethod http://localhost:8002/alerts
Invoke-RestMethod "http://localhost:8002/alerts?active_only=true"
Invoke-RestMethod http://localhost:8002/alerts/summary
```

Test Kubernetes pod health. This requires `kube-state-metrics` to be scraped
by Prometheus because the agent uses `kube_pod_*` metrics:

```powershell
Invoke-RestMethod http://localhost:8002/pods/health
Invoke-RestMethod "http://localhost:8002/pods/health?namespace=default"
```

Test Grafana using a service-account token with dashboard read access. For a
panel query, obtain the Prometheus datasource UID from Grafana's datasource
settings:

```powershell
Invoke-RestMethod http://localhost:8002/dashboards/<dashboard-uid>

$panelBody = @{
  datasource_uid = "<prometheus-datasource-uid>"
  expr = "up"
  from_minutes_ago = 15
  ref_id = "A"
} | ConvertTo-Json
Invoke-RestMethod http://localhost:8002/dashboards/panel-query -Method Post -ContentType "application/json" -Body $panelBody
```

The monitoring test is successful when metric queries return `result_count`,
alert routes return a count or summary, pod health returns a status breakdown,
and Grafana requests return dashboard panels or query results. A `503` response
means the agent could not reach the configured monitoring backend; check its
URL, Docker network, and Grafana token.

### Monitoring API reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Agent liveness and configured backend URLs |
| `POST` | `/metrics/query` | Run an instant or range PromQL query |
| `GET` | `/dashboards/{uid}` | Get Grafana dashboard metadata and panels |
| `POST` | `/dashboards/panel-query` | Query a Grafana datasource with PromQL |
| `GET` | `/alerts` | List Alertmanager alerts |
| `GET` | `/alerts/summary` | Summarize alerts by state and severity |
| `GET` | `/pods/health` | Aggregate pod phase, readiness, and restarts |

---

## Project Structure

The current implementation uses top-level `rag/` and `monitoring/` service
directories. The diagram below describes the planned broader platform layout.

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
Drop any `.md` or `.txt` file into `data/`, then re-run ingest:
```bash
curl -X POST http://localhost:8001/ingest -H "Content-Type: application/json" \
  -d '{"directory": "/app/data"}'
```

### Run tests
```bash
python -m unittest discover -s tests -v
```

### Lint
```bash
pip install ruff
ruff check rag/ monitoring/ tests/
```

---

## Roadmap

- [x] **Stage 1** — RAG Agent (runbook search, Q&A via GPT-4o)
- [ ] **Stage 2** — Orchestrator + all four agents live, Kafka fan-out
- [ ] **Stage 3** — Terraform deploy to AWS EKS, ArgoCD GitOps
- [ ] **Stage 4** — Prometheus/Grafana dashboards, Slack integration, CLI tool
