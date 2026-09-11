# SupportPilot Week 3 Review Report

- **Stage:** RAG strategy evaluation and production baseline
- **Status:** Complete
- **Review date:** September 11, 2026
- **Selected pipeline:** `rag-v1-c1-e1`
- **Project:** Personal, non-commercial AI customer-support platform

## Outcome

Week 3 delivered one measured, versioned RAG pipeline rather than a permanent strategy
switch. The isolated lab evaluated C0-C2 with E0-E2 on the human-reviewed 70-case Apple
suite. The project owner manually selected C1+E1, and a clean production branch was built
from `main` with only that parser, chunker, embedding adapter, storage contract, retrieval
path, tests, and user-facing evidence search.

The lab branch remains historical experiment evidence and was not merged. C0, C2, E0,
E2, candidate registries, mixed-dimension storage, raw datasets, PDFs, model files, and raw
results are absent from production.

The selected pipeline and its CI corrections are now on `main`. Commit `b57b267` added
the production C1+E1 vertical slice, and commit `2575fed` corrected fresh-database pgvector
bootstrap and added explicit pinned-model provisioning for CI and local setup.

## Delivered scope

| Area | Delivered result |
|---|---|
| Parsing | Deterministic PDF layout, Markdown, HTML, and plain-text parsing into normalized blocks with resolvable source locators |
| Chunking | C1 structure-aware boundaries; 350-token target, 500-token maximum, 60-token overlap, E1 tokenizer budget |
| Embedding | Pinned local Snowflake Arctic Embed XS revision, 384 normalized dimensions, fail-closed manifest and token checks, no runtime downloads |
| Storage | `document_chunks` with fixed `vector(384)`, pipeline provenance, indexes, forced RLS, least-privilege grants, and a cross-entity tenant-scope trigger |
| Worker | Object size and SHA-256 verification, lease renewal during model work, idempotent version replacement, atomic activation only after complete indexing |
| Retrieval | Active-version and tenant-scoped exact cosine candidates plus structural BM25 and deterministic reciprocal-rank fusion |
| API and UI | Workspace evidence-search endpoint and a workspace screen showing ranked passages, page/heading context, and dense/lexical ranks |
| Packaging | E1 cache mounted read-only and excluded from Git/build context; production images include only the selected runtime dependencies |

The fixed contract and future change rule are recorded in
[ADR 0007](adr/0007-c1-e1-production-rag-pipeline.md). A different strategy requires a new
pipeline version and explicit re-indexing; it cannot be enabled by a hidden configuration
switch.

## Selection evidence

C1+E1 achieved overall Recall@5 0.889, Complete@10 0.810, Citation@5 0.808, and
Citation@10 0.871. It led those four measures and tied the best Complete@5. C0+E1 was
faster and ranked the first hit slightly better, but produced less complete and less
citation-covering evidence. The complete matrix and decision limits are in the
[Week 3 RAG selection report](week-3-rag-selection-report.md).

The production parser and C1 chunker were independently compared with the exact evaluated
lab implementation at commit `8fcdba733b26301b9a1553fabf73d4a37b1effb0`. Text and
source locators matched for every chunk in all three Apple PDFs:

| Document | Lab chunks | Production chunks | Exact contract match |
|---|---:|---:|---|
| Apple Platform Security | 815 | 815 | Yes |
| Apple Personal Safety User Guide | 264 | 264 | Yes |
| Tips for Working with Apple Devices | 7 | 7 | Yes |

The pinned model ID, artifact revision, query preprocessing, input limit, vector dimension,
and normalization also match selected profile fingerprint
`430c6c3fbd841e744e3bc9b95a248fa4a5ef85ccc367e20744599ec2f45a9f7c`.

## Validation evidence

All final local gates and the post-merge GitHub workflow passed:

- Ruff lint and format checks.
- Strict mypy over `apps` and `packages`.
- 58 backend tests with 86.11% combined statement/branch coverage against the 85% gate.
- Migration cycle through Alembic head `20260911_0003`.
- Forced-RLS, direct cross-workspace access, cross-entity chunk forgery, active-version,
  worker lease/activation, hybrid retrieval, and API error-path tests.
- Frontend lint, 4 component/unit tests, TypeScript compilation, and Vite production build.
- Generated OpenAPI contract synchronized with the evidence-search endpoint.
- `npm audit --audit-level=high` with zero vulnerabilities after updating compatible
  development-tool transitive dependencies.
- API, worker, migration, storage-init, and web images built successfully.
- Healthy API/database/worker/web stack, migration container exit 0, and confirmed
  production table at Alembic revision `20260911_0003`.
- One Chromium end-to-end test using the real local E1 model: registration, Markdown
  upload, worker indexing, active status, evidence search, source passage display, and
  document job inspection.
- GitHub CI run 35 passed backend, frontend, frontend-security, contracts, containers, and
  the real-model end-to-end job on `main`.

The first post-merge workflow exposed a clean-environment gap that local state had masked:
the test database did not have the pgvector extension. The bootstrap now installs pgvector
in both application and test databases, and the complete backend suite was repeated against
a disposable fresh Linux database. Unblocking that job would also have exposed an empty E1
model mount in the end-to-end runner, so the pinned revision is now provisioned explicitly
and cached before containers start. Runtime model downloads remain disabled.

## Demo-ready scope

The current prototype supports a complete evidence-retrieval demonstration:

1. Register an owner and create an isolated workspace.
2. Upload a PDF, Markdown, HTML, or plain-text support document.
3. Observe queued processing, worker indexing, immutable version activation, and the
   completed durable job.
4. Ask a question and inspect ranked passages with document, page or heading context, and
   dense/lexical retrieval ranks.
5. Demonstrate that another workspace cannot enumerate or retrieve the first workspace's
   documents or chunks.

This is deliberately an evidence-search demo, not yet a generated-answer or conversational
assistant demo. The maintained walkthrough is in [the demo script](demo-script.md).

## Deviations and accepted trade-offs

The production baseline uses exact cosine search rather than HNSW. The current personal
corpus is small, exact search is deterministic, and no filtered-HNSW equivalence result yet
justifies approximate retrieval. Reconsider when the active corpus exceeds 10,000 chunks
or measured exact-search latency becomes unacceptable; adoption requires at least 95%
Recall@5 relative to filtered exact search.

The worker holds document bytes in memory after a bounded streaming read so synchronous PDF
and embedding libraries can process them. The configured upload limit bounds exposure. Move
to streamed temporary files or a parser service if accepted file sizes materially increase.

The Starlette `TestClient` deprecation warning remains non-blocking. It originates in the
current framework compatibility layer and does not affect runtime behavior; replace it when
the upstream FastAPI/Starlette testing path stabilizes.

## Known limitations and next work

- Six multi-part challenge cases still lack complete top-10 evidence. Evaluate query
  decomposition, per-subquery retrieval, and bounded neighbor expansion in the lab.
- The unanswerable spyware case requires answerability and grounded-generation behavior;
  retrieval alone should not decide whether to answer.
- Generated-answer faithfulness, citation completeness, clarification, abstention,
  conversation history, and human handoff remain Week 4 work.
- Passwords are correctly stored only as one-way hashes, but there is no authenticated
  password-change screen or safe local recovery command yet. Add both before relying on a
  long-lived personal account; defer email-based recovery while deployment remains local.
- A production malware scanner, DLP/PII controls, audit events, dedicated worker principal,
  secret management, retention policy, backup validation, and rate limits remain required
  before real customer data or public deployment.
- E1 requires an approximately 385.6 MiB ignored local model cache. The explicit
  `scripts/cache_rag_model.py` setup command provisions the pinned revision locally and CI
  caches it; application runtime remains offline-only.

## Week 4 handoff

Week 4 starts from a single tenant-safe evidence pipeline in `main`. Grounded chat should
treat retrieved chunks and source locators as the only answer evidence, validate every
citation against the immutable active version, and clarify or abstain when retrieval is
incomplete. More complex retrieval strategies remain lab experiments until they beat the
fixed regression suite and are promoted as a new versioned pipeline.
