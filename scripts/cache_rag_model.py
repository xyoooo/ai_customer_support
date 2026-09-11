from __future__ import annotations

import argparse
import json
from pathlib import Path

from huggingface_hub import snapshot_download

from packages.rag.config import PIPELINE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Explicitly cache the pinned production RAG model for offline use."
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("var/rag-model-cache/E1"),
        help="Directory that will be mounted read-only into the API and worker containers.",
    )
    return parser.parse_args()


def write_manifest(target: Path) -> None:
    manifest = {
        "artifact_id": PIPELINE.embedding_artifact_id,
        "artifact_revision": PIPELINE.embedding_artifact_revision,
        "dimension": PIPELINE.embedding_dimension,
    }
    (target / "supportpilot-model.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    target = args.target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=PIPELINE.embedding_artifact_id,
        revision=PIPELINE.embedding_artifact_revision,
        local_dir=target,
    )
    write_manifest(target)
    print(f"Cached {PIPELINE.version} at {target}")


if __name__ == "__main__":
    main()
