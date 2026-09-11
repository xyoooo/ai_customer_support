# ADR 0007: Use C1+E1 as the single versioned production RAG pipeline

## Context

The Week 3 lab compared nine chunking and embedding combinations on the reviewed
70-case Apple suite. The product now needs one reproducible indexing and retrieval path.
The lab itself is intentionally not a production dependency and is not merged into `main`.

## Decision drivers

- Preserve citation-friendly source boundaries and evidence completeness.
- Keep tenant isolation and active-version activation inside PostgreSQL transactions.
- Run locally without model downloads during API or worker startup.
- Make derived data reproducible and make future model changes explicit.
- Avoid runtime strategy switches, mixed vector dimensions, and losing model dependencies.

## Options comparison

| Option | Advantages | Limitations |
|---|---|---|
| C1 structure-aware chunks plus E1 Snowflake Arctic Embed XS | Best measured Recall@5, Complete@10, Citation@5, and Citation@10; 384-dimensional vectors; source-aligned citations | More chunks and higher latency than C0+E1; larger local model artifact than E0 |
| C0 fixed-token chunks plus E1 | Best MRR and nDCG@5; fewer chunks and lower latency | Lower evidence completeness and citation coverage; boundaries are less meaningful to reviewers |
| C2 contextual chunks plus E1 | Embedding input includes title and heading context | Did not improve C1+E1 and adds a second representation of each passage |
| Keep all candidates switchable | Fast online comparison | Expands the runtime schema, dependencies, configurations, and regression surface |

## Decision

`rag-v1-c1-e1` is the only production pipeline:

- `canonical-parser-v2-layout` creates normalized blocks for PDF, Markdown, HTML, and text.
- C1 uses heading, paragraph, sentence, and token boundaries with a 350-token target,
  500-token maximum, and 60-token overlap. It embeds the original chunk text.
- E1 is `snowflake/snowflake-arctic-embed-xs` at artifact revision
  `d8c86521100d3556476a063fc2342036d45c106f`, with 384 normalized dimensions, a
  512-token input limit, and the recorded query prefix.
- Retrieval combines exact cosine candidates with `bm25-structural-v1` using deterministic
  reciprocal-rank fusion. Exact search is retained for the current small, personal corpus;
  HNSW is not introduced without a filtered-recall benchmark.
- The worker verifies the stored size and SHA-256, renews its lease while indexing, writes
  a complete version index, and activates that version in one transaction.
- The model manifest and tokenizer must exist in the ignored local model cache. Runtime
  downloads and silent truncation fail closed.
- There is no user, administrator, environment, or runtime strategy switch.

A future winner must use a new pipeline version and an explicit re-indexing migration. It
does not mutate the meaning of `rag-v1-c1-e1`.

## Why this suits the current stage

C1+E1 scored Recall@5 0.889, Complete@10 0.810, Citation@5 0.808, and Citation@10
0.871 on the reviewed suite. Its stronger evidence completeness is more useful for the
next grounded-answer stage than C0+E1's modest ranking and latency advantage. Exact search
keeps this first local baseline deterministic while the indexed corpus is small.

## Consequences

- Production contains one parser, chunker, embedding adapter, vector dimension, and
  retrieval policy.
- Other-workspace, inactive-version, deleted-document, and partially indexed chunks are
  excluded from retrieval.
- Local deployment must provision the pinned E1 model cache before indexing or searching.
- E1's approximately 385.6 MiB local artifact and C1's larger chunk count are accepted.
- Six reviewed challenge cases still lack complete top-10 evidence; query decomposition
  and bounded neighbor expansion remain future experiments.

## When to reconsider

Re-run the lab from current `main` when the corpus or question distribution materially
changes, exact retrieval p95 becomes unacceptable, a new model materially improves the
fixed suite, or storage/concurrency makes the current local design impractical. Evaluate
HNSW when active chunks exceed 10,000 or exact dense search becomes a measured bottleneck;
require at least 95% Recall@5 relative to filtered exact search before adoption.
