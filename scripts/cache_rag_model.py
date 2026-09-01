from __future__ import annotations

import argparse
import json
from pathlib import Path

from huggingface_hub import snapshot_download

from packages.rag_lab.profiles import CANDIDATES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Explicitly cache one pinned RAG lab model for later offline evaluation."
    )
    parser.add_argument("candidate", choices=sorted(CANDIDATES.embeddings))
    parser.add_argument("--model-root", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spec = CANDIDATES.embedding(args.candidate)
    target = (args.model_root / spec.candidate_id).resolve()
    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=spec.artifact_id,
        revision=spec.artifact_revision,
        local_dir=target,
    )
    manifest = {
        "artifact_id": spec.artifact_id,
        "artifact_revision": spec.artifact_revision,
        "dimension": spec.dimension,
    }
    (target / "supportpilot-model.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Cached {spec.candidate_id} at {target}")


if __name__ == "__main__":
    main()
