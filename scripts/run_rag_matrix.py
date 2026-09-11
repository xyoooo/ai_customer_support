from __future__ import annotations

import argparse
from pathlib import Path

from packages.rag_lab.chunking import build_chunker
from packages.rag_lab.dataset import EvaluationDataset
from packages.rag_lab.embeddings import FastEmbedAdapter
from packages.rag_lab.evaluation import ExperimentRunner
from packages.rag_lab.profiles import CANDIDATES, RetrievalSpec, build_profile
from packages.rag_lab.token_budget import SharedModelInputBudget


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a reusable local RAG candidate matrix.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--chunkers", nargs="+", choices=sorted(CANDIDATES.chunkers))
    parser.add_argument("--embedders", nargs="+", choices=sorted(CANDIDATES.embeddings))
    parser.add_argument("--result-count", type=int, default=10)
    parser.add_argument("--threads", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = EvaluationDataset.load(args.dataset)
    budget = SharedModelInputBudget.from_model_root(
        args.model_root,
        tuple(CANDIDATES.embeddings.values()),
    )
    chunker_ids = args.chunkers or sorted(CANDIDATES.chunkers)
    embedding_ids = args.embedders or sorted(CANDIDATES.embeddings)
    runner = ExperimentRunner()
    retrieval = RetrievalSpec(result_count=args.result_count)
    for embedding_id in embedding_ids:
        embedding_spec = CANDIDATES.embedding(embedding_id)
        embedder = FastEmbedAdapter(
            embedding_spec,
            model_path=args.model_root / embedding_id,
            threads=args.threads,
        )
        for chunker_id in chunker_ids:
            profile = build_profile(
                chunker_id,
                embedding_id,
                dataset_version=dataset.dataset_version,
                code_revision=args.code_revision,
                retrieval=retrieval,
            )
            report = runner.run(
                dataset=dataset,
                corpus_root=args.corpus_root,
                profile=profile,
                chunker=build_chunker(profile.chunker, budget=budget),
                embedder=embedder,
            )
            output = args.output_dir / f"{chunker_id}-{embedding_id}.json"
            report.write(output)
            print(f"Wrote {profile.profile_id} report to {output}", flush=True)


if __name__ == "__main__":
    main()
