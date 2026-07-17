# ADR 0001: Use a modular monolith

- Status: accepted
- Date: 2026-07-13
- Last reviewed: 2026-07-17

## Context

SupportPilot needs an HTTP API, asynchronous processing, and clear boundaries between authentication, workspaces, documents, retrieval, conversations, and evaluation. It must also remain understandable and inexpensive for one developer to build, test, deploy, and demonstrate.

The decision is about the code and deployment boundary, not whether domain boundaries exist. All options must preserve explicit module ownership and testable interfaces.

## Decision drivers

- Keep local development, deployment, and debugging simple.
- Preserve domain boundaries that can be extracted later.
- Avoid distributed transactions and network failure modes before they are required.
- Allow the API and worker to scale and restart independently.
- Produce architecture that one developer can operate responsibly.

## Options comparison

| Option | Advantages | Limitations |
|---|---|---|
| Modular monolith with separate API and worker processes | One repository and release; direct in-process domain calls; simple transactions; shared types and migrations; API and worker can run independently | Requires discipline to prevent module coupling; one release version; a resource-heavy module can still affect shared infrastructure |
| Microservices | Independent deployment and scaling; strong service ownership boundaries; technology can vary by service | Adds service discovery, network contracts, distributed tracing, deployment coordination, and partial-failure handling; cross-service changes and transactions are harder |
| Single layered application with no domain modules | Fastest initial scaffolding; few abstractions | Business rules become coupled to HTTP and persistence code; difficult to test or extract; worker and API responsibilities blur |
| Serverless functions per feature | Fine-grained scaling and pay-per-use; managed runtime operations | Cold starts, fragmented local development, provider-specific orchestration, and many distributed boundaries for a small workload |

## Decision

Use one Python project containing deployable `apps` and shared `packages`. Keep domain modules explicit and prevent transport or provider code from becoming the owner of business rules.

Ship the API and worker as separate process commands from the same versioned image. Use one PostgreSQL database and version all schema changes through Alembic.

## Why this suits the current stage

The current team is one developer, the product boundary is still evolving, and the initial workload does not require independent service scaling. A modular monolith exposes meaningful architecture in the portfolio without spending most of the delivery window on distributed-system operations.

Separate API and worker processes provide the operational separation already needed for request handling and long-running jobs while retaining simple code sharing and database transactions.

## Consequences

### Advantages accepted

- Domain behavior can be tested without network calls.
- Database changes and related application changes ship together.
- Local development and low-cost hosting require fewer moving parts.
- A domain can still be extracted behind its existing interface later.

### Limitations accepted

- Module boundaries rely on code review, dependency rules, and tests rather than network isolation.
- API and worker normally share a release cadence.
- The shared database can become a coupling point if modules bypass their ownership boundaries.

## When to reconsider

Consider extracting a service only when at least one of these conditions is measured or organizationally real:

- A domain needs a materially different deployment cadence or reliability target.
- Its CPU, memory, latency, or scaling profile cannot be handled efficiently in the shared deployment.
- A separate team owns it and needs an independently versioned contract.
- Security or compliance requires a stronger process, network, or credential boundary.
- Failures in one domain repeatedly affect unrelated workloads despite process-level isolation.

Do not extract a service only because the codebase has grown. First strengthen module ownership, tests, and dependency checks.
