# SupportPilot

SupportPilot is a production-style, multi-tenant AI customer-support platform. It includes identity and tenant isolation, secure versioned document uploads, durable PostgreSQL jobs, and the selected Week 3 `rag-v1-c1-e1` evidence pipeline: layout-aware parsing, C1 structure-aware chunks, pinned local E1 embeddings, and deterministic hybrid retrieval with source locators.

## Local prerequisites

- Docker Desktop with the WSL 2 backend
- Python 3.12 managed by `uv`
- Node.js 24 LTS

## Start locally

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open `http://localhost:5173`. API documentation is available at `http://localhost:8000/docs` in development.

## Development checks

```powershell
uv sync --all-groups
uv run ruff check .
uv run mypy apps packages
uv run pytest
Set-Location apps/web
npm.cmd ci
npm.cmd run check
npm.cmd run check:api
```

Before starting the worker, provision the pinned E1 model files under
`var/rag-model-cache/E1` with `uv run python scripts/cache_rag_model.py`; this directory is
intentionally excluded from Git. Provisioning is an explicit setup/CI step. The runtime
does not download model files or silently truncate inputs.

## Weekly progress

See the [weekly progress index](docs/weekly-progress.md) for the preview plan and review report from each development week.

Week 1's delivered scope and evidence are recorded in the [Week 1 review report](docs/week-1-review-report.md). The [Week 2 preview plan](docs/week-2-preview-plan.md) defines the document-lifecycle milestone, acceptance criteria, and handoff to the RAG baseline.

The accepted [document lifecycle and durable-job ADR](docs/adr/0004-document-lifecycle-and-durable-jobs.md) defines the stable boundary for Week 2 implementation. The [Week 3 selection report](docs/week-3-rag-selection-report.md) records the full candidate result. [ADR 0006](docs/adr/0006-lab-evaluation-and-single-rag-production-pipeline.md) separates the lab from production, while [ADR 0007](docs/adr/0007-c1-e1-production-rag-pipeline.md) fixes C1+E1 as the only production pipeline.
