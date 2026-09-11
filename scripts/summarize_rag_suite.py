from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize named case groups in RAG reports.")
    parser.add_argument("reports", type=Path)
    parser.add_argument("--group", action="append", required=True, metavar="NAME=PREFIX")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _metrics(queries: list[dict[str, Any]]) -> dict[str, float | int]:
    answerable = [query for query in queries if query.get("evidence_spans_total", 0) > 0]
    evidence_total = sum(query["evidence_spans_total"] for query in answerable)
    return {
        "cases": len(queries),
        "answerable": len(answerable),
        "recall5": _mean(
            [float(any(rank <= 5 for rank in query["relevant_ranks"])) for query in answerable]
        ),
        "mrr": _mean(
            [
                1.0 / min(query["relevant_ranks"]) if query["relevant_ranks"] else 0.0
                for query in answerable
            ]
        ),
        "span5": (
            sum(query["evidence_spans_hit_at_5"] for query in answerable) / evidence_total
            if evidence_total
            else 0.0
        ),
        "complete5": _mean([float(query["all_evidence_at_5"]) for query in answerable]),
        "complete10": _mean([float(query["all_evidence_at_10"]) for query in answerable]),
        "citation5": _mean([query["citation_span_coverage"] for query in answerable]),
        "citation10": _mean([query["citation_span_coverage_at_10"] for query in answerable]),
    }


def main() -> None:
    args = parse_args()
    groups = {}
    for raw_group in args.group:
        name, separator, prefix = raw_group.partition("=")
        if not separator or not name or not prefix:
            raise ValueError("groups must use NAME=PREFIX")
        groups[name] = prefix

    reports = []
    for path in sorted(args.reports.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        reports.append(payload)

    lines = [
        "# Week 3 baseline and challenge summary",
        "",
        "These tables are diagnostic evidence and do not select a winner automatically.",
        "",
    ]
    for group_name, prefix in groups.items():
        lines.extend(
            [
                f"## {group_name.title()}",
                "",
                "| Profile | Recall@5 | MRR | Span recall@5 | Complete@5 | Complete@10 | "
                "Citation@5 | Citation@10 | Chunks | Truncated |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for report in reports:
            queries = [query for query in report["queries"] if query["case_id"].startswith(prefix)]
            metrics = _metrics(queries)
            resources = report["resources"]
            profile_id = report["profile"]["profile_id"]
            lines.append(
                f"| {profile_id} | {metrics['recall5']:.3f} | {metrics['mrr']:.3f} | "
                f"{metrics['span5']:.3f} | {metrics['complete5']:.3f} | "
                f"{metrics['complete10']:.3f} | {metrics['citation5']:.3f} | "
                f"{metrics['citation10']:.3f} | {resources['chunk_count']} | "
                f"{resources['truncated_embedding_inputs']} |"
            )
        lines.append("")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote suite summary to {args.output}")


if __name__ == "__main__":
    main()
