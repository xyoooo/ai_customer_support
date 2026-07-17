# ADR 0002: Enforce tenant isolation in the API and PostgreSQL

- Status: accepted
- Date: 2026-07-13
- Last reviewed: 2026-07-17

## Context

SupportPilot stores documents, jobs, conversations, and evaluation data for multiple workspaces in shared infrastructure. A cross-workspace read or write is a critical security failure.

An application-only convention such as adding `WHERE workspace_id = ...` to every query is easy to omit. The design therefore needs both an application authorization decision and an independent database enforcement boundary.

## Decision drivers

- Deny cross-workspace access even when an ORM filter is missing.
- Keep authorization rules explicit at API and database boundaries.
- Support shared-schema operation at low cost.
- Make isolation directly testable with the real runtime database role.
- Preserve efficient workspace-filtered joins and retrieval.

## Options comparison

| Option | Advantages | Limitations |
|---|---|---|
| Shared schema with application checks and PostgreSQL Row-Level Security (RLS) | Defense in depth; one schema and migration path; efficient shared operations; policies apply to normal reads and writes | Requires transaction-scoped tenant context; policies add testing and debugging complexity; owners and privileged roles require careful handling |
| Shared schema with application filters only | Simple database configuration; familiar ORM patterns | One missed filter can leak data; bulk queries and new code paths are risky; no independent database enforcement |
| Schema per tenant | Stronger namespace separation; per-tenant backup or migration is possible | Schema and migration count grows with tenants; cross-tenant operations and connection management become harder; operational overhead is excessive for the demo |
| Database per tenant | Strongest infrastructure separation; independent backup, encryption, and scaling | Highest cost and operational burden; connection and migration fan-out; inefficient for many small tenants |
| Separate vector or search store filtered only by metadata | Retrieval system can scale independently | Tenant enforcement may depend on every query supplying the correct filter; duplicates authorization logic; synchronization and deletion must be secured in two systems |

## Decision

Use a shared PostgreSQL schema with defense in depth:

- Every tenant-owned table includes a required `workspace_id`.
- API authorization dependencies verify workspace membership and role.
- PostgreSQL RLS independently restricts tenant-owned rows using `app.current_user_id` and `app.current_workspace_id`.
- The API sets those values with transaction-local `set_config` calls.
- Migration and runtime credentials are separate, and the runtime role does not own tenant tables.
- Tenant-owned tables enable and force RLS, with explicit policies for permitted operations.

## Why this suits the current stage

The initial product has many small workspaces and a low-cost shared deployment. Shared-schema RLS supplies a strong database guardrail without provisioning and migrating separate schemas or databases.

It also aligns retrieval, document lifecycle, and business data under the same workspace key. PostgreSQL policies can restrict which rows normal queries may select, insert, update, or delete, making the isolation rule testable below the API layer ([PostgreSQL RLS documentation](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)).

## Consequences

### Advantages accepted

- Queries remain tenant-scoped if an application filter is accidentally omitted.
- Relational and future retrieval queries use the same tenant boundary.
- Isolation can be verified with adversarial integration tests.

### Limitations accepted

- All database work for one request must remain within the transaction that owns the tenant context.
- Background jobs must establish authoritative tenant context before accessing tenant rows.
- Table owners, superusers, and roles with `BYPASSRLS` do not represent normal runtime behavior, so direct tests must use the restricted runtime role.
- New tenant-owned tables require policies, indexes beginning with `workspace_id`, and isolation tests.

## When to reconsider

Consider schema-per-tenant or database-per-tenant when contractual isolation, customer-managed encryption keys, regional residency, tenant-specific restore, or very large tenant workloads require a physical boundary.

Consider a separate retrieval store only when measured retrieval scale requires it. PostgreSQL must remain the source of truth, and the derived store must have mandatory tenant scoping, idempotent synchronization, deletion propagation, and cross-tenant leakage tests before adoption.
