# ADR 0002: Enforce tenant isolation in the API and PostgreSQL

- Status: accepted
- Date: 2026-07-13

## Context

An application-only `WHERE workspace_id = ...` convention is easy to omit and cannot provide defense in depth after an authorization defect.

## Decision

Every tenant-owned table includes `workspace_id`. Authorization dependencies verify workspace membership and role. PostgreSQL RLS independently filters tenant-owned rows using `app.current_user_id` and `app.current_workspace_id`, set with transaction-local `set_config` calls. Migration and runtime credentials are separate, and the runtime role does not own tables.

## Consequences

Queries are tenant-scoped even if an ORM filter is missed. All database work for one request must remain in one transaction. Background jobs must establish tenant context before accessing tenant rows. Direct database tests must use the runtime role because owners and superusers can bypass normal RLS behavior.

