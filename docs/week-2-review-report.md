# SupportPilot Week 2 Review Report

- **Stage:** Document lifecycle
- **Status:** Core milestone complete and locally validated
- **Document type:** Weekly review report
- **Report date:** July 16, 2026
- **Project:** Enterprise-style AI customer support platform

## 1. Executive summary

Week 2 delivered the secure source-document and durable-work foundation required before RAG development. Authorized workspace members can upload PDF, Markdown, text, and HTML files through a streaming API, create immutable versions with SHA-256 provenance, observe processing jobs, and retry failed or dead-letter work. A separate worker process verifies stored objects and activates a version transactionally without allowing incomplete work to replace the current active version.

The implementation preserves the Week 1 defense-in-depth model. `documents`, `document_versions`, and `jobs` are workspace-owned, indexed by workspace, protected by forced PostgreSQL RLS, and covered by direct restricted-role cross-workspace tests. Object storage is accessed through an application-owned interface with a local adapter, so local paths and provider SDK objects do not enter domain or API contracts.

All consolidated local quality gates passed: 46 backend tests with 86.67% statement/branch coverage, Ruff, strict mypy, four frontend tests, ESLint, TypeScript compilation, the Vite production build, deterministic OpenAPI generation, container builds, healthy API/database/worker services, and one Chromium end-to-end workflow covering upload through completed worker processing.

## 2. Decision-gate review

The preview-plan assumptions remained valid. RAG still requires immutable source provenance, tenant-safe metadata, recoverable asynchronous work, and a portable storage boundary before parsing or embeddings are introduced. PostgreSQL handled transactional enqueue, leases, retries, and local demo throughput without adding Redis or a managed queue. The local `ObjectStore` adapter kept the deployment inexpensive while preserving a cloud-storage migration path.

One design trade-off became concrete during implementation: global job discovery needs a controlled path across workspace RLS. The worker uses a transaction-local worker context only while claiming jobs, then applies the authoritative workspace from the claimed row for every document-processing transaction. This is safe for the current application boundary and is tested for stale lease ownership, but a distinct worker database credential remains the preferred production hardening step.

## 3. Delivered scope

| Area | Delivered result | Status |
|---|---|---|
| Schema | Reversible migration `20260716_0002` for documents, immutable versions, jobs, indexes, constraints, triggers, grants, and forced RLS | Complete |
| Provenance | Version number, application object key, sanitized filename, detected media type, byte size, SHA-256, creator, timestamps, and status | Complete |
| Immutability | Database trigger blocks changes to uploaded content metadata; corrections create new versions | Complete |
| Safe activation | Database trigger verifies that the active version belongs to the same document/workspace and is already active | Complete |
| Upload security | Streaming size enforcement, workspace quota, filename sanitization, extension/type/signature checks, UTF-8/binary checks, and generated keys | Complete |
| Object storage | `ObjectStore` protocol plus local streaming write/read/stat/move/delete and stale-staging reconciliation | Complete |
| Malware boundary | Scanner interface with an explicit development/test no-op implementation; production configuration rejects no-op scanning | Complete for demo boundary |
| Idempotency | Workspace/job-type request key and content-digest uniqueness prevent duplicate jobs and document versions | Complete |
| Queue | Queued, leased, processing, retrying, failed, dead-letter, and completed states with bounded attempts and jittered backoff | Complete |
| Worker concurrency | Bounded `SKIP LOCKED` claims, lease owner/expiry, expired-lease recovery, stale-worker rejection, and controlled retry | Complete |
| Deletion | Immediate soft deletion plus a separate idempotent object-cleanup job | Complete |
| API | List, upload, add version, detail, rename, soft-delete, status history, and job retry endpoints | Complete |
| Permissions | All members view; owner/admin/agent upload and retry; owner/admin rename and delete | Complete |
| Web workflow | Workspace upload form, document status list, version/job detail, retry control, and delete control | Complete |
| API contract | Regenerated OpenAPI JSON and TypeScript definitions; repeated generation produced identical hashes | Complete |
| Containers | API and worker share the runtime image and object volume; one-shot root initializer fixes volume ownership before non-root services start | Complete |

## 4. Verification evidence

### Backend

- 46 tests passed.
- Total statement/branch coverage: 86.67%; required gate: 85%.
- Ruff lint and formatting checks passed.
- Strict mypy passed across `apps` and `packages`.
- Migration downgrade/upgrade preservation passed.
- Generic migration checks confirmed forced RLS, workspace foreign keys/indexes, least privilege, and policies on every tenant table.
- Direct runtime-role tests confirmed workspace A cannot select, update, or delete workspace B document/job data.
- Durable-job tests confirmed exclusive leases, expired-lease recovery, stale-worker rejection, dead-letter transition, and manual retry.
- Worker integration confirmed stored-object verification, active-version assignment, and completed job state.

### Frontend and contract

- ESLint passed.
- Four Vitest tests in two files passed.
- TypeScript project compilation and Vite production build passed.
- OpenAPI JSON and generated TypeScript hashes remained unchanged after regeneration.
- Chromium end-to-end test passed: registration, workspace navigation, synthetic Markdown upload, worker activation, version display, and completed job display.

### Containers and runtime

- Database, migration, storage initializer, API, worker, and web images built successfully.
- Migration and storage initializer exited with code zero.
- PostgreSQL and API reported healthy; worker remained running.
- Runtime logs recorded the synthetic document job as completed without exposing document content.
- The browser test exposed and verified the fix for named-volume ownership while keeping API and worker containers non-root.

## 5. Deviations and remaining hardening

The core milestone is complete, but the following preview/ADR hardening items are not claimed as production-ready:

| Item | Current state | Follow-up trigger |
|---|---|---|
| Dedicated worker database principal | Worker shares the restricted application credential and uses a transaction-local worker context for claims | Create a separate least-privilege credential before production or external worker deployment |
| Real malware scanning | Scanner boundary exists; development/test use an explicit no-op | Required before accepting untrusted, private, or real customer files |
| Long-job lease heartbeat | Renewal service exists, but the Week 2 verification processor completes within one lease and does not heartbeat | Integrate heartbeat before Week 3 parsing/OCR can exceed the lease duration |
| Explicit request deadline | Cancellation propagates and partial files are removed, but no application-level upload timeout is configured | Add proxy and application deadlines before public deployment |
| Injected commit/storage failure test | Cleanup paths and staging reconciliation are implemented; validation cleanup is tested | Add fault-injection coverage before adopting remote object storage |
| Concurrent duplicate-upload race test | Database uniqueness protects the race; sequential duplicate and idempotent replay are tested | Add a deterministic concurrent race harness during ingestion hardening |
| Graceful SIGTERM verification | Expired leases make interrupted work recoverable; container termination behavior was not timed and asserted | Add shutdown/lease-release integration testing before long-running processors |

The existing FastAPI/Starlette test-client deprecation warning remains. It does not affect runtime behavior or current test correctness and should be resolved during a controlled dependency update.

## 6. Security and data-use limitations

Only synthetic or public documents should be uploaded. The demo does not yet provide a production scanner, DLP, PII redaction, customer retention policies, verified backup/restore, KMS-backed encryption, rate limits, audit events, or formal compliance controls. The platform remains accurately described as production-style, not production-certified.

## 7. Week 3 handoff

Week 3 can build on a stable source contract: immutable stored versions, trusted hashes and media metadata, enforced tenant scope, visible processing state, and recoverable worker coordination. The next milestone should add parsers and citation boundaries for PDF, Markdown, text, and HTML; chunking; local embeddings; pgvector and full-text indexes; deterministic Reciprocal Rank Fusion; citation validation; and the first 50-question evaluation set.

Before Week 3 implementation, the same decision gate should compare parser libraries, chunking strategies, embedding adapters, index structures, and retrieval-fusion choices. Long-running parsing should also consume the existing lease-renewal capability rather than assuming the Week 2 verification job duration.
