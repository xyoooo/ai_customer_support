# RAG strategy experiment workspace

This directory contains approved, non-production inputs for the switchable Week 3 lab. Generated reports and model caches are ignored by Git.

The tracked `benchmarks/week3-apple-suite-v2-reviewed.manifest.json` records the immutable
hash and provenance of the selected local benchmark without redistributing its questions,
source text, downloaded PDFs, synthetic fixture bodies, or model files.

## Install the isolated lab dependencies

```powershell
uv sync --group dev --group rag-lab
```

## Explicitly cache a pinned model

Normal experiment runs are offline-only. Model acquisition is a separate explicit step:

```powershell
uv run python scripts/cache_rag_model.py E0 --model-root experiments/rag/model-cache
```

The cache command downloads the exact artifact revision from the candidate profile and writes a `supportpilot-model.json` manifest. The runner rejects missing or mismatched manifests.

## Run one profile

```powershell
uv run python scripts/run_rag_experiment.py `
  --dataset experiments/rag/example/dataset.json `
  --corpus-root experiments/rag/example/corpus `
  --chunker C0 `
  --embedder E0 `
  --model-root experiments/rag/model-cache `
  --code-revision 65ff36b `
  --output experiments/rag/results/C0-E0.json
```

The example dataset is only a smoke fixture. It intentionally fails `--strict-dataset` and must never support a quality or selection claim.

## Compare completed reports

```powershell
uv run python scripts/compare_rag_experiments.py `
  experiments/rag/results/C0-E0.json `
  experiments/rag/results/C1-E0.json `
  --output experiments/rag/results/stage-a.md
```

The comparison records paired wins, ties, losses, quality, citations, and latency. It never selects a winner automatically.

## Run and summarize a candidate matrix

`scripts/run_rag_matrix.py` parses a shared corpus once and reuses each local embedding model
across chunkers. `scripts/summarize_rag_suite.py` can then report stable baseline and separate
challenge groups from the same immutable run. Normal profiles validate chunks against all
candidate tokenizers and reject overflow; they do not silently truncate source content.

The lab lexical branch uses the application-owned `bm25-structural-v1` scorer for both the
in-memory and PostgreSQL adapters. The PostgreSQL path intentionally scores the complete
tenant/profile-scoped active corpus for exact experiment parity; replace this with a bounded,
equivalence-tested SQL candidate stage before production-scale use.

