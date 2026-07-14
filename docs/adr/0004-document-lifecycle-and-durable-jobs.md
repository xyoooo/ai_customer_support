# ADR 0004: Document lifecycle, portable object storage, and durable jobs

- Status: accepted
- Date: 2026-07-14

## Context

Week 2 adds uploads, immutable document versions, object storage, asynchronous processing, retries, and a worker. These features cross the HTTP, database, storage, security, and operational boundaries. Defining those boundaries before choosing an object-storage vendor or writing a worker prevents the domain model from depending on local filesystem paths, provider SDK types, or process-local task state.

The system remains a modular monolith. PostgreSQL is the durable coordination system, and the API and worker are separate processes built from the same code and image.

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

### Permissions

- Any active workspace member may list documents and view versions and processing status.
- `owner`, `admin`, and `agent` may upload a document or new version and retry a failed processing job.
- Only `owner` and `admin` may rename or delete documents.
- Activation is performed by the worker after successful processing, not directly by a browser request.
- A worker identity is a service principal with only the table and object operations its job types require; it is not represented as a workspace member.

### Observability contract

API and worker logs bind `request_id`, `workspace_id`, `document_id`, `document_version_id`, and `job_id` when available. Error fields contain bounded codes and safe summaries. Raw document text, object credentials, cookies, tokens, signed URLs, and full provider payloads are excluded from general logs.

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

The API can use simple local storage and a PostgreSQL worker during the demo while preserving a migration path to managed object storage and an external queue. The design adds explicit staging cleanup, reconciliation, and lease tests, but those costs are preferable to hidden in-memory jobs or vendor-specific data leaking into domain contracts.

Redis, a message broker, direct browser-to-cloud uploads, and provider-specific storage features remain optional. They will be introduced only when measured throughput, upload size, or hosting constraints justify them.
