# ADR 0006: Evaluate RAG strategies in a lab branch and productionize one selected pipeline

- Status: accepted
- Date: 2026-07-22

## Context

Week 3 must choose chunking and embedding strategies for SupportPilot. Chunk boundaries, context enrichment, query/document preprocessing, embedding model, vector dimension, and normalization can materially affect retrieval quality, citation coverage, latency, storage, and packaging.

Selecting a combination before measuring it would make the production design depend on an assumption. Conversely, merging every candidate and a permanent runtime switch into the product would add unused dependencies, mixed-dimension storage, configuration states, operational paths, and tests to `main`.

SupportPilot therefore needs a boundary between a flexible comparison environment and the single RAG pipeline that will serve the product. This ADR decides how experimentation, manual selection, code transfer, production validation, and future strategy changes are separated.

## Decision drivers

- Compare chunking and embedding candidates under identical, reproducible conditions.
- Keep the production codebase small, explainable, and limited to one selected pipeline.
- Prevent losing models and experimental dependencies from entering the production image.
- Preserve tenant isolation, citation provenance, worker recovery, and activation safety during productionization.
- Avoid approximate vector-index behavior influencing the strategy-quality comparison.
- Retain enough evidence to explain and reproduce the manual selection.
- Allow future experiments without turning the current product into a permanent strategy platform.

## Options comparison

### Strategy-selection workflow

| Option | Advantages | Limitations |
|---|---|---|
| Choose one strategy before implementation | Smallest initial implementation and fastest path to a demo | No project-specific evidence; later comparison requires redesign and re-indexing |
| Implement and merge a runtime-switchable strategy platform | Alternatives remain available in production; easy online switching | Enlarges schema, dependencies, configuration space, security surface, packaging, and regression matrix for unused capabilities |
| Evaluate candidates in an isolated lab branch and manually productionize one selected solution | Fair comparison and a simple production result; losing code and dependencies remain isolated | Requires disciplined commits, a manual selection gate, and independent validation after transferring the winner |
| Maintain separate production branch per strategy | Each candidate can be deployed independently | Branches diverge in shared parsing, security, schema, and worker behavior; comparisons become confounded and maintenance grows |

### Retrieval during comparison

| Option | Advantages | Limitations |
|---|---|---|
| HNSW for every candidate | Closer to a possible production deployment | Approximation, filtering behavior, and dimension-specific indexes can distort candidate comparison |
| Separate optimized retrieval stack per candidate | Lets every model use its preferred infrastructure | Measures whole-stack differences rather than the chunker/embedder variables |
| Exact vector search with fixed lexical retrieval and RRF | Deterministic, fair across supported dimensions, and suitable for the small evaluation corpus | Does not measure final approximate-index performance |

### Transferring the result

| Option | Advantages | Limitations |
|---|---|---|
| Merge the lab branch and delete losing code afterward | Straightforward Git operation | Imports all experimental history and risks retaining dependencies, configuration, migrations, or dead paths |
| Create a clean production branch from `main` and transfer only shared work and the selected solution | Clean production history and explicit scope; easiest to audit | Requires separated lab commits or deliberate reimplementation |
| Keep the lab branch as the production branch | No transfer work | `main` no longer represents the stable product and retains the experiment platform |

## Decision

Use `codex/week3-rag-strategy-lab` to compare chunking and embedding strategies. The lab branch will contain candidate registries, switchable profiles, mixed-dimension experimental persistence, exact vector retrieval, comparison tooling, candidate-specific dependencies, and diagnostic reports.

The initial lab compares:

- Fixed-token, structure-aware recursive, and structure-aware deterministic-context chunking.
- `BAAI/bge-small-en-v1.5`, `Snowflake/snowflake-arctic-embed-xs`, and `jinaai/jina-embeddings-v2-small-en`.
- A fixed PostgreSQL lexical retrieval and deterministic RRF configuration.
- Exact cosine search for semantic candidates.

A human will review aggregate metrics, per-category metrics, paired query results, citation-span coverage, failures, indexing time, latency, storage, packaging, and operational fit. The human will record one selected combination; the decision is not made automatically from a single aggregate score.

The lab branch will not merge into `main`. After selection:

1. Push the evaluated lab commit and preserve it with an immutable tag.
2. Create `codex/week3-rag-production` from clean `main`.
3. Transfer only canonical parsing work, the selected chunker, the selected embedding adapter, and the code required for one production indexing/retrieval pipeline.
4. Use a selected-dimension production schema and vector index.
5. Rerun the selected evaluation outside the lab harness.
6. Merge the production branch only after all product, security, migration, worker, retrieval, and quality gates pass.

`main` will contain one versioned RAG pipeline and will not expose a customer, administrator, or runtime strategy switch. It will record the selected chunker parameters, embedding model revision, preprocessing, vector dimension, normalization, and pipeline version so derived data remains reproducible. A future strategy change creates a new pipeline version and explicit re-indexing work.

The concise evaluation report and reviewed regression dataset enter `main`; alternative implementations, the experiment registry, candidate profiles, raw traces, model weights, caches, generated embeddings, and losing dependencies do not.

## Why this suits the current stage

SupportPilot has one developer, a small corpus target, a 50-question initial evaluation set, a CPU-local and low-cost operating goal, and no requirement for customers to select retrieval strategies. The primary need is to make an evidence-based choice without converting a portfolio product into a research platform.

An isolated lab can be flexible enough to compare models with different dimensions and preprocessing rules. Exact pgvector retrieval is adequate for the small corpus and removes HNSW approximation from the quality decision. Creating the production branch from `main` afterward keeps the final system easy to explain: one parser path, one chunker, one embedder, one index layout, and one retrieval policy.

Manual selection is intentional. A small aggregate score can hide failures in exact identifiers, multi-chunk questions, citations, or important document types. Human review can weigh those failures alongside latency, image size, model licensing, and operational simplicity.

## Consequences

### Advantages accepted

- Candidate comparison does not permanently enlarge the production architecture.
- Losing models and their dependencies stay out of the production image.
- Mixed embedding dimensions do not force a generic production index design.
- `main` contains a single pipeline that is easier to test, operate, document, and explain.
- The selected result is independently verified after leaving the experiment harness.
- Future experiments can start from the latest production baseline without exposing switches to users.

### Limitations accepted

- Productionizing the winner requires a separate transfer and validation phase.
- Lab and production implementations can drift unless equivalence tests compare chunks, preprocessing, vectors, and rankings.
- A long-lived lab branch can become stale and must be refreshed from `main` before later experiments.
- Alternatives cannot be activated immediately in production; a new winner requires a new pipeline version and re-indexing.
- The initial 50-case dataset limits statistical confidence, so close results may remain inconclusive.
- Manual selection requires an explicit written rationale and cannot be represented as universally optimal.

## When to reconsider

Reconsider a permanent strategy/profile platform in `main` when one or more of these conditions is demonstrated:

- Different workspaces require different languages, document types, embedding providers, or retrieval policies as a product feature.
- Online A/B testing or canary rollout of retrieval profiles becomes necessary and has an approved exposure model.
- Strategy changes occur frequently enough that repeated clean-branch productionization and full re-indexing materially slows delivery.
- Multiple pipelines must coexist during a controlled migration or rollback window beyond a single version transition.
- The team grows and takes ownership of a maintained retrieval experimentation platform with dedicated compatibility and security tests.

Until then, future comparisons run in a refreshed lab branch based on current `main`. Only a manually selected, independently validated, versioned pipeline is promoted into the production codebase.
