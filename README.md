# SupportPilot

SupportPilot is a production-style, multi-tenant AI customer-support platform. This repository currently contains the Week 1 foundation: authentication, workspaces, role-based access control, PostgreSQL row-level security, migrations, a small web shell, and automated tests.

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

No AI provider or document-processing dependency is included yet. Those adapters will be added behind stable domain interfaces in later milestones.

## Development report

See the [Week 1 development report](docs/week-1-development-report.md) for delivered scope, engineering rationale, test outcomes, known limitations, and prioritized next improvements.

The accepted [document lifecycle and durable-job ADR](docs/adr/0004-document-lifecycle-and-durable-jobs.md) defines the stable boundary for Week 2 implementation.
