from __future__ import annotations

import argparse
from pathlib import Path

from packages.rag_lab.chunking import build_chunker
from packages.rag_lab.dataset import EvaluationDataset
from packages.rag_lab.embeddings import FastEmbedAdapter
from packages.rag_lab.evaluation import ExperimentRunner
from packages.rag_lab.profiles import CANDIDATES, build_profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one immutable RAG strategy profile.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--chunker", choices=sorted(CANDIDATES.chunkers), required=True)
    parser.add_argument("--embedder", choices=sorted(CANDIDATES.embeddings), required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strict-dataset", action="store_true")
    parser.add_argument("--threads", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = EvaluationDataset.load(args.dataset)
    if args.strict_dataset:
        dataset.validate_strict_coverage()
    profile = build_profile(
        args.chunker,
        args.embedder,
        dataset_version=dataset.dataset_version,
        code_revision=args.code_revision,
    )
    chunker = build_chunker(profile.chunker)
    embedder = FastEmbedAdapter(
        profile.embedding,
        model_path=args.model_root / profile.embedding.candidate_id,
        threads=args.threads,
    )
    report = ExperimentRunner().run(
        dataset=dataset,
        corpus_root=args.corpus_root,
        profile=profile,
        chunker=chunker,
        embedder=embedder,
    )
    report.write(args.output)
    print(f"Wrote {profile.profile_id} report to {args.output}")


if __name__ == "__main__":
    main()
