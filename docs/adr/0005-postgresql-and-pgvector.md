# ADR 0005: Use PostgreSQL with pgvector as the primary data and retrieval store

- Status: accepted
- Date: 2026-07-17

## Context

SupportPilot needs to store relational product state, including users, workspaces, memberships, documents, immutable versions, jobs, conversations, feedback, model runs, and evaluations, and retrieve document chunks by both keywords and semantic similarity.

The database choice must therefore cover more than vector search. It must preserve relationships and transaction boundaries, enforce tenant isolation, support durable coordination, and provide acceptable retrieval quality and latency for the initial corpus.

This is not a choice between PostgreSQL and vector search. The selected option adds the `pgvector` extension so PostgreSQL also acts as the vector store.

## Decision drivers

- Keep transactional product data as one authoritative source of truth.
- Atomically create domain records and related durable jobs.
- Enforce workspace isolation in the same system that performs retrieval.
- Support hybrid lexical and semantic retrieval.
- Avoid synchronization failures between the document lifecycle and a separate vector index.
- Keep local development, backup, migration, and hosting operations manageable for one developer.
- Meet the initial target of fewer than roughly 10,000 chunks before optimizing for hypothetical scale.

## Options comparison

| Option | Advantages | Limitations |
|---|---|---|
| PostgreSQL with pgvector and full-text search | One source of truth; ACID transactions across domain, jobs, and chunks; joins and constraints; RLS tenant enforcement; exact or approximate vector search; hybrid retrieval without cross-system synchronization | Vector indexing shares database CPU, memory, storage, and maintenance; filtered approximate search requires tuning and recall measurement; may not be the best system at very large vector scale |
| PostgreSQL for product data plus Chroma as a derived retrieval index | Vector-focused collections and APIs; built-in vector, full-text, and metadata retrieval; retrieval can scale separately | Two systems must synchronize inserts, activation, deletion, and re-embedding; needs outbox, retries, reconciliation, and duplicate tenant controls; more deployment and backup operations |
| Chroma as the primary application database | Fast RAG prototyping; simple model of IDs, embeddings, documents, and metadata; embedded, single-node, and distributed modes | Collection-oriented records are not a replacement for the product's relational constraints, multi-entity transactions, job coordination, and complete operational data model; PostgreSQL or another operational database would still be needed |
| PostgreSQL plus another managed vector database | Independent vector scaling; managed availability and vector-specific features; potentially better performance for a measured workload | Additional recurring cost and vendor dependency; the same dual-write and reconciliation problem as Chroma; tenant filtering must be enforced in both systems |
| PostgreSQL without pgvector | Strong relational and transactional foundation; simplest database operations | Cannot perform semantic nearest-neighbor retrieval in the database; keyword search alone misses paraphrases and conceptually similar text |

## Decision

Use PostgreSQL 16 or later as the authoritative operational database and enable `pgvector` for chunk embeddings.

- Store product state, chunk metadata, embeddings, job state, and evaluation data in PostgreSQL.
- Use PostgreSQL full-text search for lexical candidates and pgvector for semantic candidates.
- Fuse independently ranked results with a deterministic method such as Reciprocal Rank Fusion.
- Filter candidates by `workspace_id` and active document version before they can be returned to answer generation.
- Start with exact search while the corpus is small; introduce and tune HNSW only when benchmarks show it is needed.
- Keep uploaded file bytes behind the `ObjectStore` boundary rather than storing them in PostgreSQL.
- Treat retrieval latency, recall, index size, and database resource use as measured signals, not assumptions.

pgvector supports exact nearest-neighbor search by default and approximate HNSW and IVFFlat indexes. It can be combined with PostgreSQL full-text search for hybrid retrieval ([pgvector documentation](https://github.com/pgvector/pgvector)). PostgreSQL RLS provides per-row policy enforcement for normal reads and writes in the same database ([PostgreSQL RLS documentation](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)).

## Why this suits the current stage

The first release has one developer, a small corpus, a low-cost deployment target, and a domain whose vectors are tightly related to workspace, document-version, activation, and job state. PostgreSQL already exists for those records. Adding pgvector keeps ingestion and retrieval consistent without operating a second stateful service.

Cost is a benefit, but it is not the primary reason. The stronger reasons are transactional consistency, relational integrity, one tenant-security boundary, and simpler failure recovery. At the current scale, those benefits outweigh the possible specialization of a separate vector database.

Chroma remains a valid future retrieval component. Its architecture provides tenants, databases, and collections optimized for vector similarity, full-text search, and metadata filtering ([Chroma architecture documentation](https://docs.trychroma.com/docs/overview/architecture)). Introducing it now would still leave PostgreSQL responsible for the rest of SupportPilot and would create a synchronization boundary before measurements justify one.

## Consequences

### Advantages accepted

- Document versions, chunks, activation state, and jobs can change consistently within database transactions.
- Foreign keys and constraints prevent orphaned or mismatched retrieval records.
- Tenant RLS and retrieval filtering share one authoritative workspace identity.
- One migration, backup, monitoring, and local-development workflow covers operational and retrieval data.
- Exact and approximate retrieval can be compared in the same environment to measure recall loss.

### Limitations accepted

- Ingestion and vector queries compete with transactional traffic for PostgreSQL resources.
- HNSW consumes memory and has build and maintenance costs.
- Approximate indexes can lose recall and interact with tenant or metadata filters, so retrieval tests must cover filtered results.
- Scaling the vector workload independently is harder while it shares the primary database.
- Database size limits on a free hosted plan constrain corpus and evaluation-history growth.

## When to reconsider

Benchmark before changing the architecture. Consider adding Chroma or another dedicated vector store when one or more of these conditions is demonstrated:

- Retrieval cannot meet the agreed p95 latency, throughput, or Recall@k target after query and index tuning.
- The corpus grows by orders of magnitude beyond the initial target and vector indexes materially harm operational database performance.
- Retrieval traffic needs an independent scaling, deployment, availability, or ownership boundary.
- A vector-specific capability produces a measured quality or operational improvement that pgvector cannot provide adequately.
- Hosting limits prevent the relational and vector workloads from fitting safely in the same database.

If a dedicated vector store is introduced, PostgreSQL remains the source of truth. Publish changes through a transactional outbox, use idempotent index operations, propagate activation and deletion, reconcile the two stores, and test cross-workspace isolation in both systems. The derived vector index must be rebuildable from PostgreSQL and object storage.
