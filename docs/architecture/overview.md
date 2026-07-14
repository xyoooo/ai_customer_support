# Architecture overview

SupportPilot is a modular monolith. The API and future worker are separate processes that share domain packages and one PostgreSQL database. Every public HTTP contract is versioned under `/api/v1`.

```mermaid
flowchart LR
    Browser["React web app"] --> API["FastAPI /api/v1"]
    API --> Auth["Authentication and RBAC"]
    API --> Domain["Workspace domain"]
    Auth --> DB[("PostgreSQL 16 + pgvector")]
    Domain --> DB
    Worker["Future indexing worker"] --> Domain
    Worker --> DB
```

The database uses separate migration and application roles. Tenant context is set with transaction-local PostgreSQL settings, and RLS policies constrain tenant-owned tables. Future document, job, conversation, and evaluation tables must use the same `workspace_id` and RLS convention.

