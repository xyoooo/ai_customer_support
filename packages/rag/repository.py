from __future__ import annotations

import math
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from packages.database.models import Document, DocumentChunk
from packages.rag.config import PIPELINE
from packages.rag.lexical import BM25LexicalScorer
from packages.rag.models import Chunk, EmbeddedChunk, SearchResult, SourceLocator

_MAX_LEXICAL_CORPUS_CHUNKS = 10_000


def _locator_integer(value: dict[str, int | str | None], key: str) -> int:
    raw = value.get(key)
    if not isinstance(raw, (int, str)):
        raise RuntimeError("stored source locator is malformed")
    return int(raw)


def _stored_chunk(record: DocumentChunk) -> Chunk:
    locators = []
    for value in record.locators:
        raw_page = value.get("page_number")
        locators.append(
            SourceLocator(
                block_id=str(value["block_id"]),
                block_index=_locator_integer(value, "block_index"),
                char_start=_locator_integer(value, "char_start"),
                char_end=_locator_integer(value, "char_end"),
                page_number=None if raw_page is None else int(raw_page),
            )
        )
    return Chunk(
        chunk_id=record.chunk_id,
        document_id=record.document_id,
        version_id=record.version_id,
        order=record.chunk_order,
        text=record.original_text,
        embedding_text=record.original_text,
        token_count=record.token_count,
        locators=tuple(locators),
        heading_path=tuple(record.heading_path),
        page_number=record.page_number,
        document_title=record.document_title,
    )


def _fuse_rankings(
    dense: Sequence[Chunk],
    lexical: Sequence[Chunk],
    *,
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
            score += 1 / (PIPELINE.rrf_constant + dense_rank)
        if lexical_rank is not None:
            score += 1 / (PIPELINE.rrf_constant + lexical_rank)
        results.append(SearchResult(chunk, score, dense_rank, lexical_rank))
    results.sort(key=lambda result: (-result.fused_score, result.chunk.chunk_id))
    return tuple(results[:result_count])


class ChunkRepository:
    def __init__(self) -> None:
        self.lexical = BM25LexicalScorer()

    async def replace_version(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        records: Sequence[EmbeddedChunk],
    ) -> None:
        if not records:
            raise ValueError("cannot activate an empty production index")
        first = records[0].chunk
        if any(
            record.chunk.version_id != first.version_id
            or record.chunk.document_id != first.document_id
            or len(record.embedding) != PIPELINE.embedding_dimension
            or not all(math.isfinite(value) for value in record.embedding)
            for record in records
        ):
            raise ValueError("embedded chunks do not share the production storage contract")
        await session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.workspace_id == workspace_id,
                DocumentChunk.version_id == first.version_id,
                DocumentChunk.pipeline_version == PIPELINE.version,
            )
        )
        session.add_all(
            [
                DocumentChunk(
                    chunk_id=record.chunk.chunk_id,
                    workspace_id=workspace_id,
                    document_id=record.chunk.document_id,
                    version_id=record.chunk.version_id,
                    pipeline_version=PIPELINE.version,
                    chunk_order=record.chunk.order,
                    original_text=record.chunk.text,
                    token_count=record.chunk.token_count,
                    locators=[locator.as_dict() for locator in record.chunk.locators],
                    heading_path=list(record.chunk.heading_path),
                    page_number=record.chunk.page_number,
                    document_title=record.chunk.document_title,
                    embedding=list(record.embedding),
                )
                for record in records
            ]
        )
        await session.flush()

    async def delete_document(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        document_id: UUID,
    ) -> None:
        await session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.workspace_id == workspace_id,
                DocumentChunk.document_id == document_id,
            )
        )

    @staticmethod
    def _active_scope(workspace_id: UUID) -> tuple[ColumnElement[bool], ...]:
        return (
            DocumentChunk.workspace_id == workspace_id,
            DocumentChunk.pipeline_version == PIPELINE.version,
            Document.id == DocumentChunk.document_id,
            Document.active_version_id == DocumentChunk.version_id,
            Document.deleted_at.is_(None),
        )

    async def search(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        query: str,
        query_embedding: Sequence[float],
        result_count: int,
    ) -> tuple[SearchResult, ...]:
        if not query.strip():
            raise ValueError("retrieval query cannot be empty")
        if len(query_embedding) != PIPELINE.embedding_dimension:
            raise ValueError("retrieval query embedding has the wrong dimension")
        if not 1 <= result_count <= PIPELINE.maximum_result_count:
            raise ValueError("retrieval result count is outside the supported range")
        scope = self._active_scope(workspace_id)
        dense_records = tuple(
            await session.scalars(
                select(DocumentChunk)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(*scope)
                .order_by(
                    DocumentChunk.embedding.cosine_distance(list(query_embedding)),
                    DocumentChunk.chunk_id,
                )
                .limit(PIPELINE.dense_candidates)
            )
        )
        lexical_records = tuple(
            await session.scalars(
                select(DocumentChunk)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(*scope)
                .order_by(DocumentChunk.chunk_id)
                .limit(_MAX_LEXICAL_CORPUS_CHUNKS + 1)
            )
        )
        if len(lexical_records) > _MAX_LEXICAL_CORPUS_CHUNKS:
            raise RuntimeError("workspace exceeds the bounded lexical retrieval limit")
        dense = tuple(_stored_chunk(record) for record in dense_records)
        lexical = self.lexical.rank(
            query,
            tuple(_stored_chunk(record) for record in lexical_records),
            limit=PIPELINE.lexical_candidates,
        )
        return _fuse_rankings(dense, lexical, result_count=result_count)
