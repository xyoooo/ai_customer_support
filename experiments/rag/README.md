# RAG strategy experiment workspace

This directory contains approved, non-production inputs for the switchable Week 3 lab. Generated reports and model caches are ignored by Git.

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

