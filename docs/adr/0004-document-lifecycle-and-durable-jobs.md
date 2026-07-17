# ADR 0004: Document lifecycle, portable object storage, and durable jobs

- Status: accepted
- Date: 2026-07-14
- Last reviewed: 2026-07-17

## Context

Week 2 adds uploads, immutable document versions, object storage, asynchronous processing, retries, and a worker. These features cross the HTTP, database, storage, security, and operational boundaries. Defining those boundaries before choosing an object-storage vendor or writing a worker prevents the domain model from depending on local filesystem paths, provider SDK types, or process-local task state.

The system remains a modular monolith. PostgreSQL is the durable coordination system, and the API and worker are separate processes built from the same code and image.

## Decision drivers

- Preserve document provenance so future chunks, citations, and model runs can identify the exact source version.
- Enforce tenant isolation at both the application and database layers.
- Survive API and worker restarts without losing or silently duplicating work.
- Keep the light demo runnable without another paid or stateful service.
- Avoid leaking local filesystem or cloud-provider details into domain and API contracts.
- Make concurrency, retries, failure states, and cleanup behavior observable and testable.

## Options comparison

### Document lifecycle

| Option | Advantages | Limitations |
|---|---|---|
| Logical document with immutable versions | Preserves provenance; supports safe activation, history, duplicate detection, and rollback; citations can name an exact version | Adds version and activation state; storage grows until retention cleanup runs |
| Single mutable document row | Smallest schema; replacement is simple | Overwrites provenance; citations can silently refer to changed content; a failed replacement can displace known-good content |
| Global content-addressed blobs shared across workspaces | Maximum storage deduplication; one physical copy per checksum | Cross-tenant reference counting, deletion, authorization, and privacy rules are complex; identical bytes can reveal information across tenants if designed poorly |

### Object storage

| Option | Advantages | Limitations |
|---|---|---|
| Application-owned `ObjectStore` interface with local adapter | Free and simple locally; domain contracts stay portable; a managed adapter can replace it later | Local disk is not shared across instances and needs explicit backup and cleanup; not suitable for replaceable production instances |
| Managed object storage used through the same interface | Durable, scalable, shared across instances; supports lifecycle and signed delivery features | Provider configuration, credentials, network failures, and possible cost; unnecessary for a single local instance |
| Store document bytes in PostgreSQL | Transactional with metadata; one backup system | Large binary I/O and growth burden the relational database; database backups and replication become heavier |
| Use filesystem paths directly in domain code | Minimal abstraction and quick prototype | Couples business logic and persisted records to one host layout; unsafe migration to cloud storage; paths can leak implementation details |

### Upload transport

| Option | Advantages | Limitations |
|---|---|---|
| Stream through the API | Centralizes authorization, byte limits, signature validation, checksums, and staging cleanup; works with local storage | API carries upload bandwidth; requires streaming timeout and cancellation handling |
| Buffer the whole file in API memory | Easiest handler implementation | Memory use grows with file size and concurrent uploads; weak failure behavior for large files |
| Direct signed upload to managed storage | Removes most upload bandwidth from the API; supports multipart and resumable uploads | Requires shared managed storage, a finalization protocol, abandoned-upload cleanup, and a larger authorization threat surface |

### Job execution

| Option | Advantages | Limitations |
|---|---|---|
| PostgreSQL job table with leases | Enqueue can share the document transaction; durable across process restarts; no additional service; SQL supports inspection and recovery | Polling adds database load; lease and retry logic must be implemented; not optimized for very high queue throughput |
| In-process background task | Almost no infrastructure or queue code | Work can disappear on API restart; no safe multi-worker coordination, durable retries, or dead-letter inspection |
| Redis with Celery or a similar worker framework | Mature task routing, scheduling, retries, and worker ecosystem | Adds Redis and framework operations; database changes and job publication need consistency handling |
| Managed message queue | Strong durability and independent scaling; managed delivery and dead-letter features | Adds cloud dependency and cost; local parity is harder; transactional outbox is needed to coordinate database state with publication |

### Deployment boundary

| Option | Advantages | Limitations |
|---|---|---|
| Separate API and worker processes from the same image | Processing survives request completion; processes can restart and scale independently; code and contracts remain shared | API and worker normally share a release; worker permissions need deliberate separation |
| Process documents inside the API request | Simple synchronous control flow; immediate result | Request latency, cancellation, timeouts, and resource use become coupled to long processing |
| Independent ingestion microservice | Independent deployment, ownership, scaling, and credentials | Adds network contracts, distributed failure handling, and deployment coordination before the workload or team requires them |

## Decision

### Document and version model

`documents` represents a logical document in a workspace. It owns the display name, lifecycle metadata, and nullable pointer to the active version.

`document_versions` represents immutable uploaded content. Each row includes `workspace_id`, `document_id`, a monotonically increasing version number, application-generated object key, original display filename, detected media type, byte size, SHA-256 digest, processing status, creator, and timestamps.

The following invariants apply:

- Every document-owned row has a required `workspace_id`, a foreign key to `workspaces`, an index beginning with `workspace_id`, and forced PostgreSQL RLS.
- Content metadata on a version is immutable after upload finalization. A correction creates another version.
- `(document_id, version_number)` is unique.
- `(workspace_id, document_id, sha256)` is unique so the same bytes cannot create duplicate versions of one logical document. Identical content may still belong to different logical documents.
- A version becomes active only in the same database transaction that verifies all required processing outputs are complete.
- A failed or partially processed version never replaces the current active version.
- Deletion is initially soft deletion of the logical document. Physical object removal is a separate idempotent cleanup job so database and object-storage failures cannot create a partially deleted user-visible record.

### Upload transaction boundary

The initial demo streams uploads through the API. The service validates the caller and metadata, enforces a configured byte limit while streaming, calculates SHA-256 incrementally, validates the detected file signature against an allowlist, and writes to an application-generated staging key.

After the object write succeeds, one database transaction creates or finds the document version and enqueues its processing job using the request idempotency key. If that transaction fails, the API attempts best-effort removal of the staged object. A reconciliation job removes abandoned staging objects after a retention window.

The API never loads an entire upload into memory, uses a supplied filename as an object path, or writes document content to application logs.

### Object storage boundary

Domain and application services depend on a small `ObjectStore` interface, not a vendor SDK. The interface supports streaming write, streaming read, metadata lookup, deletion, and optional time-limited download authorization. It accepts and returns application-owned values such as object keys, byte counts, media types, and checksums.

The database stores immutable object keys, never local absolute paths, bucket URLs, signed URLs, or provider response objects. Signed URLs are short-lived delivery artifacts and are not persisted.

Week 2 will provide a local filesystem adapter rooted in a configured data directory. A future S3, Google Cloud Storage, or Supabase adapter can implement the same interface without changing document rows, API schemas, or processing services.

### Upload security policy

Upload controls are enforced before parsing:

- configurable per-file and per-workspace limits;
- declared type, extension, and file-signature agreement;
- sanitized display filenames and application-generated keys;
- incremental checksum and duplicate detection;
- explicit request timeout and cancellation handling;
- a malware-scanning interface before parsing;
- no-op scanning allowed only through an explicit development/test setting;
- synthetic content only until a production scanner, secret management, and retention policy exist.

### Durable job model

`jobs` is a tenant-owned PostgreSQL table. A job contains `workspace_id`, job type, payload schema version, identifiers rather than document content, state, idempotency key, availability time, lease owner and expiry, attempt counters, maximum attempts, bounded error metadata, and timestamps.

The externally visible states are:

`queued -> leased -> processing -> completed`

Recoverable failures move `leased` or `processing` to `retrying`, then back to `leased` when `available_at` is reached. Exhausted or explicitly non-retryable failures move to `failed` or `dead_letter`. An authorized retry creates a controlled transition from `failed` or `dead_letter` to `retrying`; it does not create an unrelated duplicate job.

Queue behavior follows these rules:

- `(workspace_id, job_type, idempotency_key)` is unique.
- Workers claim bounded batches with `FOR UPDATE SKIP LOCKED` in a short transaction.
- Processing happens outside the claim transaction.
- Lease renewal and finalization are conditional on both job ID and current lease owner.
- An expired lease makes incomplete work reclaimable after reconciliation.
- Retries use capped exponential backoff with jitter and a configured maximum attempt count.
- Payloads are versioned and contain stable entity IDs, not credentials, raw upload bytes, or provider objects.
- Processing steps are idempotent; a repeated attempt either reuses the same derived records or replaces them transactionally.
- Shutdown stops new claims, allows a bounded grace period, then releases or lets leases expire safely.

Every worker database transaction sets the workspace context using the workspace loaded from the authoritative job row. The worker does not trust a workspace identifier supplied only inside the job payload.

The Week 2 local implementation uses a transaction-local `app.current_worker_id` only for cross-workspace queue discovery, then returns to workspace-scoped RLS for processing. It currently shares the restricted application database credential. This is an explicit demo-stage deviation from a distinct service-principal credential and must be hardened before production or independent worker deployment.

### Permissions

- Any active workspace member may list documents and view versions and processing status.
- `owner`, `admin`, and `agent` may upload a document or new version and retry a failed processing job.
- Only `owner` and `admin` may rename or delete documents.
- Activation is performed by the worker after successful processing, not directly by a browser request.
- A production worker identity is a service principal with only the table and object operations its job types require; it is not represented as a workspace member. The Week 2 local credential deviation is recorded above and in the review report.

### Observability contract

API and worker logs bind `request_id`, `workspace_id`, `document_id`, `document_version_id`, and `job_id` when available. Error fields contain bounded codes and safe summaries. Raw document text, object credentials, cookies, tokens, signed URLs, and full provider payloads are excluded from general logs.

## Why this suits the current stage

Week 2 needs durable and testable document processing, but the demo runs on one development host and targets a small hosted workload. Immutable versions and durable PostgreSQL jobs protect correctness now. The `ObjectStore` boundary and separate worker process preserve migration paths without requiring managed storage, Redis, or another deployed service before their value is measurable.

The selected combination also keeps the most failure-prone transition, creating a document version and enqueueing its work, inside one database transaction. The additional lease, cleanup, and reconciliation logic is visible and testable, which is preferable at this stage to hiding those responsibilities behind process-local tasks.

## Required verification

The implementation is not complete until automated tests cover:

- upload size, type, signature, filename, checksum, and idempotency behavior;
- object-write and database-commit failure cleanup;
- duplicate upload races;
- every new tenant table's forced RLS and direct cross-workspace denial;
- two workers never owning the same valid lease concurrently;
- expired lease recovery and stale-worker finalization rejection;
- bounded retries and dead-letter transition;
- repeated processing without duplicate derived records;
- incomplete versions never becoming active;
- graceful worker shutdown and lease recovery.

## Consequences

### Advantages accepted

- The demo can use simple local storage and a PostgreSQL worker while preserving migration paths to managed storage and an external queue.
- Immutable versions keep failed replacements from displacing known-good content.
- Durable, inspectable jobs survive API and worker restarts.
- Provider details remain behind application-owned interfaces.

### Limitations accepted

- The application owns staging cleanup, reconciliation, lease, retry, and dead-letter behavior.
- Local object storage is tied to one host and is not a production high-availability design.
- PostgreSQL polling consumes database capacity and requires explicit queue monitoring.
- Redis, a message broker, direct browser-to-cloud uploads, and provider-specific storage features remain unavailable until measured throughput, upload size, or hosting constraints justify them.

## When to reconsider

- Add a managed `ObjectStore` adapter when instances become replaceable or storage must be shared across deployments.
- Add signed, multipart, or resumable uploads when file sizes or API bandwidth become measured constraints.
- Add production malware scanning, quarantine, DLP, retention, and KMS-backed encryption before accepting untrusted or real customer content.
- Replace or supplement the PostgreSQL queue when queue latency, throughput, database contention, or worker scaling is outside the measured operating target.
- Use a transactional outbox if job publication moves to an external queue and must remain consistent with database changes.
- Extract an ingestion service only when its deployment cadence, ownership, reliability target, or resource profile materially diverges from the API.
- Consider global content-addressed deduplication only after storage measurements justify the added cross-tenant deletion and privacy design.
