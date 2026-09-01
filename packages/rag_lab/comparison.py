from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True, slots=True)
class ComparisonRow:
    profile_id: str
    fingerprint: str
    recall_at_5: float
    mean_reciprocal_rank: float
    ndcg_at_5: float
    citation_span_coverage: float
    retrieval_p95_ms: float
    wins: int
    ties: int
    losses: int


def _load_report(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"experiment report could not be loaded: {path}") from exc
    if payload.get("report_schema") != "rag-lab-report-v1":
        raise ValueError(f"unsupported experiment report: {path}")
    return cast(dict[str, Any], payload)


def _first_relevant_rank(query: dict[str, Any]) -> int | None:
    ranks = query["relevant_ranks"]
    return min(ranks) if ranks else None


def compare_reports(paths: list[Path]) -> tuple[ComparisonRow, ...]:
    if len(paths) < 2:
        raise ValueError("comparison requires at least two experiment reports")
    reports = [_load_report(path) for path in paths]
    dataset_versions = {report["profile"]["dataset_version"] for report in reports}
    retrieval_profiles = {
        json.dumps(report["profile"]["retrieval"], sort_keys=True) for report in reports
    }
    if len(dataset_versions) != 1 or len(retrieval_profiles) != 1:
        raise ValueError("reports must share the same dataset and retrieval configuration")
    baseline_queries = {query["case_id"]: query for query in reports[0]["queries"]}
    rows = []
    for report in reports:
        queries = {query["case_id"]: query for query in report["queries"]}
        if queries.keys() != baseline_queries.keys():
            raise ValueError("reports do not contain the same evaluation cases")
        wins = ties = losses = 0
        for case_id, baseline in baseline_queries.items():
            baseline_rank = _first_relevant_rank(baseline)
            candidate_rank = _first_relevant_rank(queries[case_id])
            baseline_value = baseline_rank if baseline_rank is not None else 10**9
            candidate_value = candidate_rank if candidate_rank is not None else 10**9
            if candidate_value < baseline_value:
                wins += 1
            elif candidate_value > baseline_value:
                losses += 1
            else:
                ties += 1
        quality = report["quality"]
        resources = report["resources"]
        rows.append(
            ComparisonRow(
                profile_id=report["profile"]["profile_id"],
                fingerprint=report["profile_fingerprint"],
                recall_at_5=quality["recall_at_5"],
                mean_reciprocal_rank=quality["mean_reciprocal_rank"],
                ndcg_at_5=quality["ndcg_at_5"],
                citation_span_coverage=quality["citation_span_coverage"],
                retrieval_p95_ms=resources["retrieval_p95_ms"],
                wins=wins,
                ties=ties,
                losses=losses,
            )
        )
    return tuple(rows)


def render_markdown(rows: tuple[ComparisonRow, ...]) -> str:
    lines = [
        "# RAG strategy comparison",
        "",
        "This table is diagnostic evidence only; it does not select a winner automatically.",
        "",
        "| Profile | Recall@5 | MRR | nDCG@5 | Citation coverage | p95 ms | W/T/L vs control |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend(
        f"| {row.profile_id} | {row.recall_at_5:.3f} | "
        f"{row.mean_reciprocal_rank:.3f} | {row.ndcg_at_5:.3f} | "
        f"{row.citation_span_coverage:.3f} | {row.retrieval_p95_ms:.2f} | "
        f"{row.wins}/{row.ties}/{row.losses} |"
        for row in rows
    )
    lines.extend(
        [
            "",
            "Manual review must still apply the security, citation, quality, reliability, "
            "and resource priorities documented in the lab specification.",
            "",
        ]
    )
    return "\n".join(lines)
