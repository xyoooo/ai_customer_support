from __future__ import annotations

import argparse
from pathlib import Path

from packages.rag_lab.comparison import compare_reports, render_markdown


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare RAG reports without automatically selecting a winner."
    )
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = compare_reports(args.reports)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_markdown(rows), encoding="utf-8")
    print(f"Wrote comparison to {args.output}")


if __name__ == "__main__":
    main()
