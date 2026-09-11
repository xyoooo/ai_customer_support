# Week 3 RAG strategy selection report

- Date: September 10, 2026
- Dataset: `week3-apple-suite-v2-reviewed`
- Evaluated commit: `8fcdba733b26301b9a1553fabf73d4a37b1effb0`
- Selected profile fingerprint: `430c6c3fbd841e744e3bc9b95a248fa4a5ef85ccc367e20744599ec2f45a9f7c`
- Corpus: 3 Apple PDFs plus 3 synthetic lifecycle/isolation fixtures
- Cases: 70 total, including 20 challenge cases and 1 unanswerable challenge case
- Retrieval: exact cosine dense search, `bm25-structural-v1`, deterministic reciprocal-rank fusion, top 10
- Decision: **C1+E1** selected for the production prototype
- Production handoff: [Week 3 production handoff plan](week-3-production-handoff.md)

## Dataset review

The reviewed dataset is stored locally under `var/rag-evals/apple` and remains excluded
from Git with the downloaded corpus. Its source-free
[benchmark manifest](../experiments/rag/benchmarks/week3-apple-suite-v2-reviewed.manifest.json)
records the immutable dataset hash, case counts, public acquisition URLs, and all six
corpus hashes. Fourteen challenge cases were corrected without
changing any baseline case. The changes replace headings, sentence fragments, irrelevant
passages, and unsupported requirements with answer-supporting spans. Questions 002 and
008 were reframed during human review, and other artificial combinations were retained
only where they still exercise a useful retrieval behavior.

All 70 cases, document references, source block identifiers, and character boundaries
validate against the current parser and corpus.

## Candidate definitions

- C0: fixed 350-token chunks with 60-token overlap and PDF page boundaries.
- C1: structure-aware recursive chunks using headings, paragraphs, sentences, and token fallback.
- C2: C1 source chunks with document-title and heading-path context added only to embedding input.
- E0: BAAI BGE Small English v1.5, 384 dimensions.
- E1: Snowflake Arctic Embed XS, 384 dimensions.
- E2: Jina Embeddings v2 Small English, 512 dimensions.

## Full result

| Profile | Recall@5 | Complete@5 | Complete@10 | MRR | nDCG@5 | Citation@5 | Citation@10 | p95 ms | Chunks | Vector MiB | Truncated |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C0+E0 | 0.825 | 0.683 | 0.762 | 0.674 | 0.582 | 0.744 | 0.835 | 140.4 | 715 | 1.05 | 0 |
| C0+E1 | 0.857 | 0.698 | 0.794 | **0.691** | **0.602** | 0.787 | 0.854 | 140.8 | 715 | 1.05 | 0 |
| C0+E2 | 0.841 | **0.714** | 0.746 | 0.674 | 0.588 | 0.789 | 0.814 | 171.5 | 715 | 1.40 | 0 |
| C1+E0 | 0.841 | 0.635 | 0.778 | 0.645 | 0.552 | 0.741 | 0.843 | 205.0 | 1,091 | 1.60 | 0 |
| **C1+E1** | **0.889** | **0.714** | **0.810** | 0.669 | 0.584 | **0.808** | **0.871** | 172.8 | 1,091 | 1.60 | 0 |
| C1+E2 | 0.825 | 0.698 | 0.746 | 0.664 | 0.562 | 0.758 | 0.830 | 212.6 | 1,091 | 2.13 | 0 |
| C2+E0 | 0.857 | 0.667 | 0.794 | 0.653 | 0.561 | 0.753 | 0.856 | 184.6 | 1,091 | 1.60 | 0 |
| C2+E1 | 0.873 | 0.698 | 0.746 | 0.656 | 0.572 | 0.779 | 0.829 | 173.5 | 1,091 | 1.60 | 0 |
| C2+E2 | 0.810 | 0.683 | 0.730 | 0.643 | 0.555 | 0.742 | 0.811 | 234.8 | 1,091 | 2.13 | 0 |

Complete@K requires every labelled evidence span for an answerable case to occur within
the first K results. Citation@K measures the proportion of labelled source characters
covered by those results.

## Baseline and challenge result

| Profile | Baseline Recall@5 | Baseline Complete@10 | Challenge Recall@5 | Challenge Complete@5 | Challenge Complete@10 | Challenge Citation@10 |
|---|---:|---:|---:|---:|---:|---:|
| C0+E0 | 0.818 | 0.795 | 0.842 | 0.474 | 0.684 | 0.800 |
| C0+E1 | 0.886 | 0.841 | 0.789 | 0.474 | 0.684 | 0.783 |
| C0+E2 | 0.841 | 0.773 | 0.842 | **0.579** | 0.684 | 0.798 |
| C1+E0 | 0.818 | 0.818 | **0.895** | 0.421 | 0.684 | **0.825** |
| **C1+E1** | **0.909** | **0.864** | 0.842 | 0.526 | 0.684 | 0.787 |
| C1+E2 | 0.864 | 0.818 | 0.737 | 0.526 | 0.579 | 0.720 |
| C2+E0 | 0.841 | 0.841 | **0.895** | 0.474 | 0.684 | 0.815 |
| C2+E1 | 0.886 | 0.795 | 0.842 | 0.474 | 0.632 | 0.771 |
| C2+E2 | 0.841 | 0.795 | 0.737 | 0.526 | 0.579 | 0.710 |

## Selection judgment

C1+E1 is selected for the next production prototype because it has the best overall
Recall@5, Complete@10, Citation@5, and Citation@10, while tying the best Complete@5.
It also has the strongest baseline Recall@5 and Complete@10. C1 preserves source
structure and citation-friendly boundaries, while E1 provides the strongest overall
embedding quality without increasing vector dimension over E0.

C0+E1 is the closest efficiency alternative. It has better MRR and nDCG@5, uses 715
rather than 1,091 chunks, and has a 140.8 ms rather than 172.8 ms retrieval p95. The
selected C1+E1 profile accepts that cost for higher evidence completeness and citation
coverage. This trade is reasonable for the current personal, non-commercial, local-use
scope; it should be revisited if corpus size or concurrent traffic grows substantially.

The local model caches occupy approximately 64.3 MiB for E0, 385.6 MiB for E1, and
457.7 MiB for E2. E1's larger artifact is an accepted local-storage cost; its 384-dimensional
index remains the same size per chunk as E0 and smaller than E2's 512-dimensional index.

C2 is not selected because adding title and heading context did not improve C1 with E1.
E2 is not selected because its 512-dimensional vectors, larger local artifact, and higher
latency did not produce better quality. E0 remains a useful small-footprint fallback.

## Remaining failure pattern

C1+E1 does not retrieve complete top-10 evidence for challenge cases 007, 009, 010,
011, 015, and 019. Most require evidence from distant sections or different documents.
The same six cases fail for most leading profiles, so changing the embedding model again
is unlikely to solve them. Future experiments should evaluate query decomposition,
per-subquery retrieval, and bounded parent/neighbor expansion rather than enlarging the
initial production scope.

Challenge 018 asks for unknowable personal spyware details. A fixed top-k retriever will
still return related passages; correct handling belongs to answerability and grounded
generation evaluation, not a rule that requires zero retrieval results.

## Decision limits

This is a selection for the current Apple-heavy corpus, reviewed retrieval dataset, local
CPU runtime, and fixed hybrid scorer. It is not a universal model ranking. Results are
from one full matrix run and do not yet measure generated-answer faithfulness, answer
safety, or end-to-end user latency. The lab branch remains the experiment environment;
only C1, E1, the shared parser and scorer behavior, required storage, and regression tests
should be transferred to the clean production branch.
