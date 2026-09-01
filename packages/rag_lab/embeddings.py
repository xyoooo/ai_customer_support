from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from fastembed import TextEmbedding
from tokenizers import Tokenizer

from packages.rag_lab.profiles import EmbeddingSpec
from packages.rag_lab.tokenizer import RegexTokenizer


class EmbeddingAdapter(Protocol):
    spec: EmbeddingSpec

    @property
    def truncated_input_count(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...

    def embed_queries(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...


@dataclass(frozen=True, slots=True)
class LocalModelManifest:
    artifact_id: str
    artifact_revision: str
    dimension: int

    @classmethod
    def load(cls, model_path: Path) -> LocalModelManifest:
        manifest_path = model_path / "supportpilot-model.json"
        if not manifest_path.is_file():
            raise RuntimeError(f"offline model manifest is missing: {manifest_path}")
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            return cls(
                artifact_id=str(payload["artifact_id"]),
                artifact_revision=str(payload["artifact_revision"]),
                dimension=int(payload["dimension"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("offline model manifest is malformed") from exc


def _normalized(vector: Iterable[float], expected_dimension: int) -> tuple[float, ...]:
    values = tuple(float(value) for value in vector)
    if len(values) != expected_dimension:
        raise RuntimeError(
            f"embedding dimension mismatch: expected {expected_dimension}, got {len(values)}"
        )
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError("embedding contains a non-finite value")
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        raise RuntimeError("embedding has zero magnitude")
    return tuple(value / norm for value in values)


class FastEmbedAdapter:
    """Pinned, offline-only adapter for E0-E2.

    Model acquisition is a separate explicit setup step. Normal evaluation requires
    a local artifact directory and an exact SupportPilot manifest, so FastEmbed never
    receives permission to resolve or download a model at runtime.
    """

    def __init__(
        self,
        spec: EmbeddingSpec,
        *,
        model_path: Path,
        threads: int | None = None,
    ) -> None:
        if not model_path.is_dir():
            raise RuntimeError(f"offline model directory is missing: {model_path}")
        manifest = LocalModelManifest.load(model_path)
        if (
            manifest.artifact_id != spec.artifact_id
            or manifest.artifact_revision != spec.artifact_revision
            or manifest.dimension != spec.dimension
        ):
            raise RuntimeError("offline model manifest does not match the candidate profile")
        tokenizer_path = model_path / "tokenizer.json"
        if not tokenizer_path.is_file():
            raise RuntimeError("offline model tokenizer.json is missing")
        self.spec = spec
        self._truncated_input_count = 0
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._tokenizer.no_truncation()
        self._model = TextEmbedding(
            model_name=spec.model_id,
            threads=threads,
            specific_model_path=str(model_path),
        )

    def _fit_model_limit(self, prepared: str) -> str:
        encoded = self._tokenizer.encode(prepared, add_special_tokens=True)
        if len(encoded.ids) <= self.spec.input_limit:
            return prepared
        if self.spec.truncation_policy == "reject":
            raise ValueError(
                f"embedding input has {len(encoded.ids)} model tokens; "
                f"limit is {self.spec.input_limit}"
            )

        special_tokens = len(self._tokenizer.encode("", add_special_tokens=True).ids)
        budget = self.spec.input_limit - special_tokens
        if budget < 1:
            raise ValueError("embedding input limit cannot hold content and special tokens")
        content_ids = self._tokenizer.encode(prepared, add_special_tokens=False).ids
        fitted_ids = content_ids[:budget]
        fitted = self._tokenizer.decode(fitted_ids, skip_special_tokens=True).strip()
        while (
            fitted
            and len(self._tokenizer.encode(fitted, add_special_tokens=True).ids)
            > self.spec.input_limit
        ):
            fitted_ids = fitted_ids[:-1]
            fitted = self._tokenizer.decode(fitted_ids, skip_special_tokens=True).strip()
        if not fitted:
            raise ValueError("embedding truncation removed all content")
        self._truncated_input_count += 1
        return fitted

    @property
    def truncated_input_count(self) -> int:
        return self._truncated_input_count

    def _prepare(self, text: str, *, query: bool) -> str:
        stripped = text.strip()
        if not stripped:
            raise ValueError("embedding input cannot be empty")
        prefix = self.spec.query_prefix if query else self.spec.document_prefix
        prepared = f"{prefix}{stripped}"
        return self._fit_model_limit(prepared)

    def _embed(self, texts: Sequence[str], *, query: bool) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        prepared = [self._prepare(text, query=query) for text in texts]
        raw = self._model.embed(prepared)
        vectors = tuple(
            _normalized(cast(Iterable[float], vector), self.spec.dimension) for vector in raw
        )
        if len(vectors) != len(prepared):
            raise RuntimeError("embedding backend returned the wrong batch length")
        return vectors

    def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return self._embed(texts, query=False)

    def embed_queries(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return self._embed(texts, query=True)


class DeterministicHashAdapter:
    """Offline deterministic test adapter; never valid for quality claims."""

    def __init__(self, spec: EmbeddingSpec) -> None:
        self.spec = spec
        self._tokenizer = RegexTokenizer()
        self._truncated_input_count = 0

    def _prepare(self, text: str, *, query: bool) -> str:
        stripped = text.strip()
        if not stripped:
            raise ValueError("embedding input cannot be empty")
        prepared = f"{self.spec.query_prefix if query else self.spec.document_prefix}{stripped}"
        tokens = self._tokenizer.spans(prepared)
        if len(tokens) > self.spec.input_limit and self.spec.truncation_policy == "reject":
            raise ValueError("embedding input exceeds the declared input limit")
        if len(tokens) > self.spec.input_limit:
            prepared = prepared[: tokens[self.spec.input_limit - 1].end]
            self._truncated_input_count += 1
        return prepared

    @property
    def truncated_input_count(self) -> int:
        return self._truncated_input_count

    def _vector(self, text: str, *, query: bool) -> tuple[float, ...]:
        prepared = self._prepare(text, query=query)
        values = [0.0] * self.spec.dimension
        for token in self._tokenizer.spans(prepared.casefold()):
            digest = hashlib.sha256(token.text.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.spec.dimension
            values[index] += 1.0 if digest[4] & 1 else -1.0
        return _normalized(values, self.spec.dimension)

    def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return tuple(self._vector(text, query=False) for text in texts)

    def embed_queries(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return tuple(self._vector(text, query=True) for text in texts)
