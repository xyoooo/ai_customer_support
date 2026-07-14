# SupportPilot Week 1 Development Report

**Stage:** Foundation  
**Status:** Complete and locally validated  
**Report date:** July 14, 2026  
**Project:** Enterprise-style AI customer support platform

## 1. Executive summary

Week 1 established the production-style foundation on which document ingestion, retrieval-augmented generation, human handoff, evaluation, and observability can be added without replacing the core architecture.

The delivered system is a Dockerized modular monolith with a FastAPI backend, React frontend, PostgreSQL 16/pgvector database, versioned Alembic schema, authentication, rotating sessions, workspace membership, role-based access control, and forced PostgreSQL Row Level Security (RLS). The implementation includes a generated frontend API contract, CI configuration, architecture decisions, a threat model, and automated tests at the unit, API, database, security, component, browser, and container levels.

The stage passed 35 backend tests with 95.98% statement/branch coverage against an 85% quality gate. Frontend linting, component tests, TypeScript compilation, and production bundling passed. A Playwright Chromium test also passed against the complete Docker Compose stack. Direct database tests verified that the restricted runtime role cannot perform cross-workspace `SELECT`, `INSERT`, `UPDATE`, or `DELETE` operations.

This is a sound development foundation, but it is not yet a production service. Important remaining controls include real secret management, rate limiting, email verification, password recovery, audit events, self-provisioning test infrastructure, deployment validation, and the document/RAG functionality scheduled for later stages.

## 2. Delivered scope

| Area | Deliverables | Result |
|---|---|---|
| Repository foundation | Modular `apps`, `packages`, `migrations`, `tests`, `infra`, and `docs` structure | Complete |
| Dependency management | Python 3.12 with `uv.lock`; Node 24 with `package-lock.json` | Complete |
| Local infrastructure | Docker Compose services for PostgreSQL/pgvector, migrations, API, and web | Complete |
| Backend API | FastAPI application under versioned `/api/v1` routes | Complete |
| Database | Users, workspaces, memberships, and refresh sessions | Complete |
| Schema management | Reversible Alembic foundation migration, revision `20260713_0001` | Complete |
| Authentication | Registration, login, `/me`, token refresh, and logout | Complete |
| Session security | Short-lived access JWTs, opaque refresh tokens, hashing, rotation, row locking, replay-family revocation | Complete |
| Authorization | `owner`, `admin`, `agent`, and `viewer` role model with centralized permission rules | Complete |
| Tenant isolation | Separate database roles, workspace context, RLS policies, and forced RLS | Complete |
| Workspace API | Create, list, read, rename, list members, add member, change role, and remove member | Complete |
| Frontend | Registration, login, authenticated shell, workspace dashboard, and member view | Complete |
| API contract | OpenAPI-generated TypeScript definitions consumed by frontend types | Complete |
| Quality automation | Ruff, mypy, ESLint, Vitest, pytest, coverage, Playwright, and Docker builds | Complete |
| CI | GitHub Actions jobs for backend, frontend, containers, and end-to-end tests | Configured |
| Engineering documentation | Architecture overview, three ADRs, threat model, and demo script | Complete |

## 3. Engineering considerations and rationale

### 3.1 Modular monolith

The platform uses a modular monolith instead of microservices. The API and future worker remain separate processes, but they share versioned domain packages and one database.

This approach was selected because the current workload does not justify network boundaries, distributed transactions, separate deployment pipelines, or multiple operational data stores. It preserves clear domain boundaries while keeping local development, CI, and low-cost hosting practical. Later extraction remains possible if measured scaling, ownership, or reliability requirements justify it.

### 3.2 PostgreSQL as the operational center

PostgreSQL 16 is used for relational state, authorization data, future job state, full-text search, and vector storage through pgvector. Adding pgvector at foundation time prevents a disruptive database-image change when RAG development begins.

This minimizes infrastructure and keeps tenant filters, document metadata, lexical ranking, vector ranking, and transactional activation in one consistency boundary. A separate vector database or Redis queue would add cost and failure modes before there is evidence they are required.

### 3.3 Explicit migrations

The application never creates tables at startup. Alembic is the only schema-change mechanism, and migrations run as a separate Compose service with distinct credentials.

This provides repeatability, reviewable schema history, controlled deployment ordering, and a future rollback path. It also prevents application instances from racing to modify production schemas.

### 3.4 Defense-in-depth tenant isolation

Authorization is enforced twice:

1. FastAPI dependencies authenticate the user, load membership, and enforce the required role.
2. PostgreSQL RLS independently filters tenant-owned rows.

The migration role owns schema objects, while the runtime role receives only the required table and function privileges. RLS is both enabled and forced on `workspaces` and `workspace_memberships`.

The current user and workspace are set with transaction-local PostgreSQL configuration values. Transaction locality is important because pooled connections are reused; a session-level setting could expose one tenant's context to the next request. An automated test confirms that the context is empty after transaction completion.

RLS is not treated as a replacement for application authorization. The API still applies role and business rules because RLS answers which rows are visible, not whether an owner may transfer ownership or an administrator may promote another administrator.

### 3.5 Authentication and session strategy

Passwords are hashed with Argon2 through `pwdlib`. Login performs an expensive dummy verification for an unknown email, reducing timing differences that could otherwise help enumerate accounts.

Normal API calls use 15-minute signed access JWTs. Refresh tokens are random opaque credentials delivered in HTTP-only, SameSite cookies. Only a SHA-256 hash of each refresh secret is stored. Refresh operations lock the session row, rotate the token, link the replacement, and revoke the entire family when a previously used token is replayed.

This combination keeps normal authorization stateless while retaining explicit logout, revocation, replay detection, and future session-management capabilities. The frontend keeps the access token in memory rather than persistent browser storage, reducing exposure to token theft through injected JavaScript.

### 3.6 Stable API and frontend contract

All public endpoints are under `/api/v1`. The frontend's TypeScript types are generated from FastAPI's OpenAPI document instead of being independently maintained.

This limits backend/frontend contract drift and makes future additive API development safer. The same OpenAPI document can later support contract fuzzing, SDK generation, and external integration documentation.

### 3.7 Real database testing

Database integration and security tests use PostgreSQL rather than SQLite. SQLite cannot validate PostgreSQL RLS, transaction-local settings, row locks, PostgreSQL UUID behavior, or future pgvector/full-text queries.

Tests connect with both migration and restricted runtime roles. This distinction matters because superusers and table owners can bypass ordinary RLS behavior and would produce misleading security results.

Coverage is configured for greenlet and thread concurrency so execution after SQLAlchemy async boundaries is measured accurately. Without this setting, valid async code after database `await` operations was incorrectly reported as unexecuted.

### 3.8 Reproducible containers and quality gates

Python and npm dependencies are locked. The API uses a multi-stage image, runs as a non-root user, and does not carry development dependencies into the runtime image. The web application has separate development and Nginx production targets.

CI separates backend, frontend, container, and browser checks. This gives fast failure feedback while still verifying deployable artifacts and a real browser workflow.

## 4. Test plan

### 4.1 Static and build verification

- Ruff linting and formatting for Python.
- Strict mypy analysis for application packages.
- ESLint for React/TypeScript.
- TypeScript project compilation.
- Vite production bundle.
- API and web Docker image builds, including the Nginx production target.

### 4.2 Unit testing

- Complete RBAC management matrix.
- Password hashing and verification.
- JWT creation, validation, expiration, and tampering.
- Refresh-token parsing and secret comparison.
- Production configuration validation.

### 4.3 API and integration testing

- Registration, duplicate registration, login success/failure, `/me`, refresh, and logout.
- Refresh rotation and replay-family revocation.
- Workspace creation, listing, reading, and renaming.
- Member addition, duplicate handling, role change, removal, self-management restrictions, and administrator limits.
- Health and API metadata endpoints.
- Migration downgrade-to-base and upgrade-to-head against the isolated test database.

### 4.4 Security testing

- Unauthenticated and invalid-token rejection.
- Viewer and administrator privilege-boundary checks.
- Non-enumerating cross-workspace API access.
- Direct runtime-role cross-tenant `SELECT`, `INSERT`, `UPDATE`, and `DELETE` attempts.
- Transaction-local tenant-context reset on a reused connection.

### 4.5 Frontend and browser testing

- Accessible login form component test under Vitest and Testing Library.
- Chromium acceptance flow covering registration, authenticated dashboard, RLS status, workspace navigation, and member visibility.
- CORS validation using the configured `localhost` demo origin.

### 4.6 Operational smoke testing

- PostgreSQL and API health checks.
- Migration container completion with exit code zero.
- Web HTTP 200 response.
- Confirmation that both tenant tables have `relrowsecurity=true` and `relforcerowsecurity=true`.
- Stop/start lifecycle with persistent Docker volume data.

## 5. Test outcomes

| Check | Outcome |
|---|---|
| Backend tests | 35 passed |
| Backend coverage | 95.98% |
| Required coverage gate | 85% — passed |
| Cross-tenant CRUD through runtime role | All blocked or filtered as expected |
| Ruff lint | Passed |
| Ruff formatting | Passed |
| Strict mypy | Passed |
| ESLint | Passed |
| Vitest component tests | Passed |
| TypeScript compilation | Passed |
| Vite production build | Passed |
| Playwright Chromium E2E | 1 passed |
| API runtime image | Built successfully |
| Web development image | Built successfully |
| Web Nginx production image | Built successfully |
| Database and API health | Healthy during verification |
| Migration state | `20260713_0001` |

One dependency-level warning remains: the installed FastAPI test client reports that its current `httpx` compatibility path is deprecated in favor of the emerging `httpx2` integration. This does not affect runtime behavior or current test correctness, but it should be addressed during routine dependency maintenance once the replacement path is stable.

## 6. Known limitations

- The existing `.git` directory is empty, so the folder is not yet a functional Git repository and the configured GitHub Actions workflow has not run on GitHub.
- Local database passwords and the development JWT secret are intentionally demo values. They are not suitable for deployment.
- Registration has no email verification, invitation token, password reset, OAuth, or MFA workflow.
- A user must register before being added to another workspace.
- Ownership transfer is intentionally unavailable; this avoids accidentally leaving a workspace without an owner.
- Rate limiting, lockout policy, CSRF tokens beyond SameSite protection, audit events, and session-management UI are not implemented yet.
- The frontend refreshes a session on initial load but does not yet automatically refresh and retry a request when an access token expires during an active session.
- Integration tests use a dedicated Compose test database. The Testcontainers dependency is present, but tests do not yet provision an entirely isolated database automatically.
- The UI is an administration shell, not the final customer chat or support-agent experience.
- External Google Fonts should be self-hosted or removed before adopting a strict Content Security Policy.
- Production hosting, secret-manager integration, backups, restore testing, telemetry export, and rollback automation remain unverified.
- Document ingestion, object storage, job processing, embeddings, retrieval, citations, model calls, evaluation, and human handoff have not started.

## 7. Recommended future improvements

### Priority 0: Repository and CI activation

1. Initialize Git, create the initial commit, and push to a remote repository.
2. Run all GitHub Actions jobs and resolve any runner-specific differences.
3. Add branch protection requiring backend, frontend, container, and E2E checks.

### Priority 1: Foundation hardening

1. Add automatic frontend refresh-and-retry with single-flight refresh protection.
2. Add email verification, password reset, invitation tokens, and ownership transfer.
3. Add IP/user/workspace rate limits and login abuse controls.
4. Add append-only audit events for authentication, membership, role, and workspace changes.
5. Move integration tests to disposable Testcontainers databases for parallel and developer-independent execution.
6. Replace demo secrets with generated environment values locally and a secret manager in hosted environments.
7. Add CSP, HSTS in production, CSRF review, dependency scanning, and container scanning.
8. Resolve the FastAPI test-client deprecation during a controlled dependency upgrade.

### Priority 2: Week 2 document lifecycle

1. Add `documents`, `document_versions`, and `jobs` tables with `workspace_id` and forced RLS from the first migration that introduces them.
2. Introduce an `ObjectStore` interface and a local object-storage adapter without coupling domain services to a vendor SDK.
3. Implement content hashing, duplicate detection, immutable versions, and transactional activation.
4. Implement the PostgreSQL durable queue using leases, `FOR UPDATE SKIP LOCKED`, idempotency keys, bounded retries, and dead-letter state.
5. Add a worker process from the existing shared image and verify graceful shutdown and lease recovery.
6. Add file-size/type validation and a malware-scanning integration point before parsing.

### Priority 3: Week 3 RAG baseline

1. Add parsing and citation-boundary preservation for Markdown, text, HTML, and PDF.
2. Add local embedding and chat-provider interfaces before vendor implementations.
3. Add pgvector columns and HNSW indexes through Alembic.
4. Implement workspace-filtered lexical and vector retrieval followed by deterministic Reciprocal Rank Fusion.
5. Validate citation IDs against retrieved chunks and abstain when evidence is weak.
6. Create the first labeled retrieval evaluation dataset and regression report.

### Priority 4: Operational maturity

1. Add structured audit logging, OpenTelemetry, request metrics, and cost accounting.
2. Test backup/restore, migration rollback, container shutdown, and session revocation under failure.
3. Add preview deployments and automated migration checks before production rollout.
4. Run documented load tests only after representative chat and retrieval paths exist.

## 8. Stage conclusion

Week 1 achieved its primary purpose: the project now has a secure, testable, and extensible application foundation rather than a disposable chatbot prototype. The most important design choices—modular boundaries, explicit migrations, dual-layer tenant isolation, rotating sessions, generated contracts, real-PostgreSQL testing, and reproducible containers—are compatible with the planned document, RAG, evaluation, and operational stages.

The next development stage should extend these conventions rather than introduce parallel infrastructure. In particular, every new tenant-owned table should use the existing workspace/RLS pattern, every external dependency should sit behind a small provider interface, and each document/job state transition should be exercised against real PostgreSQL behavior.
