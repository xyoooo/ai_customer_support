# SupportPilot Week 2 Preview Plan

- **Stage:** Document lifecycle
- **Status:** Implemented and reviewed; see the Week 2 review report
- **Document type:** Weekly preview plan
- **Planning date:** July 16, 2026
- **Execution window:** July 16-22, 2026
- **Project:** Enterprise-style AI customer support platform

## 1. Week 1 recap

Week 1 is complete and locally validated. It delivered the modular-monolith foundation: FastAPI and React applications, PostgreSQL 16 with pgvector, explicit Alembic migrations, registration and rotating sessions, workspace membership and RBAC, and forced PostgreSQL Row Level Security (RLS).

The evidence reported at the end of the week was strong: 35 backend tests passed with 95.98% coverage against an 85% gate; frontend linting, component tests, TypeScript compilation, and the production build passed; the Docker Compose browser flow passed; and direct database tests blocked cross-workspace reads and writes through the restricted runtime role.

The repository is now initialized locally on `main` and tracks `origin/main`. The latest remote CI result and branch-protection settings still need confirmation. Broader foundation improvements such as email verification, password reset, rate limiting, production secret management, audit events, and automatic frontend token refresh remain important, but they are not Week 2 blockers unless they directly affect the document lifecycle.

## 2. Objective for this week

Deliver the secure, tenant-isolated document lifecycle and durable asynchronous job foundation that Week 3 can extend with parsing, chunking, embeddings, and retrieval.

By the end of the week, an authorized workspace member should be able to upload a supported file without loading it fully into API memory, create an immutable document version, observe its processing job, and safely retry a failed job. The worker should claim jobs with leases, recover expired work, and complete or dead-letter jobs without allowing stale workers or another workspace to alter the result.

## 3. Why this implementation is needed

The RAG system planned for Week 3 needs a trustworthy source-of-record before it can parse, embed, retrieve, or cite anything. If uploaded content is mutable, tenant isolation is incomplete, or background work can be lost or duplicated, later retrieval quality cannot be trusted even when the model appears to answer correctly.

This milestone therefore solves five foundation problems before AI processing begins:

1. **Provenance:** immutable versions and checksums establish exactly which content produced a chunk, citation, or answer.
2. **Tenant safety:** application permissions and forced RLS prevent one workspace from listing, processing, or retrieving another workspace's documents.
3. **Failure recovery:** durable jobs survive API or worker restarts and make retries, leases, and dead-letter cases visible instead of hiding failures in process memory.
4. **Provider portability:** an application-owned storage interface prevents the domain model from depending on local paths or one cloud vendor's SDK.
5. **Operational evidence:** explicit states, bounded errors, and correlation identifiers make the lifecycle testable, observable, and credible as a production-style portfolio system.

Deferring this work and building parsing or chat directly on local files would be faster for a prototype, but it would create a second implementation that must later be replaced to support isolation, versioning, recovery, and citations.

## 4. Available choices and evaluation

### 4.1 Document representation

| Choice | Advantages | Limitations | Decision |
|---|---|---|---|
| One mutable row per document | Smallest schema and simplest update path | Weak provenance; updates can invalidate citations and overwrite a known-good version | Rejected |
| Logical document with immutable versions | Stable provenance, safe activation, history, rollback path, and duplicate detection | More schema and lifecycle rules | Selected |
| Content-addressed global blob catalog | Maximum deduplication across documents and workspaces | Adds cross-tenant reference counting, deletion, privacy, and authorization complexity | Defer until storage measurements justify it |

### 4.2 Object storage

| Choice | Advantages | Limitations | Decision |
|---|---|---|---|
| Store file bytes in PostgreSQL | Transactionally convenient and easy to back up as one system | Database growth, expensive large-object I/O, and poor separation between metadata and file content | Rejected for normal documents |
| Use a local filesystem directly from domain code | Fastest local implementation | Leaks paths into the domain and makes cloud migration invasive | Rejected |
| Use an `ObjectStore` interface with a local adapter | Zero-cost local development, streaming support, and a stable migration path to cloud storage | Requires an interface and staging cleanup | Selected |
| Adopt S3, GCS, Supabase Storage, or MinIO now | Production-like object semantics and possible signed uploads | Adds credentials, services, cost, and vendor-specific failure modes before they are needed | Deferred |

### 4.3 Upload path

| Choice | Advantages | Limitations | Decision |
|---|---|---|---|
| Read the complete upload into API memory | Very simple handler | Unsafe memory use and poor behavior for larger files | Rejected |
| Stream through the API | Central authorization, validation, hashing, and size enforcement; simple local demo | API carries file traffic and must clean up staging failures | Selected for Week 2 |
| Browser uploads directly with a signed URL | Efficient for large files and reduces API bandwidth | Requires managed object storage, finalization callbacks, expiry handling, and more complex threat controls | Future improvement |

### 4.4 Background execution

| Choice | Advantages | Limitations | Decision |
|---|---|---|---|
| FastAPI background tasks or an in-memory queue | Minimal code and infrastructure | Work is lost on restart; no durable lease, retry, or multi-worker coordination | Rejected |
| PostgreSQL durable queue | Reuses the existing database, supports transactional enqueue, leases, RLS, and `SKIP LOCKED`, and costs nothing extra | Requires careful claim/retry logic and is not intended for unlimited throughput | Selected |
| Redis with Celery/RQ | Mature worker ecosystem and high queue throughput | Adds another stateful service, delivery semantics, credentials, and operational cost | Deferred |
| Managed queue such as SQS, Pub/Sub, or Cloud Tasks | Strong managed durability and scaling | Cloud coupling, local-development complexity, and non-atomic database/queue coordination without an outbox | Deferred |

### 4.5 Process and deployment boundary

| Choice | Advantages | Limitations | Decision |
|---|---|---|---|
| Run processing inside API requests | Simple execution path | Long request latency, cancellation risk, and no independent retry or scaling | Rejected |
| Separate API and worker processes from the same code and image | Failure and scaling separation while preserving modular-monolith simplicity | Requires explicit worker lifecycle and service-principal permissions | Selected |
| Independent ingestion microservice | Maximum deployment independence | Distributed contracts and operations are not justified by the current workload | Deferred |

### 4.6 Upload malware control

| Choice | Advantages | Limitations | Decision |
|---|---|---|---|
| No scanning boundary | Least work | Makes unsafe parsing easy to introduce and hides a production requirement | Rejected |
| Mandatory local scanner in every environment | Stronger default protection | Adds a heavy service and signature-update burden to local development and CI | Not selected for Week 2 |
| Scanner interface with an explicit development/test no-op | Establishes the security boundary now and keeps tests deterministic | Demo remains unsuitable for untrusted or sensitive uploads | Selected, with synthetic/public data only |
| Managed malware or DLP service | Production-grade scanning and policy controls | Cost, credentials, latency, and provider coupling | Future production option |

## 5. Final engineering decision

Week 2 will implement logical documents with immutable versions, streaming API uploads, an application-owned `ObjectStore` interface backed by local storage, and a PostgreSQL durable queue processed by a separate worker from the shared application image. Every tenant-owned record will use the existing application-authorization and forced-RLS model. Upload scanning will be represented by an interface, with a no-op implementation allowed only through an explicit development/test setting.

This combination is the best fit for the current stage because it provides the correctness properties needed by later RAG work without introducing another paid or stateful service. It also produces strong engineering evidence: transactional boundaries, idempotency, concurrency control, tenant isolation, safe failure recovery, and portable provider interfaces.

The accepted trade-offs are that the API carries upload bandwidth, local storage is suitable only for a single demo environment, PostgreSQL queue throughput is finite, and untrusted files cannot be accepted until a real scanner and retention controls are deployed. These limitations are explicit and measurable rather than hidden behind a prototype interface.

## 6. Potential future improvements and triggers

| Improvement | Introduce when |
|---|---|
| S3/GCS/Supabase `ObjectStore` adapter | The application is deployed across replaceable instances or needs durable shared storage. |
| Direct signed and resumable uploads | File sizes, upload duration, or API bandwidth make proxying through FastAPI a measured bottleneck. |
| Managed malware scanning, quarantine, and DLP | The platform accepts untrusted, private, or regulated content. |
| Redis or a managed queue | Measured job throughput, scheduling latency, database contention, or independent worker scaling exceeds the PostgreSQL queue's operating envelope. |
| Transactional outbox for an external queue | Database changes and queue publication must remain reliable across separate systems. |
| Global content-addressed deduplication | Storage measurements show meaningful duplication and cross-tenant privacy/deletion semantics are fully designed. |
| Multipart uploads and resumable staging cleanup | Large or unreliable-network uploads become a supported use case. |
| Object encryption with managed KMS and key rotation | Real customer content or production security requirements enter scope. |
| Retention policies, legal hold, and verified physical deletion | The product moves beyond synthetic demo data or gains contractual data-lifecycle requirements. |
| Autoscaled standalone ingestion service | Worker deployment cadence, ownership, or resource usage materially diverges from the API. |

Week 3 will make the first planned extension by adding parsing, citation boundaries, chunks, embeddings, and retrieval on top of these stable document and job contracts.

## 7. Planned outcomes

### 7.1 Document and version data model

- Add tenant-owned `documents`, `document_versions`, and `jobs` tables through a reversible Alembic migration.
- Apply `workspace_id`, workspace-first indexes, application authorization, and forced RLS to every new tenant-owned table.
- Represent a logical document separately from its immutable uploaded versions.
- Enforce monotonically increasing version numbers and uniqueness for `(document_id, version_number)` and `(workspace_id, document_id, sha256)`.
- Support document rename, soft deletion, version history, processing status, and a nullable active-version pointer.
- Permit activation only through a worker transaction after the currently required processing checks succeed; failed or partial work must never replace the active version.

### 7.2 Portable object storage and secure upload

- Define a small `ObjectStore` interface for streaming write/read, metadata lookup, deletion, and optional temporary download authorization.
- Implement a local filesystem adapter rooted in a configured data directory; keep local paths and vendor response types out of domain models and database rows.
- Stream uploads through the API while incrementally enforcing the byte limit and calculating SHA-256.
- Validate the declared type, extension, and detected file signature for the supported Week 2 file set.
- Sanitize display filenames and generate all object keys inside the application.
- Add a malware-scanning interface with an explicit development/test no-op mode; continue to treat all demo content as synthetic or public.
- Use staging keys and best-effort cleanup when the database transaction fails after object storage succeeds.

### 7.3 Durable PostgreSQL job queue and worker

- Implement the accepted job states: `queued`, `leased`, `processing`, `retrying`, `failed`, `dead_letter`, and `completed`.
- Enforce a workspace-scoped idempotency key per job type.
- Claim bounded batches using `FOR UPDATE SKIP LOCKED` in short transactions, then process outside the claim transaction.
- Require the current lease owner for renewals and finalization so stale workers cannot overwrite newer results.
- Add capped exponential backoff with jitter, maximum attempts, safe bounded error metadata, and controlled manual retry.
- Reclaim expired leases and support graceful shutdown that stops new claims before the worker exits.
- Set workspace context from the authoritative job row in every worker transaction rather than trusting the payload alone.

### 7.4 API and user-visible status

- Add document endpoints to create a logical document, upload a new version, list documents, view version/job status, rename, soft-delete, and retry eligible failed jobs.
- Apply the accepted permissions: all active members may view; `owner`, `admin`, and `agent` may upload or retry; only `owner` and `admin` may rename or delete.
- Add a focused Documents view to the existing web shell with upload progress, document/version status, failure summary, and retry controls.
- Regenerate the OpenAPI TypeScript contract and keep frontend types sourced from it.

### 7.5 Verification and documentation

- Test upload size, type, signature, filename, checksum, duplicate, and idempotency behavior.
- Test cleanup when object writing or the database commit fails, including abandoned staging-object reconciliation.
- Test forced RLS and direct cross-workspace denial for every new tenant table.
- Test concurrent worker claims, expired-lease recovery, stale-worker rejection, retries, dead-letter transition, and repeat processing.
- Test that incomplete versions cannot become active and that graceful shutdown leaves work recoverable.
- Keep raw document content, credentials, tokens, signed URLs, and provider payloads out of general logs.
- Update the architecture/demo documentation and finish the week with a Week 2 review report against this plan.

## 8. Execution sequence

### Phase 1 - Schema and domain contracts

Implement the enums, schemas, models, migration, permissions, RLS policies, and lifecycle invariants first. Prove migration upgrade/downgrade and cross-workspace isolation before building API behavior on top.

### Phase 2 - Storage and upload transaction

Add the `ObjectStore` boundary and local adapter, then implement streaming validation, hashing, staging, idempotent database creation, and cleanup. Cover failure paths before adding the UI.

### Phase 3 - Queue and worker reliability

Implement claim, lease, processing, retry, dead-letter, reconciliation, and shutdown behavior. Exercise competing workers and expired leases against real PostgreSQL.

### Phase 4 - API and web workflow

Expose document/version/job state through the versioned API, regenerate the frontend contract, and add the smallest usable document-management workflow to the web shell.

### Phase 5 - Hardening and weekly review

Run the complete backend, frontend, browser, migration, security, and container checks. Confirm remote CI if available, update the demo script, and record delivered, partial, and deferred items in the Week 2 review report.

## 9. Definition of done

Week 2 is complete when all of the following are true:

1. The new migration upgrades and downgrades cleanly, and all new tenant tables have verified forced RLS.
2. Authorized users can upload supported files as immutable versions through a streaming, size-limited, checksum-producing path.
3. Duplicate and retried requests are idempotent and do not create duplicate versions or jobs.
4. Object-storage and database failures do not leave a user-visible partial version; abandoned staging data has a reconciliation path.
5. Two workers cannot own the same valid lease, stale workers cannot finalize work, and expired work is recoverable.
6. Retry limits and dead-letter behavior are deterministic and visible through the API and web UI.
7. Failed or incomplete versions never replace the active version.
8. Backend, frontend, migration, security, browser, and container checks pass, with backend coverage remaining at or above 85%.
9. Logs contain identifiers and safe error summaries but no raw document content or secrets.
10. The Week 2 review report records actual results, evidence, deviations, remaining risks, and the Week 3 handoff.

## 10. Non-goals for Week 2

- PDF/HTML parsing, OCR, text normalization, chunking, or citation-boundary extraction.
- Embeddings, pgvector indexes for chunks, full-text retrieval, Reciprocal Rank Fusion, or reranking.
- LLM calls, grounded chat, citation validation, evaluation datasets, or human handoff.
- Production cloud object-storage integration or a production malware-scanning vendor.
- Completing every Week 1 hardening item. Only work that blocks or materially protects the document lifecycle enters this week's scope.

## 11. Main risks and controls

| Risk | Control this week |
|---|---|
| Upload consumes excessive memory or disk | Stream with a hard byte limit, timeouts, cancellation handling, staging cleanup, and configured workspace limits. |
| Filename or media-type spoofing | Generate object keys, sanitize display names, and require extension/type/signature agreement. |
| Cross-workspace document access | Apply API authorization plus forced RLS and direct restricted-role tests to every new table. |
| Duplicate versions during retries or races | Use incremental SHA-256, database uniqueness, request/job idempotency keys, and race tests. |
| Two workers process or finalize the same job | Use short claim transactions, lease ownership conditions, and stale-worker rejection tests. |
| Partial processing replaces good content | Activate only in a successful worker transaction after required outputs are verified. |
| Week 2 expands into Week 3 RAG work | Keep the worker processor boundary extensible, but defer parsing, chunks, embeddings, and retrieval. |
| Foundation backlog displaces the milestone | Time-box CI confirmation and fix only foundation issues that block or materially weaken Week 2. |

## 12. Expected Week 3 handoff

Week 3 should begin with a stable source-document contract: immutable stored versions, trustworthy checksums and metadata, tenant-safe access, visible processing state, and a worker that can reliably execute idempotent steps. Week 3 can then add parsers, chunks, embeddings, lexical/vector retrieval, citations, and the first 50-question evaluation set without redesigning upload, storage, or job coordination.
