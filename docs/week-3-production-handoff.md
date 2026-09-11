# Week 3 production handoff plan

- Status: approved implementation plan; production coding not started
- Selected pipeline: C1 structure-aware chunking + E1 Snowflake Arctic Embed XS
- Retrieval baseline: `bm25-structural-v1` + exact cosine + deterministic RRF
- Lab branch: `codex/week3-rag-strategy-lab`
- Production branch: `codex/week3-rag-production`, created from current `main`
- Governing decision: [ADR 0006](adr/0006-lab-evaluation-and-single-rag-production-pipeline.md)
- Selection evidence: [Week 3 RAG strategy selection report](week-3-rag-selection-report.md)

## 1. Delivery rule

The lab branch will be preserved, not merged. The production branch will start from clean,
up-to-date `main` and receive one fixed pipeline. Production will not contain candidate IDs,
a strategy registry, mixed vector dimensions, runtime model selection, or losing model
dependencies.

The current `main` migration head is `20260716_0002`. The lab-only migrations
`20260722_0003` and `20260910_0004` must not be copied. Production receives a new migration
whose parent is the migration head on `main` when the production branch is created.

`main` currently also has uncommitted documentation owned by the project owner. Those files
must be reviewed and committed or otherwise deliberately preserved before creating the
production branch. The handoff must not overwrite or hide them.

## 2. Finalize the lab branch

### 2.1 Freeze the experiment inputs

1. Preserve `week3-apple-suite-v2-reviewed` as the selected benchmark version.
2. Confirm that only the 14 reviewed challenge cases differ from the provisional suite.
3. Validate all 70 cases, source versions, block identifiers, and character boundaries.
4. Record all six source hashes and the public acquisition URLs where applicable in a corpus
   manifest.
5. Keep downloaded Apple documents, model weights, caches, vectors, and raw result JSON out
   of Git.
6. Keep the full reviewed question/evidence dataset local. Commit only a source-free
   benchmark manifest containing its hash, case counts, local filenames, public source URLs,
   and corpus hashes.

### 2.2 Freeze the implementation

Organize the current work into two auditable commits. Create the functional commit first;
create the documentation commit only after the committed-code matrix has completed:

1. `feat: calibrate the RAG strategy lab`
   - parser v2 and source locators;
   - shared model-token budget enforcement;
   - `bm25-structural-v1` and PostgreSQL parity adapter;
   - matrix and summary tooling;
   - migrations and automated tests.
2. `docs: record the reviewed C1+E1 selection`
   - reviewed benchmark manifest;
   - challenge review guide;
   - selection report, ADR outcome, and this handoff plan.

Do not combine generated model data or raw local reports with either commit.

### 2.3 Reproduce from a commit

The final matrix was reproduced from functional commit
`8fcdba733b26301b9a1553fabf73d4a37b1effb0`. Before tagging the lab:

1. [Complete] Commit the functional implementation and obtain its Git SHA.
2. [Complete] Rerun the full 3x3 matrix with that SHA as `code_revision` and the frozen reviewed dataset.
3. [Complete] Confirm all nine profiles complete, with zero truncation and zero cross-workspace results.
4. [Complete] Record the committed run's C1+E1 fingerprint:
   `430c6c3fbd841e744e3bc9b95a248fa4a5ef85ccc367e20744599ec2f45a9f7c`.
5. [Complete] Inspect finalist disagreements and confirm the manual selection still holds.
6. Commit the reviewed source-free manifest and final documentation as the evidence commit.

### 2.4 Lab exit gates

Before the branch is pushed and tagged:

- Ruff, formatting, strict mypy, unit tests, PostgreSQL integration tests, security tests,
  migration upgrade/downgrade, coverage, frontend lint/test/build, and container builds pass.
- The C1+E1 PostgreSQL adapter reproduces the in-memory chunks and rankings on approved
  fixtures.
- Git contains no local corpus, model cache, embedding, database dump, credential, or raw
  experiment artifact.
- The selection report names the evaluated functional commit, reviewed dataset version,
  final profile fingerprint, accepted trade-offs, and remaining failures.
- Push `codex/week3-rag-strategy-lab` and create an immutable tag such as
  `rag-week3-lab-v2-c1-e1` on the final evidence commit.

## 3. Create the production branch

1. Finish or deliberately preserve the current uncommitted documentation on `main`.
2. Fetch and confirm local `main` matches `origin/main`.
3. Create `codex/week3-rag-production` from that clean `main` commit.
4. Do not merge or wholesale cherry-pick the lab branch.
5. Transfer selected code in small production-oriented commits and independently validate
   each boundary.

## 4. Production code structure

Create a production package named `packages/rag`; do not retain the `rag_lab` name or its
candidate abstractions.

| Production module | Responsibility | Lab source used as reference |
|---|---|---|
| `packages/rag/models.py` | Canonical blocks, C1 chunks, locators, and retrieval results | selected portions of `rag_lab/models.py` |
| `packages/rag/parsing.py` | Bounded PDF, Markdown, HTML, and text parsing | `rag_lab/parsing.py` |
| `packages/rag/chunking.py` | C1 only, with fixed parameters | C1 path in `rag_lab/chunking.py` |
| `packages/rag/embedding.py` | E1 only, pinned preprocessing and model revision | E1 path in `rag_lab/embeddings.py` |
| `packages/rag/lexical.py` | `bm25-structural-v1` | `rag_lab/lexical.py` |
| `packages/rag/repository.py` | Tenant-scoped chunk persistence and retrieval queries | selected PostgreSQL behavior |
| `packages/rag/service.py` | Indexing and hybrid retrieval orchestration | selected lab flow |
| `apps/api/routes/retrieval.py` | Authorized evidence-search endpoint | new production code |

Production constants belong in one versioned pipeline definition, for example
`rag-v1-c1-e1`:

- C1 target 350 tokens, hard maximum 500, and approximately 60-token overlap;
- heading, paragraph, sentence, then token fallback boundaries;
- E1 artifact `snowflake/snowflake-arctic-embed-xs` at the pinned lab revision;
- documented query prefix, CLS pooling, normalization, cosine distance, and 384 dimensions;
- lexical scorer version and weights;
- dense and lexical candidate counts, RRF constant, result limit, and tie-break rule.

These values are constants, not customer settings. A future change creates a new pipeline
version and explicit re-indexing operation.

## 5. Production database design

Create a production table such as `document_chunks`; do not rename or reuse
`rag_lab_chunks`. The first migration should contain:

- `workspace_id`, `document_id`, and immutable `version_id` foreign keys;
- pipeline version, deterministic chunk ID, chunk order, original text, token count, title,
  heading path, page number, and source locators;
- one `vector(384)` embedding column rather than an unbounded vector plus a dimension column;
- a generated English `tsvector` for lexical support;
- uniqueness for one chunk within a document version and pipeline version;
- checks for non-empty text, valid IDs, positive tokens/pages, and valid pipeline version;
- forced RLS policies and grants for the restricted application role;
- workspace/version lookup and GIN lexical indexes.

Retrieval must determine visibility by joining through `documents.active_version_id` and
excluding deleted documents. Do not rely on a second mutable `active` flag that can drift
from the document lifecycle.

Use exact cosine retrieval for the initial small corpus. Add HNSW only after it reaches at
least 95% Recall@5 relative to exact search under tenant filtering; otherwise record exact
search as the production baseline.

## 6. Worker indexing transaction

Replace the current verify-and-activate document path with this sequence:

1. Claim the processing job and mark the document version processing.
2. Start lease renewal before parsing or embedding.
3. Re-read and verify the stored object size and digest.
4. Parse into deterministic canonical blocks with bounded PDF/page/text limits.
5. Produce C1 chunks and resolve every locator back to its source block.
6. Validate every E1 input with the actual tokenizer; never silently truncate.
7. Embed in bounded batches using one process-level E1 model instance.
8. In one final transaction, verify current lease ownership, replace the version's complete
   chunk set, set `documents.active_version_id`, mark the new version active, and complete
   the job.
9. On failure or stale lease, keep the previous active version searchable, remove or hide
   partial derived data, and apply the existing bounded retry/dead-letter policy.

Deletion must remove or make inaccessible all derived chunks. Reprocessing the same version
and pipeline must be idempotent.

## 7. Hybrid retrieval path

The first production query path remains deliberately simple:

1. Validate and normalize a bounded user query.
2. Set PostgreSQL user and workspace tenant context.
3. Embed the query with the fixed E1 query preprocessing.
4. Retrieve exact cosine candidates from active document versions only.
5. Score active, tenant-scoped chunks with `bm25-structural-v1`.
6. Fuse dense and lexical ranks with the fixed deterministic RRF configuration.
7. Return the top evidence passages with resolvable source citations.

For the present personal corpus, application BM25 may scan the bounded active workspace
chunk set and cache prepared lexical documents by an index-generation key. Record a scaling
trigger before this exceeds 10,000 active chunks or the measured latency budget. At that
trigger, introduce stored corpus statistics or bounded SQL candidate generation and rerun
the benchmark; do not silently substitute PostgreSQL `ts_rank` and call it equivalent BM25.

Online query decomposition and rewriting are deferred to the answer-generation layer. The
retrieval API must be reusable for several subqueries and must preserve per-query traces.
Parent-child chunking is also deferred; current failures involve distant or cross-document
evidence rather than a retrieved child lacking nearby context.

## 8. API contract

Add an authenticated workspace evidence-search endpoint with:

- a non-empty bounded query;
- a server-bounded result count;
- membership and workspace checks before retrieval;
- results containing document/version identity, original evidence text, page, heading path,
  exact source locators, and deterministic rank information;
- no model vectors, raw internal prompts, filesystem paths, or cross-workspace metadata;
- stable errors for unavailable model cache, unsupported document state, and bounded
  processing failures.

This endpoint returns evidence, not a generated answer. Chat, streaming, answerability,
query rewriting, and citation-grounded generation remain later product work.

## 9. Dependency and model packaging

- Move only the selected runtime libraries into a production dependency group installed in
  the API and worker images.
- Remove E0/E2 artifacts and model-selection code from the production build.
- Configure a dedicated E1 model-cache path and verify its pinned manifest at startup.
- Normal API and worker startup must never download model files implicitly.
- Mount or provision the approximately 385.6 MiB E1 artifact explicitly for local Docker.
- Keep API and worker model loading lazy or process-scoped so repeated requests/jobs do not
  reload the model.
- Add model-cache availability to readiness without logging local paths or model contents.

## 10. Production tests and acceptance gates

### Equivalence

- Golden fixtures produce identical parser blocks, C1 chunks, embedding input, and locators
  in lab and production.
- E1 vectors match within a documented floating-point tolerance.
- Exact dense, BM25, and fused ordering match the selected profile on fixed fixtures.
- The standalone production evaluation stays within an accepted tolerance of C1+E1:
  Recall@5 0.889, Complete@5 0.714, Complete@10 0.810, Citation@5 0.808, and
  Citation@10 0.871, with zero truncation and cross-workspace results.

### Security and lifecycle

- Direct restricted-role and API tests prove forced RLS and active-version filtering.
- Superseded, deleted, other-workspace, partial, failed, and stale-worker chunks never appear.
- Retry, cancellation, lease expiry, duplicate delivery, and activation races preserve the
  previous working index.
- Citation locators resolve only within their immutable source version.

### Repository and runtime

- Backend lint, formatting, strict typing, unit, integration, security, migration, and 85%
  statement/branch coverage gates pass.
- Frontend lint, tests, type checking, production build, OpenAPI synchronization, and browser
  evidence-search flow pass.
- API and worker images build with only the selected RAG dependencies.
- Docker smoke testing covers upload, processing, activation, search, citation resolution,
  replacement by a new version, and deletion.

## 11. Planned production commit sequence

1. `docs: define the C1+E1 production contract`
2. `feat: add tenant-safe production chunk storage`
3. `feat: add the selected parser chunker and embedder`
4. `feat: index document versions before atomic activation`
5. `feat: add deterministic hybrid evidence retrieval`
6. `feat: expose workspace evidence search`
7. `test: verify lab equivalence and lifecycle safety`
8. `docs: close Week 3 and record production evidence`

Each commit should pass its relevant focused tests. The final branch must pass the complete
repository and container gates before review.

## 12. Explicit exclusions from `main`

- C0 and C2 implementations;
- E0 and E2 adapters, weights, and dependencies used only by them;
- candidate registries, switches, profile matrices, and mixed-dimension storage;
- `rag_lab_chunks` and both lab migration revisions;
- raw PDFs, model weights, generated vectors, caches, and raw result reports;
- parent-child chunking, HNSW without equivalence evidence, rerankers, query rewriting,
  generated answers, and chat UI.

## 13. Merge into `main`

After all gates pass, review the production branch as a standalone change against `main`.
Merge only `codex/week3-rag-production`; keep the lab branch and immutable tag as historical
selection evidence. Tag the production merge with the pipeline version, retain the reviewed
regression manifest and concise selection report, and make any future retrieval change an
explicit new pipeline version with a re-indexing plan.
