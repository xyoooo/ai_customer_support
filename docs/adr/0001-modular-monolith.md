# ADR 0001: Use a modular monolith

- Status: accepted
- Date: 2026-07-13

## Context

The product needs clear domain boundaries, an API process, and an asynchronous worker, but the portfolio workload does not justify independently deployed microservices.

## Decision

Use one Python project containing deployable `apps` and shared `packages`. Ship the API and worker as separate process commands from the same versioned image. Use one PostgreSQL database and version all schema changes through Alembic.

## Consequences

Domain boundaries remain visible and testable without distributed transactions or extra infrastructure. A domain can be extracted later only when measured scaling or ownership requirements justify it.

