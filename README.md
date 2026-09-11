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

The production application still ends at the Week 2 document lifecycle. This lab branch contains the measured RAG experiment implementation, but it is not wired into the production worker or API and will not be merged wholesale. The selected C1+E1 pipeline will be implemented separately behind the stable document, storage, and worker interfaces.

## Weekly progress

See the [weekly progress index](docs/weekly-progress.md) for the preview plan and review report from each development week.

Week 1's delivered scope and evidence are recorded in the [Week 1 review report](docs/week-1-review-report.md). The [Week 2 preview plan](docs/week-2-preview-plan.md) defines the document-lifecycle milestone, acceptance criteria, and handoff to the RAG baseline.

The accepted [document lifecycle and durable-job ADR](docs/adr/0004-document-lifecycle-and-durable-jobs.md) defines the stable boundary for Week 2 implementation. The [Week 3 preview plan](docs/week-3-preview-plan.md) defines the lab-based chunking and embedding comparison, manual selection gate, and single-pipeline production milestone. [ADR 0006](docs/adr/0006-lab-evaluation-and-single-rag-production-pipeline.md) records why the lab branch is not merged and only the selected solution enters `main`. The [RAG strategy lab specification](docs/rag-strategy-lab.md) defines the candidates and test criteria, the [selection report](docs/week-3-rag-selection-report.md) records the C1+E1 decision, and the [production handoff plan](docs/week-3-production-handoff.md) defines how to build the selected pipeline from clean `main`.
