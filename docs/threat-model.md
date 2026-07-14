# Week 1 threat model

## Assets

- User credentials and refresh sessions
- Workspace membership and role assignments
- Tenant-owned data and future knowledge documents
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

## Explicit limitations

Week 1 does not yet include rate limiting, audit events, malware scanning, document prompt-injection defenses, PII redaction, or production key rotation. Synthetic data only should be used in the demo.

