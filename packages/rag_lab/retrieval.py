from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.rag_lab.models import (
    Chunk,
    IndexedChunk,
    RetrievalTrace,
    SearchResult,
    SourceLocator,
)
from packages.rag_lab.profiles import RetrievalSpec
from packages.rag_lab.tokenizer import RegexTokenizer


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("cannot compare embeddings with different dimensions")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("cannot compare a zero-magnitude embedding")
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def _fuse_rankings(
    dense: Sequence[Chunk],
    lexical: Sequence[Chunk],
    *,
    workspace_id: str,
    rrf_constant: int,
    result_count: int,
) -> tuple[SearchResult, ...]:
    dense_ranks = {chunk.chunk_id: rank for rank, chunk in enumerate(dense, start=1)}
    lexical_ranks = {chunk.chunk_id: rank for rank, chunk in enumerate(lexical, start=1)}
    chunks = {chunk.chunk_id: chunk for chunk in (*dense, *lexical)}
    results = []
    for chunk_id, chunk in chunks.items():
        dense_rank = dense_ranks.get(chunk_id)
        lexical_rank = lexical_ranks.get(chunk_id)
        score = 0.0
        if dense_rank is not None:
            score += 1.0 / (rrf_constant + dense_rank)
        if lexical_rank is not None:
            score += 1.0 / (rrf_constant + lexical_rank)
        results.append(
            SearchResult(
                workspace_id=workspace_id,
                chunk=chunk,
                fused_score=score,
                dense_rank=dense_rank,
                lexical_rank=lexical_rank,
            )
        )
    results.sort(key=lambda result: (-result.fused_score, result.chunk.chunk_id))
    return tuple(results[:result_count])


class InMemoryHybridIndex:
    """Deterministic reference implementation for tests and small fixture runs."""

    def __init__(self, retrieval: RetrievalSpec) -> None:
        self.retrieval = retrieval
        self._records: dict[tuple[str, str, str], IndexedChunk] = {}
        self._tokenizer = RegexTokenizer()

    def replace_version(
        self,
        *,
        workspace_id: str,
        profile_fingerprint: str,
        version_id: str,
        records: Sequence[IndexedChunk],
    ) -> None:
        stale = [
            key
            for key, record in self._records.items()
            if key[0] == workspace_id
            and key[1] == profile_fingerprint
            and record.chunk.version_id == version_id
        ]
        for key in stale:
            del self._records[key]
        for record in records:
            if record.workspace_id != workspace_id or record.chunk.version_id != version_id:
                raise ValueError("indexed record identity does not match the replacement scope")
            key = (workspace_id, profile_fingerprint, record.chunk.chunk_id)
            self._records[key] = record

    def deactivate_version(
        self,
        *,
        workspace_id: str,
        profile_fingerprint: str,
        version_id: str,
    ) -> None:
        for key, record in tuple(self._records.items()):
            if (
                key[0] == workspace_id
                and key[1] == profile_fingerprint
                and record.chunk.version_id == version_id
            ):
                self._records[key] = IndexedChunk(
                    workspace_id=record.workspace_id,
                    chunk=record.chunk,
                    embedding=record.embedding,
                    active=False,
                )

    def search(
        self,
        *,
        workspace_id: str,
        profile_fingerprint: str,
        query: str,
        query_embedding: Sequence[float],
    ) -> tuple[SearchResult, ...]:
        return self.search_with_trace(
            workspace_id=workspace_id,
            profile_fingerprint=profile_fingerprint,
            query=query,
            query_embedding=query_embedding,
        ).results

    def search_with_trace(
        self,
        *,
        workspace_id: str,
        profile_fingerprint: str,
        query: str,
        query_embedding: Sequence[float],
    ) -> RetrievalTrace:
        if not query.strip():
            raise ValueError("retrieval query cannot be empty")
        candidates = [
            record
            for key, record in self._records.items()
            if key[0] == workspace_id and key[1] == profile_fingerprint and record.active
        ]
        dense_scored = [
            (_cosine_similarity(query_embedding, record.embedding), record.chunk)
            for record in candidates
        ]
        dense_scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
        dense = [chunk for _, chunk in dense_scored[: self.retrieval.dense_candidates]]

        query_terms = [token.text.casefold() for token in self._tokenizer.spans(query)]
        lexical_scored: list[tuple[float, Chunk]] = []
        for record in candidates:
            terms = [token.text.casefold() for token in self._tokenizer.spans(record.chunk.text)]
            counts = Counter(terms)
            score = sum(counts[term] for term in query_terms) / math.sqrt(max(1, len(terms)))
            if score > 0:
                lexical_scored.append((score, record.chunk))
        lexical_scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
        lexical = [chunk for _, chunk in lexical_scored[: self.retrieval.lexical_candidates]]
        results = _fuse_rankings(
            dense,
            lexical,
            workspace_id=workspace_id,
            rrf_constant=self.retrieval.rrf_constant,
            result_count=self.retrieval.result_count,
        )
        return RetrievalTrace(results=results, dense=tuple(dense), lexical=tuple(lexical))


def _vector_literal(vector: Sequence[float]) -> str:
    if not vector or not all(math.isfinite(value) for value in vector):
        raise ValueError("PostgreSQL vector must contain finite values")
    return "[" + ",".join(format(float(value), ".17g") for value in vector) + "]"


def _row_to_chunk(row: Any) -> Chunk:
    mapping = row._mapping
    raw_locators = mapping["locators"]
    if isinstance(raw_locators, str):
        raw_locators = json.loads(raw_locators)
    raw_heading_path = mapping["heading_path"]
    if isinstance(raw_heading_path, str):
        raw_heading_path = json.loads(raw_heading_path)
    return Chunk(
        chunk_id=mapping["chunk_id"],
        document_id=str(mapping["document_id"]),
        version_id=str(mapping["version_id"]),
        order=mapping["chunk_order"],
        text=mapping["original_text"],
        embedding_text=mapping["embedding_text"],
        token_count=mapping["token_count"],
        locators=tuple(SourceLocator(**locator) for locator in raw_locators),
        heading_path=tuple(raw_heading_path),
        page_number=mapping["page_number"],
    )


_DENSE_QUERY = """
SELECT chunk_id, document_id, version_id, chunk_order, original_text,
       embedding_text, token_count, locators, heading_path, page_number
FROM rag_lab_chunks
WHERE workspace_id = CAST(:workspace_id AS uuid)
  AND profile_fingerprint = :profile_fingerprint
  AND embedding_dimension = :embedding_dimension
  AND active
ORDER BY embedding <=> CAST(:query_vector AS vector), chunk_id
LIMIT :dense_limit
"""

_LEXICAL_QUERY = """
SELECT chunk_id, document_id, version_id, chunk_order, original_text,
       embedding_text, token_count, locators, heading_path, page_number
FROM rag_lab_chunks,
     plainto_tsquery(CAST(:lexical_config AS regconfig), :query) AS q
WHERE workspace_id = CAST(:workspace_id AS uuid)
  AND profile_fingerprint = :profile_fingerprint
  AND active
  AND search_vector @@ q
ORDER BY ts_rank_cd(search_vector, q) DESC, chunk_id
LIMIT :lexical_limit
"""


class PostgresHybridIndex:
    """Lab-only PostgreSQL exact vector, lexical, and deterministic RRF retrieval."""

    def __init__(self, retrieval: RetrievalSpec) -> None:
        self.retrieval = retrieval

    async def replace_version(
        self,
        session: AsyncSession,
        *,
        workspace_id: str,
        profile_fingerprint: str,
        records: Sequence[IndexedChunk],
    ) -> None:
        if not records:
            raise ValueError("cannot activate an empty experimental index")
        version_id = records[0].chunk.version_id
        if any(
            record.workspace_id != workspace_id or record.chunk.version_id != version_id
            for record in records
        ):
            raise ValueError("indexed records do not share the replacement scope")
        await session.execute(
            text(
                """
                DELETE FROM rag_lab_chunks
                WHERE workspace_id = CAST(:workspace_id AS uuid)
                  AND profile_fingerprint = :profile_fingerprint
                  AND version_id = CAST(:version_id AS uuid)
                """
            ),
            {
                "workspace_id": workspace_id,
                "profile_fingerprint": profile_fingerprint,
                "version_id": version_id,
            },
        )
        statement = text(
            """
            INSERT INTO rag_lab_chunks (
                workspace_id, profile_fingerprint, chunk_id, document_id, version_id,
                chunk_order, original_text, embedding_text, token_count, locators,
                heading_path, page_number, embedding, embedding_dimension, active
            ) VALUES (
                CAST(:workspace_id AS uuid), :profile_fingerprint, :chunk_id,
                CAST(:document_id AS uuid), CAST(:version_id AS uuid), :chunk_order,
                :original_text, :embedding_text, :token_count, CAST(:locators AS jsonb),
                CAST(:heading_path AS jsonb), :page_number, CAST(:embedding AS vector),
                :embedding_dimension, :active
            )
            """
        )
        payloads = []
        for record in records:
            payload = record.chunk.as_storage_dict()
            payload.update(
                {
                    "workspace_id": workspace_id,
                    "profile_fingerprint": profile_fingerprint,
                    "locators": json.dumps(payload["locators"], separators=(",", ":")),
                    "heading_path": json.dumps(payload["heading_path"], separators=(",", ":")),
                    "embedding": _vector_literal(record.embedding),
                    "embedding_dimension": len(record.embedding),
                    "active": record.active,
                }
            )
            payloads.append(payload)
        await session.execute(statement, payloads)

    async def search(
        self,
        session: AsyncSession,
        *,
        workspace_id: str,
        profile_fingerprint: str,
        query: str,
        query_embedding: Sequence[float],
    ) -> tuple[SearchResult, ...]:
        trace = await self.search_with_trace(
            session,
            workspace_id=workspace_id,
            profile_fingerprint=profile_fingerprint,
            query=query,
            query_embedding=query_embedding,
        )
        return trace.results

    async def search_with_trace(
        self,
        session: AsyncSession,
        *,
        workspace_id: str,
        profile_fingerprint: str,
        query: str,
        query_embedding: Sequence[float],
    ) -> RetrievalTrace:
        if not query.strip():
            raise ValueError("retrieval query cannot be empty")
        parameters = {
            "workspace_id": workspace_id,
            "profile_fingerprint": profile_fingerprint,
            "query": query,
            "query_vector": _vector_literal(query_embedding),
            "embedding_dimension": len(query_embedding),
            "dense_limit": self.retrieval.dense_candidates,
            "lexical_limit": self.retrieval.lexical_candidates,
            "lexical_config": self.retrieval.lexical_config,
        }
        dense_rows = (
            await session.execute(
                text(_DENSE_QUERY),
                parameters,
            )
        ).all()
        lexical_rows = (
            await session.execute(
                text(_LEXICAL_QUERY),
                parameters,
            )
        ).all()
        dense = tuple(_row_to_chunk(row) for row in dense_rows)
        lexical = tuple(_row_to_chunk(row) for row in lexical_rows)
        results = _fuse_rankings(
            dense,
            lexical,
            workspace_id=workspace_id,
            rrf_constant=self.retrieval.rrf_constant,
            result_count=self.retrieval.result_count,
        )
        return RetrievalTrace(results=results, dense=dense, lexical=lexical)
