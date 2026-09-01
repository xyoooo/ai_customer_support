from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from packages.rag_lab.chunking import StructureAwareChunker, build_chunker
from packages.rag_lab.comparison import compare_reports, render_markdown
from packages.rag_lab.dataset import EvaluationDataset
from packages.rag_lab.embeddings import DeterministicHashAdapter
from packages.rag_lab.evaluation import ExperimentRunner
from packages.rag_lab.profiles import (
    ChunkerSpec,
    EmbeddingSpec,
    ExperimentProfile,
    RetrievalSpec,
    build_profile,
)


def _write_dataset(root: Path) -> EvaluationDataset:
    workspace_a = uuid4()
    workspace_b = uuid4()
    version_a = uuid4()
    version_b = uuid4()
    (root / "returns.md").write_text(
        "# Returns\nInternational returns must be requested within 30 days.\n\nUse code RET-30.",
        encoding="utf-8",
    )
    (root / "decoy.txt").write_text("RET-30 is a private workspace code.", encoding="utf-8")
    payload = {
        "schema_version": "rag-lab-dataset-v1",
        "dataset_version": "tiny-v1",
        "documents": [
            {
                "workspace_id": str(workspace_a),
                "document_id": str(uuid4()),
                "version_id": str(version_a),
                "title": "Returns",
                "media_type": "text/markdown",
                "source_path": "returns.md",
            },
            {
                "workspace_id": str(workspace_b),
                "document_id": str(uuid4()),
                "version_id": str(version_b),
                "title": "Private",
                "media_type": "text/plain",
                "source_path": "decoy.txt",
            },
        ],
        "cases": [
            {
                "case_id": "return-window",
                "workspace_id": str(workspace_a),
                "query": "How long do I have for an international return?",
                "tags": ["semantic_paraphrase"],
                "evidence": [
                    {
                        "version_id": str(version_a),
                        "block_id": "b000001",
                        "char_start": 0,
                        "char_end": 21,
                    }
                ],
            },
            {
                "case_id": "exact-code",
                "workspace_id": str(workspace_a),
                "query": "RET-30",
                "tags": ["exact_identifier"],
                "evidence": [
                    {
                        "version_id": str(version_a),
                        "block_id": "b000002",
                        "char_start": 0,
                        "char_end": 16,
                    }
                ],
            },
            {
                "case_id": "unanswerable",
                "workspace_id": str(workspace_a),
                "query": "What is the lifetime warranty?",
                "tags": ["unanswerable"],
                "evidence": [],
                "unanswerable": True,
            },
        ],
    }
    path = root / "dataset.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return EvaluationDataset.load(path)


def _profile() -> ExperimentProfile:
    chunker = ChunkerSpec(
        candidate_id="C1",
        implementation_version="test",
        target_tokens=40,
        max_tokens=50,
        overlap_tokens=5,
        boundary_policy="test",
        context_policy="original",
    )
    embedding = EmbeddingSpec(
        candidate_id="ETEST",
        provider="test",
        model_id="test/model",
        artifact_id="test/artifact",
        artifact_revision="a" * 40,
        dimension=32,
        input_limit=100,
        pooling="mean",
        normalized=True,
        query_prefix="",
        document_prefix="",
        license="MIT",
    )
    return ExperimentProfile(
        schema_version="rag-lab-profile-v1",
        profile_id="C1+ETEST",
        parser_id="canonical-parser-v1",
        chunker=chunker,
        embedding=embedding,
        retrieval=RetrievalSpec(result_count=5),
        dataset_version="tiny-v1",
        code_revision="test-revision",
    )


def test_experiment_runner_reports_quality_resources_and_no_raw_content(tmp_path) -> None:
    dataset = _write_dataset(tmp_path)
    profile = _profile()
    report = ExperimentRunner().run(
        dataset=dataset,
        corpus_root=tmp_path,
        profile=profile,
        chunker=StructureAwareChunker(profile.chunker),
        embedder=DeterministicHashAdapter(profile.embedding),
    )

    assert report.quality.evaluated_answerable_cases == 2
    assert report.quality.recall_at_5 == 1.0
    assert report.quality.cross_workspace_results == 0
    assert report.quality.citation_locator_resolution == 1.0
    assert report.resources.document_count == 2
    assert report.resources.chunk_count == 2
    assert report.resources.vector_bytes == 2 * 32 * 4
    assert report.profile_fingerprint == profile.fingerprint

    output = tmp_path / "report.json"
    report.write(output)
    serialized = output.read_text(encoding="utf-8")
    assert "International returns" not in serialized
    assert all("embedding" not in query for query in report.as_dict()["queries"])


def test_runner_rejects_runtime_profile_mismatch(tmp_path) -> None:
    dataset = _write_dataset(tmp_path)
    profile = _profile()
    wrong_spec = replace(profile.embedding, candidate_id="WRONG")
    with pytest.raises(ValueError, match="runtime strategies"):
        ExperimentRunner().run(
            dataset=dataset,
            corpus_root=tmp_path,
            profile=profile,
            chunker=StructureAwareChunker(profile.chunker),
            embedder=DeterministicHashAdapter(wrong_spec),
        )


def test_comparison_reports_paired_wins_without_selecting_a_winner(tmp_path) -> None:
    dataset = _write_dataset(tmp_path)
    profile = _profile()
    report = ExperimentRunner().run(
        dataset=dataset,
        corpus_root=tmp_path,
        profile=profile,
        chunker=StructureAwareChunker(profile.chunker),
        embedder=DeterministicHashAdapter(profile.embedding),
    )
    baseline_path = tmp_path / "baseline.json"
    report.write(baseline_path)
    candidate_payload = report.as_dict()
    candidate_payload["profile"]["profile_id"] = "C2+ETEST"
    candidate_payload["profile_fingerprint"] = "b" * 64
    candidate_payload["queries"][0]["relevant_ranks"] = []
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(candidate_payload), encoding="utf-8")

    rows = compare_reports([baseline_path, candidate_path])
    assert rows[0].ties == 3
    assert rows[1].losses == 1
    rendered = render_markdown(rows)
    assert "does not select a winner automatically" in rendered
    assert "C2+ETEST" in rendered

    with pytest.raises(ValueError, match="at least two"):
        compare_reports([baseline_path])


def test_checked_in_smoke_dataset_executes_but_is_not_strict_evidence() -> None:
    experiment_root = Path("experiments/rag/example")
    dataset = EvaluationDataset.load(experiment_root / "dataset.json")
    profile = build_profile(
        "C0",
        "E0",
        dataset_version=dataset.dataset_version,
        code_revision="test-revision",
    )
    report = ExperimentRunner().run(
        dataset=dataset,
        corpus_root=experiment_root / "corpus",
        profile=profile,
        chunker=build_chunker(profile.chunker),
        embedder=DeterministicHashAdapter(profile.embedding),
    )

    assert report.quality.cross_workspace_results == 0
    assert len(report.queries) == 3
    with pytest.raises(ValueError, match="at least 50"):
        dataset.validate_strict_coverage()
