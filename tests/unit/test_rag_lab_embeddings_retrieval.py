from __future__ import annotations

import json
import math

import pytest

from packages.rag_lab.embeddings import (
    DeterministicHashAdapter,
    FastEmbedAdapter,
    LocalModelManifest,
)
from packages.rag_lab.models import Chunk, IndexedChunk, SourceLocator
from packages.rag_lab.profiles import EmbeddingSpec, RetrievalSpec
from packages.rag_lab.retrieval import InMemoryHybridIndex


def _embedding_spec(*, dimension: int = 16, input_limit: int = 30) -> EmbeddingSpec:
    return EmbeddingSpec(
        candidate_id="ETEST",
        provider="test",
        model_id="test/model",
        artifact_id="test/artifact",
        artifact_revision="a" * 40,
        dimension=dimension,
        input_limit=input_limit,
        pooling="mean",
        normalized=True,
        query_prefix="query: ",
        document_prefix="document: ",
        license="MIT",
    )


def _chunk(chunk_id: str, text: str, *, version_id: str = "version") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id="document",
        version_id=version_id,
        order=0,
        text=text,
        embedding_text=text,
        token_count=len(text.split()),
        locators=(SourceLocator("b000000", 0, 0, len(text)),),
        heading_path=(),
        page_number=None,
    )


def test_deterministic_embedding_contract_is_normalized_and_batch_stable() -> None:
    adapter = DeterministicHashAdapter(_embedding_spec())
    batch = adapter.embed_documents(["refund policy", "shipping policy"])

    assert len(batch) == 2
    assert batch[0] == adapter.embed_documents(["refund policy"])[0]
    assert len(batch[0]) == 16
    assert math.isclose(sum(value * value for value in batch[0]), 1.0)
    assert batch[0] != adapter.embed_queries(["refund policy"])[0]
    assert all(math.isfinite(value) for vector in batch for value in vector)
    assert adapter.embed_documents([]) == ()

    with pytest.raises(ValueError, match="empty"):
        adapter.embed_queries([" "])
    with pytest.raises(ValueError, match="input limit"):
        DeterministicHashAdapter(_embedding_spec(input_limit=1)).embed_documents(["too long"])


def test_offline_model_manifest_fails_closed_before_model_loading(tmp_path) -> None:
    spec = _embedding_spec()
    with pytest.raises(RuntimeError, match="directory"):
        FastEmbedAdapter(spec, model_path=tmp_path / "missing")

    model_path = tmp_path / "model"
    model_path.mkdir()
    with pytest.raises(RuntimeError, match="manifest"):
        LocalModelManifest.load(model_path)
    (model_path / "supportpilot-model.json").write_text(
        json.dumps(
            {
                "artifact_id": "wrong",
                "artifact_revision": "b" * 40,
                "dimension": 99,
            }
        ),
        encoding="utf-8",
    )
    assert LocalModelManifest.load(model_path).artifact_id == "wrong"
    with pytest.raises(RuntimeError, match="does not match"):
        FastEmbedAdapter(spec, model_path=model_path)


def test_hybrid_index_is_tenant_scoped_idempotent_and_deterministic() -> None:
    retrieval = RetrievalSpec(dense_candidates=5, lexical_candidates=5, result_count=5)
    index = InMemoryHybridIndex(retrieval)
    refund = _chunk("a" * 64, "refund code RET-30")
    shipping = _chunk("b" * 64, "shipping takes two days")
    decoy = _chunk("c" * 64, "refund code RET-30", version_id="other-version")
    records = (
        IndexedChunk("workspace-a", refund, (1.0, 0.0)),
        IndexedChunk("workspace-a", shipping, (0.0, 1.0)),
    )
    index.replace_version(
        workspace_id="workspace-a",
        profile_fingerprint="profile",
        version_id="version",
        records=records,
    )
    index.replace_version(
        workspace_id="workspace-a",
        profile_fingerprint="profile",
        version_id="version",
        records=records,
    )
    index.replace_version(
        workspace_id="workspace-b",
        profile_fingerprint="profile",
        version_id="other-version",
        records=(IndexedChunk("workspace-b", decoy, (1.0, 0.0)),),
    )

    trace = index.search_with_trace(
        workspace_id="workspace-a",
        profile_fingerprint="profile",
        query="refund RET-30",
        query_embedding=(1.0, 0.0),
    )
    assert [result.chunk.chunk_id for result in trace.results] == [
        refund.chunk_id,
        shipping.chunk_id,
    ]
    assert trace.results[0].dense_rank == 1
    assert trace.results[0].lexical_rank == 1
    assert all(result.workspace_id == "workspace-a" for result in trace.results)
    assert (
        index.search(
            workspace_id="workspace-a",
            profile_fingerprint="profile",
            query="refund RET-30",
            query_embedding=(1.0, 0.0),
        )
        == trace.results
    )

    index.deactivate_version(
        workspace_id="workspace-a",
        profile_fingerprint="profile",
        version_id="version",
    )
    assert not index.search(
        workspace_id="workspace-a",
        profile_fingerprint="profile",
        query="refund",
        query_embedding=(1.0, 0.0),
    )


def test_hybrid_index_rejects_invalid_scope_queries_and_vectors() -> None:
    index = InMemoryHybridIndex(RetrievalSpec())
    chunk = _chunk("a" * 64, "refund")
    with pytest.raises(ValueError, match="identity"):
        index.replace_version(
            workspace_id="workspace-a",
            profile_fingerprint="profile",
            version_id="version",
            records=(IndexedChunk("workspace-b", chunk, (1.0, 0.0)),),
        )
    index.replace_version(
        workspace_id="workspace-a",
        profile_fingerprint="profile",
        version_id="version",
        records=(IndexedChunk("workspace-a", chunk, (1.0, 0.0)),),
    )
    with pytest.raises(ValueError, match="empty"):
        index.search(
            workspace_id="workspace-a",
            profile_fingerprint="profile",
            query=" ",
            query_embedding=(1.0, 0.0),
        )
    with pytest.raises(ValueError, match="different dimensions"):
        index.search(
            workspace_id="workspace-a",
            profile_fingerprint="profile",
            query="refund",
            query_embedding=(1.0,),
        )
