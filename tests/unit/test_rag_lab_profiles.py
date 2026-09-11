from __future__ import annotations

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from packages.rag_lab.dataset import EvaluationDataset
from packages.rag_lab.models import (
    BlockKind,
    CanonicalBlock,
    CanonicalDocument,
    SourceLocator,
)
from packages.rag_lab.profiles import (
    CANDIDATES,
    ChunkerSpec,
    EmbeddingSpec,
    RetrievalSpec,
    build_profile,
)


def test_candidate_registry_and_profile_fingerprints_are_immutable() -> None:
    profile = build_profile("c1", "e2", dataset_version="week3-v1", code_revision="abc")
    same = build_profile("C1", "E2", dataset_version="week3-v1", code_revision="abc")
    changed = build_profile("C1", "E2", dataset_version="week3-v1", code_revision="def")

    assert profile.profile_id == "C1+E2"
    assert profile.fingerprint == same.fingerprint
    assert profile.fingerprint != changed.fingerprint
    assert len(profile.fingerprint) == 64
    assert profile.embedding.artifact_revision == CANDIDATES.embedding("E2").artifact_revision

    with pytest.raises(TypeError):
        CANDIDATES.chunkers["C3"] = profile.chunker  # type: ignore[index]
    with pytest.raises(ValueError, match="unknown chunking"):
        CANDIDATES.chunker("missing")
    with pytest.raises(ValueError, match="unknown embedding"):
        CANDIDATES.embedding("missing")


def test_candidate_spec_validation_rejects_ambiguous_profiles() -> None:
    with pytest.raises(ValueError, match="limits"):
        ChunkerSpec("C0", "1", 10, 9, 1, "fixed", "original")
    with pytest.raises(ValueError, match="overlap"):
        ChunkerSpec("C0", "1", 10, 10, 10, "fixed", "original")
    with pytest.raises(ValueError, match="commit SHA"):
        EmbeddingSpec(
            "E",
            "provider",
            "model",
            "artifact",
            "main",
            3,
            10,
            "mean",
            True,
            "",
            "",
            "MIT",
        )
    with pytest.raises(ValueError, match="truncation policy"):
        EmbeddingSpec(
            "E",
            "provider",
            "model",
            "artifact",
            "a" * 40,
            3,
            10,
            "mean",
            True,
            "",
            "",
            "MIT",
            "middle",
        )
    with pytest.raises(ValueError, match="cosine"):
        RetrievalSpec(distance="euclidean")
    with pytest.raises(ValueError, match="english"):
        RetrievalSpec(lexical_config="simple")
    with pytest.raises(ValueError, match="lexical scorer"):
        RetrievalSpec(lexical_scorer="word-count-v0")
    with pytest.raises(ValueError, match="BM25"):
        RetrievalSpec(bm25_b=1.1)
    with pytest.raises(ValueError, match="weights"):
        RetrievalSpec(heading_weight=-1)


def test_canonical_locators_resolve_and_fail_closed() -> None:
    block = CanonicalBlock("b000000", 0, BlockKind.PARAGRAPH, "alpha beta")
    document = CanonicalDocument("doc", "version", "Title", "text/plain", (block,))
    locator = SourceLocator("b000000", 0, 0, 5)
    assert document.resolve(locator) == "alpha"

    with pytest.raises(ValueError, match="missing block"):
        document.resolve(SourceLocator("b000001", 1, 0, 1))
    with pytest.raises(ValueError, match="identity"):
        document.resolve(SourceLocator("wrong", 0, 0, 1))
    with pytest.raises(ValueError, match="beyond"):
        document.resolve(SourceLocator("b000000", 0, 0, 99))


def test_dataset_schema_validates_references_paths_and_strict_coverage(tmp_path) -> None:
    workspace_id = uuid4()
    version_id = uuid4()
    payload = {
        "schema_version": "rag-lab-dataset-v1",
        "dataset_version": "tiny-v1",
        "documents": [
            {
                "workspace_id": str(workspace_id),
                "document_id": str(uuid4()),
                "version_id": str(version_id),
                "title": "Policy",
                "media_type": "text/plain",
                "source_path": "policy.txt",
            }
        ],
        "cases": [
            {
                "case_id": "lookup",
                "workspace_id": str(workspace_id),
                "query": "policy",
                "tags": ["direct_lookup"],
                "evidence": [
                    {
                        "version_id": str(version_id),
                        "block_id": "b000000",
                        "char_start": 0,
                        "char_end": 6,
                    }
                ],
            }
        ],
    }
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "policy.txt").write_text("policy", encoding="utf-8")
    dataset = EvaluationDataset.load(dataset_path)

    assert dataset.resolve_source(dataset.documents[0], tmp_path).name == "policy.txt"
    with pytest.raises(ValueError, match="at least 50"):
        dataset.validate_strict_coverage()

    payload["documents"][0]["source_path"] = "../private.txt"
    with pytest.raises(ValidationError, match="corpus directory"):
        EvaluationDataset.model_validate(payload)
    payload["documents"][0]["source_path"] = "policy.txt"
    payload["cases"][0]["evidence"][0]["version_id"] = str(uuid4())
    with pytest.raises(ValidationError, match="unknown document version"):
        EvaluationDataset.model_validate(payload)
