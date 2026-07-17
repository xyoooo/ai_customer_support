# Architecture decision records

ADRs record an important technical choice, why it fits the product now, which limitations are accepted, and what evidence should cause the team to reconsider it. They explain a decision; they are not implementation specifications or permanent rules.

## Index

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-modular-monolith.md) | Use a modular monolith | Accepted |
| [0002](0002-tenant-isolation.md) | Enforce tenant isolation in the API and PostgreSQL | Accepted |
| [0003](0003-authentication-sessions.md) | Use short-lived JWT access tokens with rotating opaque sessions | Accepted |
| [0004](0004-document-lifecycle-and-durable-jobs.md) | Use immutable document versions, portable object storage, and durable jobs | Accepted |
| [0005](0005-postgresql-and-pgvector.md) | Use PostgreSQL with pgvector as the primary data and retrieval store | Accepted |

## Required structure

Every new ADR uses these sections:

1. **Context**: the problem and boundary being decided.
2. **Decision drivers**: the properties that matter for this project.
3. **Options comparison**: a table with each viable option, its advantages, and its limitations.
4. **Decision**: the selected option and the rules it establishes.
5. **Why this suits the current stage**: why the trade-off matches the present team, scale, product maturity, and operating constraints.
6. **Consequences**: both advantages gained and limitations accepted.
7. **When to reconsider**: observable triggers for evaluating another option.

Use this comparison format:

| Option | Advantages | Limitations |
|---|---|---|
| Selected option | Benefits relevant to the decision drivers | Costs and risks the team accepts now |
| Alternative | Benefits that could make it preferable elsewhere | Why it does not fit the current stage |

## Writing rules

- Compare credible alternatives, not intentionally weak choices.
- Do not use cost as the only reason unless the decision is explicitly financial.
- State the selected option's limitations as clearly as its advantages.
- Use measurable reconsideration triggers where possible: latency, throughput, corpus size, failure rate, team ownership, compliance, or operating burden.
- Avoid predicting that a technology will scale or fail without benchmark evidence.
- If one ADR contains several inseparable sub-decisions, use a separate comparison table for each dimension. Otherwise, split independent decisions into separate ADRs.
- When a decision changes, keep the old ADR and mark it superseded; create a new ADR that links back to it.
