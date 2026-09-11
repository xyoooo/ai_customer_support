from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any

from packages.rag_lab.tokenizer import RegexTokenizer


@dataclass(frozen=True, slots=True)
class ChunkerSpec:
    candidate_id: str
    implementation_version: str
    target_tokens: int
    max_tokens: int
    overlap_tokens: int
    boundary_policy: str
    context_policy: str
    tokenizer_id: str = RegexTokenizer.identifier

    def __post_init__(self) -> None:
        if self.target_tokens < 1 or self.max_tokens < self.target_tokens:
            raise ValueError("chunk token limits are invalid")
        if self.overlap_tokens < 0 or self.overlap_tokens >= self.target_tokens:
            raise ValueError("chunk overlap must be smaller than the target")


@dataclass(frozen=True, slots=True)
class EmbeddingSpec:
    candidate_id: str
    provider: str
    model_id: str
    artifact_id: str
    artifact_revision: str
    dimension: int
    input_limit: int
    pooling: str
    normalized: bool
    query_prefix: str
    document_prefix: str
    license: str
    truncation_policy: str = "reject"

    def __post_init__(self) -> None:
        if len(self.artifact_revision) != 40:
            raise ValueError("embedding artifact revision must be a full commit SHA")
        if self.dimension < 1 or self.input_limit < 1:
            raise ValueError("embedding dimension and input limit must be positive")
        if not self.license:
            raise ValueError("embedding license metadata is required")
        if self.truncation_policy not in {"reject", "right"}:
            raise ValueError("embedding truncation policy must be reject or right")


@dataclass(frozen=True, slots=True)
class RetrievalSpec:
    distance: str = "cosine"
    lexical_config: str = "english"
    lexical_scorer: str = "bm25-structural-v1"
    bm25_k1: float = 1.2
    bm25_b: float = 0.75
    heading_weight: float = 0.75
    title_weight: float = 0.5
    exact_identifier_bonus: float = 1.5
    phrase_bonus: float = 0.25
    lexical_candidates: int = 20
    dense_candidates: int = 20
    rrf_constant: int = 60
    result_count: int = 5
    tie_breaker: str = "chunk_id"

    def __post_init__(self) -> None:
        if self.distance != "cosine":
            raise ValueError("the initial lab supports exact cosine distance only")
        if self.lexical_config != "english":
            raise ValueError("the initial lab fixes PostgreSQL lexical retrieval to english")
        if self.lexical_scorer != "bm25-structural-v1":
            raise ValueError("unsupported lexical scorer")
        if self.bm25_k1 <= 0 or not 0 <= self.bm25_b <= 1:
            raise ValueError("BM25 parameters are invalid")
        if (
            min(
                self.heading_weight,
                self.title_weight,
                self.exact_identifier_bonus,
                self.phrase_bonus,
            )
            < 0
        ):
            raise ValueError("lexical weights and bonuses cannot be negative")
        if (
            min(
                self.lexical_candidates,
                self.dense_candidates,
                self.rrf_constant,
                self.result_count,
            )
            < 1
        ):
            raise ValueError("retrieval limits and RRF constant must be positive")


@dataclass(frozen=True, slots=True)
class ExperimentProfile:
    schema_version: str
    profile_id: str
    parser_id: str
    chunker: ChunkerSpec
    embedding: EmbeddingSpec
    retrieval: RetrievalSpec
    dataset_version: str
    code_revision: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class CandidateRegistry:
    chunkers: MappingProxyType[str, ChunkerSpec]
    embeddings: MappingProxyType[str, EmbeddingSpec]

    def chunker(self, candidate_id: str) -> ChunkerSpec:
        try:
            return self.chunkers[candidate_id.upper()]
        except KeyError as exc:
            raise ValueError(f"unknown chunking candidate: {candidate_id}") from exc

    def embedding(self, candidate_id: str) -> EmbeddingSpec:
        try:
            return self.embeddings[candidate_id.upper()]
        except KeyError as exc:
            raise ValueError(f"unknown embedding candidate: {candidate_id}") from exc


_CHUNKERS = {
    "C0": ChunkerSpec(
        candidate_id="C0",
        implementation_version="2-shared-model-budget",
        target_tokens=350,
        max_tokens=350,
        overlap_tokens=60,
        boundary_policy="fixed-token; never cross PDF pages",
        context_policy="original",
    ),
    "C1": ChunkerSpec(
        candidate_id="C1",
        implementation_version="2-layout-and-shared-model-budget",
        target_tokens=350,
        max_tokens=500,
        overlap_tokens=60,
        boundary_policy="heading; paragraph; sentence; token fallback",
        context_policy="original",
    ),
    "C2": ChunkerSpec(
        candidate_id="C2",
        implementation_version="2-layout-and-shared-model-budget",
        target_tokens=350,
        max_tokens=500,
        overlap_tokens=60,
        boundary_policy="heading; paragraph; sentence; token fallback",
        context_policy="document-title-and-heading-path",
    ),
}

_EMBEDDINGS = {
    "E0": EmbeddingSpec(
        candidate_id="E0",
        provider="fastembed-0.8.0",
        model_id="BAAI/bge-small-en-v1.5",
        artifact_id="qdrant/bge-small-en-v1.5-onnx-q",
        artifact_revision="52398278842ec682c6f32300af41344b1c0b0bb2",
        dimension=384,
        input_limit=512,
        pooling="cls",
        normalized=True,
        query_prefix="Represent this sentence for searching relevant passages: ",
        document_prefix="",
        license="MIT",
        truncation_policy="reject",
    ),
    "E1": EmbeddingSpec(
        candidate_id="E1",
        provider="fastembed-0.8.0",
        model_id="snowflake/snowflake-arctic-embed-xs",
        artifact_id="snowflake/snowflake-arctic-embed-xs",
        artifact_revision="d8c86521100d3556476a063fc2342036d45c106f",
        dimension=384,
        input_limit=512,
        pooling="cls",
        normalized=True,
        query_prefix="Represent this sentence for searching relevant passages: ",
        document_prefix="",
        license="Apache-2.0",
        truncation_policy="reject",
    ),
    "E2": EmbeddingSpec(
        candidate_id="E2",
        provider="fastembed-0.8.0",
        model_id="jinaai/jina-embeddings-v2-small-en",
        artifact_id="xenova/jina-embeddings-v2-small-en",
        artifact_revision="523cadcb9c2e71c7153fc46016e1fe79acb4f58f",
        dimension=512,
        input_limit=8192,
        pooling="mean",
        normalized=True,
        query_prefix="",
        document_prefix="",
        license="Apache-2.0",
        truncation_policy="reject",
    ),
}

CANDIDATES = CandidateRegistry(
    chunkers=MappingProxyType(_CHUNKERS),
    embeddings=MappingProxyType(_EMBEDDINGS),
)


def build_profile(
    chunker_id: str,
    embedding_id: str,
    *,
    dataset_version: str,
    code_revision: str,
    retrieval: RetrievalSpec | None = None,
) -> ExperimentProfile:
    chunker = CANDIDATES.chunker(chunker_id)
    embedding = CANDIDATES.embedding(embedding_id)
    return ExperimentProfile(
        schema_version="rag-lab-profile-v1",
        profile_id=f"{chunker.candidate_id}+{embedding.candidate_id}",
        parser_id="canonical-parser-v2-layout",
        chunker=chunker,
        embedding=embedding,
        retrieval=retrieval or RetrievalSpec(),
        dataset_version=dataset_version,
        code_revision=code_revision,
    )
