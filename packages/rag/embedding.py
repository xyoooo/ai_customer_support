from __future__ import annotations

import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from fastembed import TextEmbedding
from tokenizers import Tokenizer

from packages.rag.config import PIPELINE


class Embedder(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...

    def embed_queries(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...


@dataclass(frozen=True, slots=True)
class ModelManifest:
    artifact_id: str
    artifact_revision: str
    dimension: int

    @classmethod
    def load(cls, model_path: Path) -> ModelManifest:
        path = model_path / "supportpilot-model.json"
        if not path.is_file():
            raise RuntimeError(f"offline E1 model manifest is missing: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                artifact_id=str(payload["artifact_id"]),
                artifact_revision=str(payload["artifact_revision"]),
                dimension=int(payload["dimension"]),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("offline E1 model manifest is malformed") from exc


def normalize_embedding(vector: Iterable[float]) -> tuple[float, ...]:
    values = tuple(float(value) for value in vector)
    if len(values) != PIPELINE.embedding_dimension:
        raise RuntimeError("E1 returned an unexpected embedding dimension")
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError("E1 returned a non-finite embedding")
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        raise RuntimeError("E1 returned a zero-magnitude embedding")
    return tuple(value / norm for value in values)


class E1Embedder:
    """Pinned Snowflake Arctic Embed XS adapter with no runtime downloads."""

    def __init__(self, model_path: Path, *, threads: int | None = None) -> None:
        if not model_path.is_dir():
            raise RuntimeError(f"offline E1 model directory is missing: {model_path}")
        manifest = ModelManifest.load(model_path)
        if (
            manifest.artifact_id != PIPELINE.embedding_artifact_id
            or manifest.artifact_revision != PIPELINE.embedding_artifact_revision
            or manifest.dimension != PIPELINE.embedding_dimension
        ):
            raise RuntimeError("offline E1 model manifest does not match rag-v1-c1-e1")
        tokenizer_path = model_path / "tokenizer.json"
        if not tokenizer_path.is_file():
            raise RuntimeError("offline E1 tokenizer.json is missing")
        self.tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self.tokenizer.no_truncation()
        self.model = TextEmbedding(
            model_name=PIPELINE.embedding_model_id,
            threads=threads,
            specific_model_path=str(model_path),
        )

    def _prepare(self, text: str, *, query: bool) -> str:
        value = text.strip()
        if not value:
            raise ValueError("embedding input cannot be empty")
        prepared = f"{PIPELINE.embedding_query_prefix if query else ''}{value}"
        tokens = self.tokenizer.encode(prepared, add_special_tokens=True).ids
        if len(tokens) > PIPELINE.embedding_input_limit:
            raise ValueError("embedding input exceeds the E1 token limit")
        return prepared

    def _embed(self, texts: Sequence[str], *, query: bool) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        prepared = [self._prepare(text, query=query) for text in texts]
        vectors = tuple(
            normalize_embedding(cast(Iterable[float], vector))
            for vector in self.model.embed(prepared)
        )
        if len(vectors) != len(prepared):
            raise RuntimeError("E1 returned the wrong batch length")
        return vectors

    def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return self._embed(texts, query=False)

    def embed_queries(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return self._embed(texts, query=True)


class E1TokenBudget:
    def __init__(self, model_path: Path) -> None:
        tokenizer_path = model_path / "tokenizer.json"
        if not tokenizer_path.is_file():
            raise RuntimeError("offline E1 tokenizer.json is missing")
        self.tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self.tokenizer.no_truncation()

    def fits(self, text: str) -> bool:
        return (
            len(self.tokenizer.encode(text.strip(), add_special_tokens=True).ids)
            <= PIPELINE.embedding_input_limit
        )

    def assert_fits(self, text: str) -> None:
        if not self.fits(text):
            raise ValueError("chunk exceeds the E1 token limit")
