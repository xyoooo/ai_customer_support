# Week 3 RAG strategy selection report

- **Dataset:** `week3-apple-suite-v2-reviewed` (70 cases: 50 baseline, 20 challenge)
- **Evaluated lab commit:** `8fcdba733b26301b9a1553fabf73d4a37b1effb0`
- **Selected profile fingerprint:** `430c6c3fbd841e744e3bc9b95a248fa4a5ef85ccc367e20744599ec2f45a9f7c`
- **Decision:** C1+E1 for production pipeline `rag-v1-c1-e1`

The local, Git-ignored dataset and three public Apple PDFs were reviewed before the final
matrix run. C1 is the structure-aware chunker; E1 is the pinned 384-dimensional Snowflake
Arctic Embed XS model. The primary path used exact cosine search, structural BM25, and
deterministic reciprocal-rank fusion.

| Profile | Recall@5 | Complete@10 | MRR | Citation@5 | Citation@10 | p95 ms | Chunks |
|---|---:|---:|---:|---:|---:|---:|---:|
| C0+E0 | 0.825 | 0.762 | 0.674 | 0.744 | 0.835 | 140.4 | 715 |
| C0+E1 | 0.857 | 0.794 | **0.691** | 0.787 | 0.854 | 140.8 | 715 |
| C0+E2 | 0.841 | 0.746 | 0.674 | 0.789 | 0.814 | 171.5 | 715 |
| C1+E0 | 0.841 | 0.778 | 0.645 | 0.741 | 0.843 | 205.0 | 1,091 |
| **C1+E1** | **0.889** | **0.810** | 0.669 | **0.808** | **0.871** | 172.8 | 1,091 |
| C1+E2 | 0.825 | 0.746 | 0.664 | 0.758 | 0.830 | 212.6 | 1,091 |
| C2+E0 | 0.857 | 0.794 | 0.653 | 0.753 | 0.856 | 184.6 | 1,091 |
| C2+E1 | 0.873 | 0.746 | 0.656 | 0.779 | 0.829 | 173.5 | 1,091 |
| C2+E2 | 0.810 | 0.730 | 0.643 | 0.742 | 0.811 | 234.8 | 1,091 |

C1+E1 was selected for evidence completeness and citation coverage. C0+E1 remains the
closest efficiency alternative, but its lower Complete@10 and citation scores matter more
than its latency advantage for the grounded-support use case. C2 did not improve C1 with
E1, and E2's larger vectors did not produce better quality.

The result is specific to the current Apple-heavy corpus, local CPU runtime, fixed hybrid
scorer, and reviewed questions. It is not a universal ranking. Complete top-10 evidence is
still missing for six multi-part challenge cases; future evaluation should focus on query
decomposition and bounded parent/neighbor expansion rather than silently changing this
pipeline.
