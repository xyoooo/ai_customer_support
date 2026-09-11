# SupportPilot RAG Strategy Lab

- **Branch:** `codex/week3-rag-strategy-lab`
- **Status:** Reviewed 70-case matrix complete; C1+E1 selected for the production prototype
- **Date:** September 10, 2026
- **Related plan:** [Week 3 preview plan](week-3-preview-plan.md)
- **Selection evidence:** [Week 3 RAG strategy selection report](week-3-rag-selection-report.md)
- **Decision boundary:** [ADR 0006](adr/0006-lab-evaluation-and-single-rag-production-pipeline.md)

## 1. Purpose

This branch exists to compare chunking and embedding combinations before SupportPilot commits to one production RAG pipeline. It is a controlled experiment environment, not a second product implementation and not a branch that will merge into `main`.

The lab must answer four questions with evidence:

1. Which chunking approach retrieves the correct source evidence most reliably for the current document corpus?
2. Which local embedding model performs best with the selected chunking approach under the project's CPU, storage, packaging, and licensing constraints?
3. Does deterministic document and heading context improve retrieval enough to justify including it in the production pipeline?
4. Can the manually selected combination be reproduced outside the lab harness without losing quality, citations, isolation, or reliability?

The word **selected** means best for the current corpus, evaluation set, metrics, and operating constraints. The report must not describe the result as universally optimal.

### Implemented lab layout

- `packages/rag_lab/parsing.py`: canonical layout-aware PDF, Markdown, HTML, and text parsing.
- `packages/rag_lab/chunking.py`: switchable C0, C1, and C2 implementations.
- `packages/rag_lab/token_budget.py`: shared E0-E2 model-tokenizer budget validation.
- `packages/rag_lab/embeddings.py`: pinned offline E0-E2 FastEmbed adapters and model-manifest checks.
- `packages/rag_lab/retrieval.py`: exact dense, fixed lexical, and deterministic RRF reference/PostgreSQL retrieval.
- `packages/rag_lab/dataset.py`: reviewed-dataset schema, reference validation, and strict 50-case coverage gates.
- `packages/rag_lab/evaluation.py`: indexing, query execution, quality, citation, isolation, latency, and storage reporting.
- `scripts/cache_rag_model.py`: explicit pinned model acquisition; normal runs never download models.
- `scripts/run_rag_experiment.py`: one-profile execution with an immutable fingerprint.
- `scripts/run_rag_matrix.py`: reusable corpus/model execution for a candidate matrix.
- `scripts/summarize_rag_suite.py`: separate baseline and challenge summaries.
- `scripts/compare_rag_experiments.py`: side-by-side evidence without automatic selection.
- `experiments/rag/example`: synthetic smoke inputs only; not selection evidence.

The local `week3-apple-suite-v2-reviewed` dataset combines the stable 50-case baseline and
20 reviewed challenge cases. The full local dataset, downloaded Apple corpus, and generated
reports are excluded from Git. A source-free question/evidence manifest and corpus hashes are
the reproducibility artifacts planned for transfer; raw Apple documents remain local. The
code rejects incomplete baseline category/media coverage when `--strict-dataset` is enabled.

## 2. Branch boundary

### Included in this branch

- Canonical parser prototypes and approved synthetic fixtures.
- Switchable chunking and embedding contracts.
- Candidate registry and immutable candidate profiles.
- Exact vector retrieval that supports candidate embeddings with different dimensions.
- Fixed PostgreSQL lexical retrieval and deterministic Reciprocal Rank Fusion (RRF).
- A reviewed 50-case retrieval dataset and source-span labels.
- Batch indexing, comparison, reporting, and diagnostic tooling.
- Candidate-specific dependencies and contract tests.
- Raw local experiment output that is excluded from Git when it is large or generated.

### Excluded from this branch's merge result

- A permanent runtime strategy switch in the product.
- Customer or administrator profile selection.
- A production schema designed to host all candidate dimensions.
- Losing strategy implementations and their dependencies.
- Downloaded model weights, caches, generated vectors, database dumps, or private documents.

After manual selection, `codex/week3-rag-production` will be created from clean `main`. The lab branch will not be merged. Only the selected solution and approved reusable work will be transferred and independently validated.

## 3. Experimental constants

The following inputs remain fixed while chunking and embedding candidates are compared:

| Area | Fixed condition |
|---|---|
| Source content | Same immutable synthetic document versions and checksums |
| Parsing | Same ordered canonical blocks and source locators |
| Tenant scope | Same workspace and active-version filters with forced RLS |
| Lexical retrieval | Same application-owned `bm25-structural-v1` scorer for in-memory and PostgreSQL runs |
| Vector comparison | Exact cosine search; no approximate index during candidate selection |
| Candidate counts | Same lexical and dense candidate limits |
| Fusion | Same deterministic RRF constant and tie-breaking rule |
| Result count | Same top-k for every evaluation case |
| Labels | Same reviewed document-version and source-span evidence labels |
| Runtime | Same machine, CPU allocation, batch size, warm-up policy, and model-cache state per comparison group |
| Repetition | Same number of indexing and query repetitions |

Changing any constant creates a new experiment version and invalidates direct comparison with prior results unless the full candidate group is rerun.

## 4. Candidate profile identity

Every run uses an immutable profile with a canonical JSON representation and SHA-256 fingerprint. At minimum, the profile records:

- Profile ID and schema version.
- Parser ID, version, and normalization settings.
- Chunker ID, version, token limits, overlap, boundary rules, and context policy.
- Embedding provider, model ID, immutable revision, input limit, vector dimension, pooling, normalization, and query/document prefixes.
- Distance function.
- Lexical configuration.
- Lexical and vector candidate counts.
- RRF constant, result count, and deterministic tie-breaker.
- Dataset version and code revision.

A parameter change creates a new profile ID. Results from two fingerprints must never be combined under one label.

## 5. Chunking candidates for the initial experiment

These candidates are implemented in the Week 3 lab.

### C0 - Fixed-token control

| Field | Value |
|---|---|
| Status | Implemented in the lab framework |
| Target and maximum | 350 tokens |
| Overlap | 60 tokens |
| Boundary rule | Never cross a PDF page; otherwise ignore structure |
| Embedding input | Original chunk text |
| Purpose | Provide the simplest deterministic baseline |

Expected advantage: minimal implementation and predictable size. Expected weakness: headings, paragraphs, lists, and sentence boundaries may be split arbitrarily.

Required tests:

- Exact output for fixed fixtures.
- No empty or over-limit chunks.
- Stable overlap with no duplicate final chunk.
- No chunk crosses a PDF page.
- Every source token belongs to a chunk except explicitly normalized whitespace.
- Citation locator covers the complete chunk source span.

### C1 - Structure-aware recursive

| Field | Value |
|---|---|
| Status | Implemented in the lab framework |
| Target | 350 tokens |
| Hard maximum | 500 tokens |
| Overlap | Approximately 60 tokens without crossing source boundaries |
| Preferred boundaries | Heading, paragraph, sentence, then token fallback |
| Embedding input | Original chunk text |
| Purpose | Preserve policy and manual structure while bounding context size |

Expected advantage: coherent, citation-friendly units for Markdown, HTML, text, and PDF. Expected weakness: performance depends on parser structure and fallback behavior for oversized blocks.

Required tests:

- All C0 safety and determinism properties where applicable.
- Heading paths and paragraph order are preserved.
- A normal section is not joined to the following unrelated section only to reach the target size.
- Oversized paragraphs split deterministically at sentence or token boundaries.
- Lists remain ordered and list-item source locators remain valid.
- Overlap never produces a citation outside the chunk's permitted page or section boundary.

### C2 - Structure-aware with deterministic context

| Field | Value |
|---|---|
| Status | Implemented through the pinned offline adapter |
| Chunk boundaries | Identical to C1 |
| Stored and cited content | Original C1 chunk text only |
| Embedding input | Document title, heading path, then original chunk text |
| Purpose | Test whether inexpensive structural context improves isolated chunk retrieval |

Example embedding input:

```text
Document: Returns and Refunds
Section: International Returns > Time limits

<original source chunk>
```

Required tests:

- C1 and C2 generate identical original chunks and locators.
- Only the embedding input differs.
- Context fields come from trusted parsed metadata, not source instructions or generated text.
- Missing titles or headings produce a canonical representation rather than variable whitespace.
- Returned evidence and citations never claim the synthetic prefix as source content.
- Prefix token use is counted and remains inside the embedding model's input limit.

## 6. Embedding candidates for the initial experiment

These candidates are in Week 3 scope. All are intended for local CPU inference through an application-owned adapter; no model is selected in advance.

### E0 - BGE small English v1.5

| Field | Value |
|---|---|
| Model | `BAAI/bge-small-en-v1.5` |
| Status | Implemented through the pinned offline adapter |
| Dimension | 384 |
| Role | Existing project baseline |
| License to record | MIT |
| Key variable | Query instruction enabled or disabled must be fixed in the profile |

The model card recommends evaluating the retrieval instruction on the target task; passages do not require that instruction. The chosen setting must be part of the profile fingerprint. See the [BGE model card](https://huggingface.co/BAAI/bge-small-en-v1.5).

### E1 - Snowflake Arctic Embed XS

| Field | Value |
|---|---|
| Model | `Snowflake/snowflake-arctic-embed-xs` |
| Status | Implemented through the pinned offline adapter |
| Dimension | 384 |
| Role | Retrieval-focused lightweight alternative with the same dimension as E0 |
| License to record | Apache-2.0 |
| Key variable | Query prefix and CLS pooling are adapter-owned behavior |

The adapter must reproduce the model's documented query prefix, pooling, and normalization behavior. See the [Arctic Embed XS model card](https://huggingface.co/Snowflake/snowflake-arctic-embed-xs).

### E2 - Jina Embeddings v2 Small English

| Field | Value |
|---|---|
| Model | `jinaai/jina-embeddings-v2-small-en` |
| Status | Implemented through the pinned offline adapter |
| Dimension | 512 |
| Role | Lightweight long-context comparison and future late-chunking path |
| License to record | Apache-2.0 |
| Key variable | Maximum input length must be explicit and measured |

The model card describes a 33-million-parameter English model with long input support. This experiment uses ordinary independent chunk embeddings; late chunking is a separate future candidate. See the [Jina v2 small model card](https://huggingface.co/jinaai/jina-embeddings-v2-small-en).

FastEmbed currently lists E0-E2 as supported local models. The lab must pin package and model revisions rather than relying on the moving supported-model list. See the [FastEmbed model catalog](https://qdrant.github.io/fastembed/examples/Supported_Models/).

### Common embedding contract tests

Every initial embedding adapter must pass:

- Model revision and license metadata are present.
- Query and document preprocessing are separate, explicit, and deterministic.
- Output dimension equals the profile dimension for every batch item.
- Empty input is rejected before model inference.
- Output contains no NaN or infinite values.
- Normalization matches the declared distance function.
- Batch and single-item inference produce equivalent vectors within a documented floating-point tolerance.
- Repeated warm inference produces equivalent vectors within tolerance.
- Oversized input is rejected or deterministically truncated according to the profile; silent library truncation is prohibited.
- Model loading never downloads implicitly during a normal offline evaluation run.
- Raw document text and vectors are absent from general logs.

Normal E0-E2 profiles reject oversized embedding inputs. Before chunk finalization, the lab
validates the proposed input against all three actual model tokenizers, including special
tokens, document prefixes, and the full C2 title/heading context. C1 and C2 therefore retain
identical source boundaries while fitting the strictest candidate. Oversized semantic pieces
split deterministically at source-aligned token spans. Right truncation remains an adapter
fallback for explicitly configured diagnostic profiles only; it is not used by the measured
profiles. The September 2 matrix reported zero truncated inputs for all nine combinations.

## 7. Future chunking candidates

The following strategies are catalogued for later lab cycles. They are not Week 3 implementation commitments.

| ID | Candidate | Intended benefit | Trigger to implement | Additional test burden |
|---|---|---|---|---|
| FC3 | Parent-child retrieval | Retrieve a precise child but return a larger parent section | Correct facts are retrieved but lack surrounding conditions | Parent linkage, expansion limits, duplicate-parent fusion, citation containment |
| FC4 | Semantic breakpoint chunking | Split when adjacent sentence meaning changes | Structure-aware chunks repeatedly combine unrelated topics | Segmentation-model fingerprint, threshold sweep, stability, added indexing cost |
| FC5 | Late chunking | Preserve document context in chunk embeddings | Pronouns or cross-paragraph references cause repeated misses | Token-to-source alignment, pooling spans, long-input bounds, compatible-model verification |
| FC6 | Proposition or atomic-fact indexing | Improve fine-grained factual retrieval | Passage granularity dominates failures | Generation provenance, factual preservation, omissions, duplicate propositions, cost |
| FC7 | LLM-generated contextual chunks | Add document-specific context that headings cannot provide | C2 remains weak on context-dependent evidence | Prompt/model versioning, hallucination checks, source separation, cost and retry controls |
| FC8 | Hierarchical/RAPTOR indexing | Retrieve leaf facts and higher-level summaries | Multi-section questions are a major measured category | Tree reproducibility, summary provenance, parent/child ranking, generation failures |
| FC9 | Query-adaptive window expansion | Add neighboring context only for the current query | Static chunks trade precision against insufficient context | Query-time determinism, latency, expansion bounds, cache behavior, citation union |
| FC10 | Advanced table/OCR-aware chunking | Extend the implemented text-layout parser to preserve table cells and image-only pages | Table or scanned-document questions fail | Cell coordinates, table fixtures, OCR confidence, image-only pages |

References for the catalogued approaches include [Late Chunking](https://arxiv.org/abs/2409.04701), [Dense X Retrieval](https://arxiv.org/abs/2312.06648), [RAPTOR](https://arxiv.org/abs/2401.18059), and [Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval). Their inclusion here records an evolution path, not a quality claim for SupportPilot.

## 8. Future embedding and representation candidates

| ID | Candidate | Intended benefit | Trigger to implement | Additional test burden |
|---|---|---|---|---|
| FE3 | Nomic Embed v1.5 with Matryoshka dimensions | Compare quality, storage, and latency at multiple vector sizes | Index memory or storage becomes material | Prefix correctness, dimension truncation, re-normalization, per-dimension recall |
| FE4 | BGE-M3 | Multilingual dense, sparse, and multi-vector experiments in one model family | Multilingual or multi-representation retrieval becomes a requirement | Mode isolation, 1024-dimension storage, long-input limits, language-stratified evaluation |
| FE5 | Qwen3 Embedding 0.6B | Long-context multilingual instruction-aware retrieval | More CPU/memory is acceptable and multilingual quality is needed | Resource limits, instruction versioning, selectable dimensions, cold-start measurement |
| FE6 | SPLADE learned sparse retrieval | Neural lexical expansion beyond standard full-text search | Dense plus PostgreSQL lexical retrieval misses domain terminology | Sparse-vector storage, pruning, fusion fairness, interpretability and latency tests |
| FE7 | ColBERT-style late interaction | Token-level relevance beyond one vector per chunk | Correct evidence enters the candidate set but ranks poorly | Multi-vector storage, MaxSim correctness, candidate generation, compression, latency |
| FE8 | Multiple vectors per chunk | Retrieve through source text, title, summary, or synthetic questions | One representation cannot cover recurring query styles | View provenance, deduplication, fusion, storage multiplier, generated-view validation |
| FE9 | Hosted embedding adapter | Reduce local image size or improve measured quality | Local cold start or CPU indexing violates deployment targets | Provider terms, privacy, retry/idempotency, quotas, cost accounting, fallback behavior |
| FE10 | Domain-adapted embedding | Improve support-domain retrieval with hard negatives | Several hundred reviewed queries and negatives exist | Train/eval separation, leakage checks, model registry, reproducible training, rollback |
| FE11 | Multimodal page embeddings | Retrieve diagrams, screenshots, or scanned visual evidence | Multimodal documents become supported | Image/text alignment, page-region citations, model terms, storage, safety evaluation |

Relevant model families include [Nomic Embed v1.5](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5), [BGE-M3](https://huggingface.co/BAAI/bge-m3), and [Qwen3 Embedding 0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B). Learned sparse and late-interaction approaches are represented by [SPLADE v2](https://arxiv.org/abs/2109.10086) and [ColBERTv2](https://arxiv.org/abs/2112.01488).

## 9. Initial experiment sequence

The lab uses staged comparison to isolate variables and avoid an unnecessary full grid.

### Stage A - Chunking

Hold E0 constant:

| Run | Chunker | Embedder |
|---|---|---|
| A0 | C0 | E0 |
| A1 | C1 | E0 |
| A2 | C2 | E0 |

Review aggregate metrics, per-category results, and chunk/citation diagnostics. Select the best two chunking candidates for the finalist stage.

### Stage B - Embedding

Hold the best Stage A chunker constant:

| Run | Chunker | Embedder |
|---|---|---|
| B0 | Stage A winner | E0 |
| B1 | Stage A winner | E1 |
| B2 | Stage A winner | E2 |

### Stage C - Interaction check

Run the second-best Stage A chunker with the best Stage B embedder. If its important-category results reverse the Stage A ordering, run the remaining finalist combination before making a decision.

No profile is selected automatically. The final choice requires a documented human review.

## 10. Evaluation dataset criteria

The initial dataset contains 50 human-reviewed cases. Cases may carry multiple tags, but the set should cover at least:

| Category | Minimum cases | Purpose |
|---|---:|---|
| Direct single-source lookup | 10 | Basic evidence retrieval |
| Semantic paraphrase | 8 | Dense retrieval contribution |
| Exact identifier, product name, or error code | 6 | Lexical retrieval contribution |
| Evidence spanning multiple chunks or sections | 6 | Boundary and context behavior |
| Ambiguous question | 4 | Avoid misleading evidence ranking |
| Unanswerable question | 4 | Observe false-positive evidence behavior before Week 4 abstention |
| Superseded or conflicting document version | 4 | Active-version correctness |
| Cross-workspace or adversarial retrieval attempt | 4 | Tenant isolation and filter correctness |
| Structure-sensitive list, heading, or procedure | 4 | C1/C2 behavior |

The corpus must include PDF, Markdown, HTML, and text. Labels identify acceptable immutable document versions and source spans, not generated chunk IDs. A retrieved chunk is relevant when its locator contains or meaningfully overlaps an approved evidence span according to a versioned scoring rule.

The dataset must not be used to train or tune an embedding model. Parameter choices informed by the dataset must be recorded, and final claims must acknowledge that the same small set influenced selection.

### 10.1 Separate complex challenge set

The reviewed `week3-apple-suite-v2-reviewed` dataset contains the stable 50-case baseline
and a 20-case challenge group. The challenge group has 19 answerable cases and one
false-premise unanswerable case. Fourteen challenge cases were corrected during human review
to replace headings, fragments, irrelevant passages, and unsupported requirements with
answer-supporting spans. The baseline cases were not changed.

Challenge reporting adds evidence-span Recall@5, all-required-evidence Recall@5 and Recall@10,
and citation coverage at both cutoffs. A query that retrieves one relevant passage but misses
the remaining required passages is counted as partial, not complete.

Human review follows the [Week 3 challenge-set review guide](week-3-challenge-review-guide.md).

### 10.2 Lexical scorer calibration boundary

The September 10 lexical revision replaces the reference word-frequency score and PostgreSQL
all-terms query with one deterministic BM25 implementation. It removes common question words,
keeps original and conservative suffix variants, preserves numeric and punctuation-bearing
identifiers, applies corpus-level inverse-document frequency, rewards adjacent query terms,
and includes trusted heading paths and document titles at lower weights than source text.

For exact lab equivalence, the PostgreSQL adapter loads the tenant-scoped, active,
profile-scoped chunks and applies the same application scorer. This is acceptable for the
small evaluation corpus but is not the production scaling design. After a strategy is selected,
the production branch must reproduce the approved ranking with a bounded SQL candidate query,
stored statistics, or a proven BM25 extension before using a large corpus.

## 11. Test criteria

### 11.1 Hard eligibility gates

A candidate combination cannot be selected unless all of these pass:

1. Zero cross-workspace results in API, direct restricted-role, and evaluation tests.
2. Every returned result belongs to the requested workspace, an active document, and the active immutable version.
3. All returned citation locators resolve to stored source blocks and remain within the cited document version.
4. Chunking is deterministic for identical input and configuration.
5. Query and document embedding preprocessing matches the candidate profile exactly.
6. Repeated processing is idempotent and does not create duplicate visible chunks.
7. Malformed or empty input fails without activating a partial index.
8. Raw source content, embedding values, credentials, paths, and provider payloads are absent from general logs.
9. The candidate's model license and immutable revision are recorded.
10. The complete run is reproducible from approved fixtures with runtime model downloads disabled.

### 11.2 Quality gates

For production eligibility on the initial 50 cases:

- Recall@5 is at least 0.80 overall.
- MRR is at least 0.70 overall.
- Cross-workspace retrieval count is zero.
- Citation locator resolution is 100% for returned results.
- No critical exact-identifier, active-version, or tenant-isolation category has an unexplained regression relative to the control.

Also report Recall@1, nDCG@5, citation-span coverage, dense-only and lexical-only branch recall, RRF contribution, and per-category results. A candidate that misses a numeric gate is not promoted merely because it has the highest score among weak candidates.

### 11.3 Reliability tests

- Worker lease renewal during parsing and embedding.
- Stale-worker rejection before final persistence or activation.
- Retry after parsing, embedding, database, or cancellation failure.
- Previous active version remains searchable until the new complete selected index commits.
- Duplicate job and repeated profile execution produce one visible index result.
- Deleted and superseded versions disappear from retrieval without orphaned visible chunks.
- Model-load failure and offline-cache failure produce bounded safe error codes.

The lab may simulate these behaviors, but the selected production implementation must repeat them against the real PostgreSQL job and tenant context.

### 11.4 Performance and resource measurements

For every candidate, record:

- Cold model-load time and peak memory.
- Warm indexing duration per document and per 1,000 source tokens.
- Embedding batch throughput.
- Number of chunks and total embedded tokens.
- Vector bytes and total derived-storage estimate.
- Warm retrieval p50 and p95 latency across the complete query set.
- End-to-end API retrieval latency separately from in-process retrieval time.
- Production image-size impact and model-cache size.

The initial experiment has no universal latency winner gate, but a candidate must disclose any material regression. The final manual decision must explain a quality gain that justifies higher latency, memory, storage, or packaging cost.

### 11.5 Statistical and manual review

- Run every query against every compared candidate using the same order or a documented randomized order with a fixed seed.
- Warm each model before warm-latency measurement.
- Repeat timing runs and report the aggregation method.
- Report per-query win, tie, and loss counts against C0+E0.
- Inspect every disagreement on tenant isolation, active version, exact identifiers, and citations.
- Inspect at least the ten largest ranking disagreements between finalists.
- Treat close aggregate scores as inconclusive when failures and paired results do not show a meaningful difference.

No weighted composite score automatically selects the winner. The manual decision priority is:

1. Security and active-version correctness.
2. Citation validity and evidence coverage.
3. Retrieval quality on important categories.
4. Reliability and reproducibility.
5. Latency, memory, storage, image size, and implementation simplicity.

## 12. Full lab validation gates

Before the lab result can be frozen and tagged:

- Candidate contract tests pass.
- Parser and source-locator tests pass.
- Lab PostgreSQL schema upgrades and downgrades if the lab introduces migrations.
- Exact semantic, lexical, and RRF ranking functions pass deterministic fixtures.
- Tenant-isolation tests pass for every experimental derived table.
- The 50-case dataset passes schema and reference validation.
- Every scheduled run completes or has a documented bounded failure.
- The comparison report identifies profile and code fingerprints.
- The working tree contains no model caches, generated vectors, database dumps, or unapproved source files.
- Existing repository lint, type, and test gates remain green for any shared code changed by the lab.

## 13. Manual selection record

The September 10 reviewed matrix executed every C0-C2 by E0-E2 combination over all 70
cases with `bm25-structural-v1`, exact cosine search, deterministic RRF, top 10 results, zero
embedding truncation, and zero cross-workspace results. The complete measurements and
trade-off analysis are recorded in the
[Week 3 RAG strategy selection report](week-3-rag-selection-report.md).

**C1+E1 is selected.** C1 is structure-aware recursive chunking with a 350-token target,
500-token hard maximum, approximately 60-token overlap, and heading, paragraph, sentence,
then token fallback boundaries. E1 is the pinned 384-dimensional
`snowflake/snowflake-arctic-embed-xs` adapter with its recorded query prefix, CLS pooling,
normalization, revision, and Apache-2.0 license.

C1+E1 achieved the highest overall Recall@5 (0.889), Complete@10 (0.810), Citation@5
(0.808), and Citation@10 (0.871), while tying the best Complete@5 (0.714). C0+E1 remains
the efficiency reference because it has fewer chunks, lower retrieval latency, and better
MRR and nDCG@5. The selection accepts C1+E1's additional local storage and latency for
better evidence completeness, citation coverage, and structure-preserving source units in
the current personal, local-use deployment.

The selection record is:

```yaml
experiment_tag: rag-strategy-evaluation-v2-reviewed
evaluated_commit: 8fcdba733b26301b9a1553fabf73d4a37b1effb0
dataset_version: week3-apple-suite-v2-reviewed
fixed_retrieval_config: bm25-structural-v1 + exact-cosine + rrf-60
selected_candidate: C1+E1
selected_profile_fingerprint: 430c6c3fbd841e744e3bc9b95a248fa4a5ef85ccc367e20744599ec2f45a9f7c
decision_owner: project owner
decision_date: 2026-09-10
```

The evaluated commit is the frozen functional implementation used by all nine final reports.
The immutable tag must point to the later evidence commit that records this decision. Raw corpus files, model
weights, generated vectors, and raw result JSON remain excluded from Git.

## 14. Production-transfer equivalence tests

The production branch must not assume that copied code behaves like the lab. Before merge into `main`, compare the selected lab profile with the standalone production implementation:

- Identical canonical parsed blocks and locators for approved fixtures.
- Identical original chunks and embedding-input text.
- Equivalent embeddings within a documented tolerance.
- Identical exact-search ordering with deterministic tie handling.
- Equivalent lexical and fused ranking.
- Quality metrics within an explicitly accepted tolerance.
- Same query/document preprocessing, normalization, and distance function.
- Same active-version and tenant filters.

The production branch then adds and tests the selected-dimension HNSW index. HNSW Recall@5 must be at least 95% relative to exact search on the evaluation corpus; otherwise production remains on exact search and records the deviation.

## 15. Exit conditions

This lab cycle ends when:

1. The initial scheduled candidates have been implemented or explicitly marked skipped with a reason.
2. The complete documented experiment sequence has run reproducibly.
3. A human has selected one combination and signed the decision record.
4. The evaluated commit has been pushed and tagged.
5. A clean production branch has been created from `main`.
6. Only the selected solution and approved reusable work have been transferred.
7. The standalone production pipeline passes the equivalence, quality, reliability, security, migration, API, browser, container, and coverage gates.

Future candidates remain in this catalog until their trigger is observed. They do not delay the Week 3 decision and are not implied production commitments.
