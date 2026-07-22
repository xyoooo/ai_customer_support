# SupportPilot Week 3 Preview Plan

- **Stage:** RAG strategy evaluation and baseline
- **Status:** Planned; documentation approved before implementation
- **Document type:** Weekly preview plan
- **Planning date:** July 22, 2026
- **Execution window:** July 23-29, 2026
- **Project:** Enterprise-style AI customer support platform

## 1. Week 2 recap

Week 2 is complete and locally validated. It delivered tenant-isolated logical documents and immutable versions, secure streaming uploads, portable local object storage, durable PostgreSQL jobs, worker leases and retries, user-visible processing state, and safe version activation.

The consolidated evidence was strong: 46 backend tests passed with 86.67% statement/branch coverage against an 85% gate; Ruff and strict mypy passed; frontend linting, four tests, TypeScript compilation, and the production build passed; migrations and forced-RLS checks passed; both runtime containers built; and a Chromium workflow covered upload through completed worker processing.

The Week 2 review identified one prerequisite for this milestone: parsing and embedding can run longer than object verification, so the production worker must renew its lease during long processing. The demo remains limited to synthetic or public files because a production malware scanner, OCR, DLP, and retention controls are not yet present.

## 2. Objective for this week

Evaluate several chunking and embedding combinations under identical retrieval conditions, manually select the best combination for SupportPilot's current corpus and operating constraints, and productionize only that selected solution as the Week 3 RAG baseline.

The comparison system will live in `codex/week3-rag-strategy-lab`. It will support strategy switching, mixed embedding dimensions, exact vector retrieval, repeatable profile execution, and side-by-side quality reports. The lab branch will not be merged into `main`.

After evaluation, a clean `codex/week3-rag-production` branch will be created from `main`. Only reusable parsing work, the selected chunking implementation, the selected embedding implementation, the final database and worker integration, production retrieval, regression tests, and concise decision evidence will enter that branch and later merge into `main`.

By the end of the week, an authorized workspace member should be able to upload PDF, Markdown, text, or HTML content, wait for the selected pipeline to index it, submit a search query, and receive ranked evidence with a citation locator pointing to the source page, heading, or line range. Customer-facing generated answers remain a Week 4 concern.

## 3. Why this implementation is needed

Chunk size, boundary rules, context enrichment, query/document preprocessing, and embedding model can materially change retrieval quality. Selecting one combination before measuring it would turn an assumption into architecture and make later comparison expensive.

At the same time, placing every candidate and a runtime strategy switch in `main` would increase the production dependency surface, image size, configuration states, schema complexity, and testing burden. SupportPilot needs experimental flexibility during selection but one simple, explainable production pipeline after selection.

This milestone therefore separates two concerns:

1. **Research clarity:** the lab branch can compare candidates fairly without production compatibility constraints.
2. **Production clarity:** `main` receives one selected solution rather than a permanent experiment platform.
3. **Source fidelity:** every candidate uses the same canonical parser output and citation boundaries.
4. **Fair measurement:** exact vector search and fixed lexical/fusion settings prevent approximate-index behavior from distorting strategy selection.
5. **Reproducibility:** candidate configurations, model revisions, dataset version, code revision, and results are fingerprinted.
6. **Safe delivery:** the selected solution must independently pass ingestion, activation, tenant-isolation, retrieval, and regression gates before merge.

## 4. Engineering decision gate

### 4.1 Experiment-to-production workflow

| Choice | Advantages | Limitations | Decision |
|---|---|---|---|
| Select a chunker and embedder before implementation | Smallest initial implementation | Choice is based on assumptions; comparison later requires rework | Rejected |
| Merge a permanent runtime strategy platform into `main` | Alternatives remain immediately switchable | Enlarges production schema, dependencies, configuration states, and security/test surface | Rejected for the current product |
| Compare candidates in a lab branch, then manually productionize one winner from clean `main` | Fair experimentation and a small production pipeline; losing dependencies and code stay isolated | Requires disciplined commits and a deliberate transfer/validation step | Selected |

The lab branch is an experimental environment, not a merge candidate. Git merge is not used to transfer the result because it would include every reachable experimental commit. Shared production-quality work and the selected solution will instead be cherry-picked or deliberately reimplemented on a clean production branch created from `main`.

The completed lab state will be pushed and preserved with an immutable tag such as `rag-strategy-evaluation-v1`. The concise comparison report in `main` will record the tag, evaluated commit, dataset version, candidate fingerprints, selected pipeline version, and measured results.

This decision is specified in [ADR 0006](adr/0006-lab-evaluation-and-single-rag-production-pipeline.md).

### 4.2 Parsing strategy

| Choice | Advantages | Limitations | Decision |
|---|---|---|---|
| Each candidate parses its own source | Maximum candidate freedom | Parser differences confound chunking and embedding results; repeated security work | Rejected |
| One generic text extractor for every format | Small integration surface | Flattens structure and weakens citations | Rejected |
| Shared format-specific parsers producing canonical source blocks | Preserves native boundaries and keeps candidate comparisons fair | Requires production-quality parser contracts before experimentation | Selected |

The application-owned `DocumentParser` boundary will return ordered normalized blocks rather than final chunks. Blocks retain text, block type, heading path, and a format-specific locator. PDF uses page-level extraction; Markdown, text, and HTML adapters preserve headings, paragraphs, and source positions. HTML parsing removes active or irrelevant elements and never fetches linked resources.

Encrypted, malformed, image-only, empty, oversized, or extraction-amplification inputs fail with bounded error metadata. OCR remains deferred; scanned pages must be reported explicitly rather than silently indexed as empty content.

### 4.3 Chunking candidates

The initial lab will compare three profiles:

| ID | Candidate | Configuration | Purpose |
|---|---|---|---|
| C0 | Fixed-token boundary | 350-token windows, 60-token overlap, never cross a PDF page | Deterministic control baseline |
| C1 | Structure-aware recursive | Target 350, maximum 500, overlap about 60; prefer heading, paragraph, sentence, then token boundaries | Primary document-aware candidate |
| C2 | Structure-aware with deterministic context | Same chunks as C1; embed document title and heading path before the original chunk | Measure context retention without an ingestion LLM |

C2 stores and cites the original chunk text. The deterministic title and heading prefix is an embedding input, not source evidence.

Parent-child retrieval, embedding-based semantic breakpoints, late chunking, proposition extraction, LLM-generated contextual chunks, and hierarchical/RAPTOR indexing remain named future experiments. They enter the lab only after the initial candidates are complete or when measured failures justify them.

### 4.4 Embedding candidates

The initial lab will compare three local CPU candidates:

| ID | Candidate | Dimension | Role in the experiment |
|---|---|---:|---|
| E0 | `BAAI/bge-small-en-v1.5` | 384 | Existing lightweight project baseline |
| E1 | `Snowflake/snowflake-arctic-embed-xs` | 384 | Retrieval-focused alternative with the same dimension |
| E2 | `jinaai/jina-embeddings-v2-small-en` | 512 | Lightweight long-context alternative and future late-chunking path |

Each adapter owns its query and document preprocessing, pooling, normalization, dimension validation, and model revision. Candidate profiles must record those values because a prefix or pooling change creates a different retrieval system even when the model name is unchanged.

The lab may use a dimension-flexible pgvector column or isolated temporary tables and exact cosine search. `main` will receive only the selected dimension and its production index.

### 4.5 Retrieval conditions during selection

| Choice | Advantages | Limitations | Decision |
|---|---|---|---|
| Compare candidates through separate end-to-end retrieval implementations | Lets each candidate optimize independently | Confounds chunking/embedding quality with retrieval differences | Rejected |
| Compare with HNSW | Matches a possible production index | Approximation and filtered-index behavior can distort model comparison | Deferred until a winner exists |
| Use exact cosine search with fixed lexical retrieval and RRF | Fair and deterministic quality comparison; supports mixed dimensions | Does not measure final approximate-index performance | Selected for the lab |

All candidates use the same PostgreSQL full-text configuration, lexical/vector candidate counts, RRF constant, result count, tenant filters, active-version rules, and evaluation labels. Dense-only results are diagnostic; the primary selection score uses the same hybrid path intended for production.

After manual selection, the production branch will add a dimension-specific HNSW cosine index for the selected embedding and compare it with exact search. If the HNSW recall gate fails, the initial production pipeline remains on exact search and the deviation is documented.

### 4.6 Evaluation dataset and labels

| Choice | Advantages | Limitations | Decision |
|---|---|---|---|
| Ad hoc manual questions | Fast to demo | Cannot support fair comparison or regression detection | Rejected |
| Labels tied to generated chunk IDs | Easy scoring for one chunker | Invalid across chunking strategies | Rejected |
| Human-reviewed source-span labels | Valid across different chunk boundaries; directly checks citation coverage | Requires careful fixture and locator design | Selected |

The first dataset will contain 50 reviewed questions covering direct lookup, paraphrase, exact identifiers, multi-chunk evidence, ambiguous and unanswerable questions, superseded versions, and cross-workspace leakage attempts. Expected evidence is labeled by immutable document version and source locator or span rather than candidate-generated chunk ID.

The comparison report will include Recall@1, Recall@5, MRR, nDCG@5, citation-span coverage, per-category results, indexing duration, query latency, chunks per document, storage size, failures, and paired per-query wins/ties/losses. With only 50 cases, the report must not present small differences as universal superiority.

## 5. Final engineering decision

Week 3 will first build a switchable, exact-search experiment harness in `codex/week3-rag-strategy-lab` and compare C0-C2 with E0-E2 through a staged evaluation. A human will review the metrics and failure cases and manually select the best combination for the current SupportPilot corpus, citation requirements, CPU-local operating model, and latency/storage constraints.

The lab branch will not merge into `main`. A new `codex/week3-rag-production` branch will start from clean `main` and receive only:

- Canonical parsing and citation-boundary work.
- The selected chunking implementation and fixed parameters.
- The selected embedding adapter, pinned model revision, preprocessing, dimension, and normalization.
- One versioned production indexing pipeline.
- Tenant-owned chunk storage, lexical search, and the selected vector index.
- Worker lease renewal, safe activation, retry/idempotency behavior, retrieval API, tests, and concise evaluation evidence.

`main` will not receive the experiment registry, candidate profiles, losing strategies, mixed-dimension storage, profile-selection API/UI, candidate-only dependencies, notebooks, raw model caches, or raw generated indexes.

## 6. Branch and artifact boundaries

### 6.1 `main` before implementation

- Complete Week 1 and Week 2 product foundation.
- Approved Week 3 preview plan and ADR 0006.
- Existing quality gates passing.
- No partial Week 3 RAG implementation.

### 6.2 `codex/week3-rag-strategy-lab`

- Shared canonical parser prototypes and fixtures.
- Strategy contracts, registry, candidate profiles, and configuration fingerprints.
- C0-C2 chunkers and E0-E2 embedding adapters.
- Dimension-flexible experimental persistence.
- Exact vector search, fixed lexical retrieval, deterministic RRF, and comparison runner.
- Full candidate metrics, raw diagnostic output, and experiment-specific dependencies.
- Separate commits for shared work and each candidate so the selected result can be transferred cleanly.

### 6.3 `codex/week3-rag-production`

- Created from `main` only after manual selection.
- Production-quality shared parsing work.
- One selected chunking implementation.
- One selected embedding implementation.
- One pinned pipeline version and one production schema/index design.
- Complete ingestion, activation, retrieval, security, API, web inspection, and regression tests.
- Final concise comparison report and Week 3 review documentation.

### 6.4 Artifacts excluded from Git

- Downloaded model weights and caches.
- Generated embeddings and PostgreSQL dumps.
- Uploaded source documents other than approved synthetic fixtures.
- Secrets, credentials, local object-store data, and private content.
- Large raw benchmark traces that are not needed to reproduce the decision.

## 7. Production pipeline requirements

The selected pipeline merged into `main` will be direct and single-purpose:

1. Verify the immutable stored document version.
2. Parse it into canonical source blocks.
3. Apply the selected chunker with fixed versioned parameters.
4. Apply the selected embedding model with pinned preprocessing and revision.
5. Atomically persist tenant-owned chunks, citations, provenance, lexical data, and vectors.
6. Activate the new document version only after its complete selected index is ready.
7. Retrieve lexical and vector candidates scoped to the workspace and active version.
8. Fuse ranks deterministically and return citation-ready evidence.

The production implementation will record a single `RAG_PIPELINE_VERSION`, chunker identifier/version/parameters, embedding model/revision/dimension/normalization, and indexing timestamp. These fields provide provenance; they do not enable runtime strategy switching. A future strategy change creates a new pipeline version and requires explicit re-indexing.

## 8. Execution sequence

### Phase 1 - Documentation and shared evaluation contract

Approve this preview plan and ADR 0006. Define canonical source locators, the 50-case label format, candidate configuration fingerprints, fixed retrieval conditions, metrics, manual decision criteria, and branch-transfer rules before product implementation.

### Phase 2 - Lab parsing and chunking comparison

Create `codex/week3-rag-strategy-lab`. Build canonical parsing fixtures and C0-C2, then compare chunking with E0 held constant. Verify deterministic chunk output and source-span scoring.

### Phase 3 - Lab embedding comparison

Hold the best chunking candidate constant and compare E0-E2. Run a small finalist interaction check with the second-best chunker so the selected combination is not based only on a sequential assumption.

### Phase 4 - Manual selection and lab preservation

Review aggregate and per-category metrics, important failure cases, citation quality, latency, index size, model packaging, and operational constraints. Record the selected combination and rationale. Push and tag the evaluated lab commit.

### Phase 5 - Clean production implementation

Create `codex/week3-rag-production` from `main`. Transfer only reusable parsing work and the selected solution. Add the final migration, worker pipeline, lease heartbeat, idempotent persistence, safe activation, retrieval service, API, minimal web inspection surface, and selected-model packaging.

### Phase 6 - Independent production validation and review

Rerun the selected evaluation outside the lab harness, compare HNSW with exact search, run all backend/frontend/security/browser/container gates, update architecture and demo documentation, and produce the Week 3 review report.

## 9. Definition of done

Week 3 is complete when all of the following are true:

1. The lab evaluates the documented candidate set under identical exact-search, lexical, fusion, corpus, and labeling conditions.
2. Candidate configurations, model revisions, dataset version, code revision, and measured results are recorded reproducibly.
3. A human reviews metrics and failures and records one manually selected chunking/embedding combination with an explicit rationale.
4. The evaluated lab commit is pushed and preserved by an immutable tag; the lab branch is not merged into `main`.
5. A clean production branch from `main` contains only canonical parsing work and the selected RAG solution, not the switchable experiment framework or losing candidates.
6. All supported formats produce deterministic normalized blocks, selected chunks, and resolvable source locators from approved fixtures.
7. Malformed, encrypted, empty, image-only, oversized, and pathological files fail safely without activation, raw-content logging, or loss of the previous active version.
8. Repeat processing and retries produce one valid derived chunk set; an expired or stale worker cannot persist results or activate a version.
9. Lexical, vector, and fused retrieval return only active, non-deleted content from the requested workspace under both API and direct restricted-role tests.
10. The selected production implementation independently reaches Recall@5 of at least 80% and MRR of at least 0.70, with zero cross-workspace retrievals on the 50-case dataset.
11. HNSW Recall@5 is at least 95% relative to exact cosine search, or the production baseline remains on exact search with the reason documented.
12. Backend, frontend, migration, security, browser, and container checks pass, with backend statement/branch coverage at or above 85%.
13. The concise report in `main` records all evaluated combinations and metrics without including losing implementations or raw experimental artifacts.
14. The Week 3 review report records delivered scope, evidence, deviations, limitations, the selected pipeline version, and the Week 4 handoff.

## 10. Non-goals for Week 3

- A permanent runtime strategy switch or customer-selectable RAG profile in `main`.
- Merging all lab candidates or their dependencies into the production codebase.
- Customer-facing chat, token streaming, conversation history, or LLM-generated answers.
- Confidence thresholds, clarification policy, answer abstention, or human ticket handoff.
- OCR, table reconstruction, image understanding, or hosted layout parsing.
- Cross-encoder reranking, query rewriting, learned sparse retrieval, multilingual retrieval, or model fine-tuning.
- Large-scale vector performance claims; the target remains a small portfolio corpus.
- Training on the 50-case evaluation set.

## 11. Main risks and controls

| Risk | Control this week |
|---|---|
| Candidate pipeline differs in more than the intended variable | Share parsing, labels, exact search, lexical retrieval, fusion, and filters; change one experiment axis at a time. |
| Lab code accidentally expands production scope | Never merge the lab branch; create the production branch from clean `main` and transfer only approved work. |
| Selected implementation behaves differently after transfer | Rerun the complete selected evaluation and compare chunks, preprocessing, vectors, and rankings outside the lab harness. |
| Fifty cases produce an unstable winner | Report paired and per-category results, inspect failures manually, and treat close results as inconclusive rather than universal superiority. |
| Different vector dimensions complicate comparison | Use dimension-flexible experimental storage and exact search in the lab; create a selected-dimension production schema/index later. |
| Model preprocessing is applied inconsistently | Keep query/document prefixes, pooling, normalization, and revision inside each adapter and its fingerprint. |
| Parser consumes excessive CPU or memory | Enforce byte, page, character, block, and expansion-ratio limits with bounded failures. |
| Chunk overlap creates misleading citations | Retain precise source spans and never cross PDF pages. |
| Long ingestion loses its lease | Add heartbeat renewal and require current lease ownership in the final production transaction. |
| Failed indexing replaces working evidence | Keep the previous active version until the complete selected index commits successfully. |
| Experimental artifacts expose data or bloat Git | Use approved synthetic fixtures and exclude weights, caches, embeddings, object data, dumps, and large raw traces. |

## 12. Potential future lab experiments and triggers

| Experiment | Introduce when |
|---|---|
| Parent-child retrieval | Small chunks find the correct fact but lack sufficient surrounding policy context. |
| Semantic breakpoint chunking | Structure-aware chunks repeatedly combine unrelated topics. |
| Late chunking | Pronouns and cross-paragraph references cause measurable retrieval failures. |
| Proposition retrieval | Fine-grained fact retrieval is a dominant failure and ingestion-model provenance is acceptable. |
| LLM-generated contextual retrieval | Deterministic title/heading context is insufficient and the added cost can be measured. |
| Matryoshka embeddings | Vector storage or index memory becomes a meaningful constraint. |
| Learned sparse/SPLADE retrieval | PostgreSQL lexical plus dense retrieval repeatedly misses domain terminology. |
| ColBERT or other late interaction | Correct evidence reaches the candidate set but single-vector ranking remains inadequate. |
| Multilingual embedding | Non-English content becomes an explicit requirement with a labeled multilingual dataset. |
| Domain fine-tuning | Several hundred reviewed queries with positive and hard-negative evidence labels are available. |

Each future experiment starts from the current `main`, runs in a refreshed lab branch, and produces a new manually selected pipeline version only if it demonstrates a material improvement.

## 13. Expected Week 4 handoff

Week 4 should begin with one production RAG pipeline whose chunking and embedding choices were measured rather than assumed. Active source versions become citation-ready chunks through recoverable jobs; hybrid retrieval is tenant-safe and deterministic; the selected strategy and provenance are explicit; and a fixed regression dataset shows where the pipeline succeeds and fails. Week 4 can then add streaming grounded chat, citation validation against retrieved evidence, conversation history, confidence-based clarification or abstention, feedback, and human ticket handoff.
