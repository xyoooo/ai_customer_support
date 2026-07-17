# Week 2 threat model

## Assets

- User credentials and refresh sessions
- Workspace membership and role assignments
- Tenant-owned data and future knowledge documents
- Uploaded objects, immutable version metadata, and processing jobs
- Database and signing credentials

## Trust boundaries

- Browser to API over HTTPS in production
- API to PostgreSQL using the restricted runtime role
- CI/migration process to PostgreSQL using the migration role
- Future model and storage providers outside the platform boundary

## Principal threats and controls

| Threat | Week 1 control | Remaining work |
|---|---|---|
| Cross-tenant read/write | API membership checks, runtime-role RLS, isolation tests | Apply the same policy template to every future table |
| Role escalation | Central permission matrix, manager dependencies, self-role restrictions | Add ownership-transfer workflow with confirmation |
| Password disclosure | Argon2 hashes, constant-work unknown-user verification, no credential logging | Rate limits and breached-password checks in security milestone |
| Token theft | Short-lived access token, HTTP-only refresh cookie, stored refresh hash | Production HTTPS, CSP, and device/session management |
| Refresh replay | Rotation, row lock, family revocation, automated replay test | Alerting and user notification |
| SQL injection | SQLAlchemy parameters and typed schemas | Semgrep and adversarial endpoint fuzzing |
| Tenant context leakage | `set_config(..., true)` transaction locality and pool-reset test | Enforce context helper in future worker repositories |
| Secret leakage | Environment configuration and `.env` exclusion | Cloud secret manager during deployment |
| Cross-tenant document access | Workspace authorization, forced RLS on documents/versions/jobs, direct runtime-role denial tests | Give the worker a separate least-privilege database credential |
| Oversized or memory-exhausting upload | Streaming reads, hard per-file and workspace byte limits | Add proxy-level request timeouts and resumable uploads for large files |
| Filename/path traversal | Sanitized display names and application-generated object keys constrained to the configured root | Add managed object storage policy validation during deployment |
| Media-type spoofing | Extension, declared type, UTF-8/binary checks, and PDF signature validation | Use a mature file-identification library as formats expand |
| Malicious uploaded file | Scanner interface before activation; explicit no-op only in development/test | Production malware scanning, quarantine, DLP, and retention controls |
| Lost or duplicate background work | PostgreSQL jobs, idempotency keys, leases, bounded retries, and dead-letter state | Add worker heartbeats for long parsing/OCR jobs and evaluate an external queue at measured scale |
| Stale worker overwrites newer result | Lease-owner conditional finalization and stale-worker rejection tests | Add attempt/lease fencing tokens if job processors gain external side effects |
| Partial upload or abandoned staging object | Partial-write cleanup, failed-transaction cleanup path, and stale-staging reconciliation | Add injected database/object-store failure tests and cleanup metrics |

## Explicit limitations

The demo still does not include rate limiting, audit events, a real malware scanner, document prompt-injection defenses, PII redaction, production key rotation, or contractual retention/deletion controls. The worker currently shares the restricted application database credential and uses a transaction-local worker context; a distinct service principal is still required before production. Synthetic or public data only should be used.
