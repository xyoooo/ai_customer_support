# SupportPilot

SupportPilot is a production-style, multi-tenant AI customer-support platform. The repository now contains the Week 1 identity and tenant-isolation foundation plus the Week 2 document lifecycle: secure streaming uploads, immutable versions, portable local object storage, durable PostgreSQL jobs, a separate worker, processing status, and retry controls.

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

No AI provider, parser, embedding model, or retrieval dependency is included yet. Week 3 will add those capabilities behind the stable document, storage, and worker interfaces established in Week 2.

## Weekly progress

See the [weekly progress index](docs/weekly-progress.md) for the preview plan and review report from each development week.

Week 1's delivered scope and evidence are recorded in the [Week 1 review report](docs/week-1-review-report.md). The [Week 2 preview plan](docs/week-2-preview-plan.md) defines the document-lifecycle milestone, acceptance criteria, and handoff to the RAG baseline.

The accepted [document lifecycle and durable-job ADR](docs/adr/0004-document-lifecycle-and-durable-jobs.md) defines the stable boundary for Week 2 implementation.
