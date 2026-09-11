from __future__ import annotations

import json
import math
from dataclasses import replace

import pytest

from packages.rag_lab.embeddings import (
    DeterministicHashAdapter,
    FastEmbedAdapter,
    LocalModelManifest,
)
from packages.rag_lab.lexical import BM25LexicalScorer, lexical_terms
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


def _chunk(
    chunk_id: str,
    text: str,
    *,
    version_id: str = "version",
    heading_path: tuple[str, ...] = (),
    document_title: str = "",
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id="document",
        version_id=version_id,
        order=0,
        text=text,
        embedding_text=text,
        token_count=len(text.split()),
        locators=(SourceLocator("b000000", 0, 0, len(text)),),
        heading_path=heading_path,
        page_number=None,
        document_title=document_title,
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

    truncating = DeterministicHashAdapter(
        replace(_embedding_spec(input_limit=3), truncation_policy="right")
    )
    assert truncating.embed_documents(["one two three four"]) == truncating.embed_documents(
        ["one two three"]
    )
    assert truncating.truncated_input_count == 2


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


def test_bm25_ignores_question_noise_and_rewards_rare_terms() -> None:
    scorer = BM25LexicalScorer(RetrievalSpec())
    relevant = _chunk(
        "a" * 64,
        "Emergency Reset immediately stops digital sharing.",
        heading_path=("Safety Check", "Emergency Reset"),
        document_title="Apple Personal Safety User Guide",
    )
    noisy = _chunk(
        "b" * 64,
        "Apple devices provide information and settings for a person using a device.",
        document_title="Apple Device Guide",
    )

    ranked = scorer.rank(
        "I have an Apple device. What should I use to stop all sharing immediately?",
        (noisy, relevant),
        limit=2,
    )

    assert ranked == (relevant, noisy)
    assert "what" not in lexical_terms("What should I use?")
    assert set(lexical_terms("sharing")) & set(lexical_terms("share"))


def test_bm25_preserves_identifiers_and_uses_trusted_structure() -> None:
    scorer = BM25LexicalScorer(RetrievalSpec())
    identifier = _chunk("a" * 64, "Use recovery code RET-30 for this request.")
    unrelated = _chunk("b" * 64, "Use recovery code RET-31 for this request.")
    structural = _chunk(
        "c" * 64,
        "Review the people and applications listed here.",
        heading_path=("Safety Check", "Manage Sharing and Access"),
    )

    assert scorer.rank("Where is RET-30?", (unrelated, identifier), limit=1) == (identifier,)
    assert scorer.rank("Manage sharing access", (identifier, structural), limit=1) == (structural,)
