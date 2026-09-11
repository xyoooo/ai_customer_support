from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from packages.rag.chunking import StructureAwareChunker
from packages.rag.embedding import E1Embedder, E1TokenBudget, Embedder
from packages.rag.models import EmbeddedChunk, SearchResult
from packages.rag.parsing import CanonicalParser
from packages.rag.repository import ChunkRepository


class Indexer(Protocol):
    def index_content(
        self,
        content: bytes,
        *,
        document_id: UUID,
        version_id: UUID,
        title: str,
        media_type: str,
    ) -> tuple[EmbeddedChunk, ...]: ...


class RAGIndexer:
    def __init__(
        self,
        *,
        parser: CanonicalParser,
        chunker: StructureAwareChunker,
        embedder: Embedder,
        batch_size: int,
    ) -> None:
        self.parser = parser
        self.chunker = chunker
        self.embedder = embedder
        self.batch_size = batch_size

    def index_content(
        self,
        content: bytes,
        *,
        document_id: UUID,
        version_id: UUID,
        title: str,
        media_type: str,
    ) -> tuple[EmbeddedChunk, ...]:
        document = self.parser.parse(
            content,
            document_id=document_id,
            version_id=version_id,
            title=title,
            media_type=media_type,
        )
        chunks = self.chunker.chunk(document)
        records: list[EmbeddedChunk] = []
        for start in range(0, len(chunks), self.batch_size):
            batch = chunks[start : start + self.batch_size]
            embeddings = self.embedder.embed_documents([chunk.embedding_text for chunk in batch])
            if len(embeddings) != len(batch):
                raise RuntimeError("E1 returned the wrong indexing batch length")
            records.extend(
                EmbeddedChunk(chunk, embedding)
                for chunk, embedding in zip(batch, embeddings, strict=True)
            )
        return tuple(records)


class RetrievalService:
    def __init__(self, embedder: Embedder, repository: ChunkRepository | None = None) -> None:
        self.embedder = embedder
        self.repository = repository or ChunkRepository()

    async def search(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        query: str,
        result_count: int,
    ) -> tuple[SearchResult, ...]:
        vectors = await asyncio.to_thread(self.embedder.embed_queries, (query,))
        if len(vectors) != 1:
            raise RuntimeError("E1 returned the wrong query batch length")
        return await self.repository.search(
            session,
            workspace_id=workspace_id,
            query=query,
            query_embedding=vectors[0],
            result_count=result_count,
        )


@lru_cache
def get_e1_embedder(model_path: str, threads: int | None) -> E1Embedder:
    return E1Embedder(Path(model_path), threads=threads)


@lru_cache
def get_rag_indexer(model_path: str, threads: int | None, batch_size: int) -> RAGIndexer:
    path = Path(model_path)
    return RAGIndexer(
        parser=CanonicalParser(),
        chunker=StructureAwareChunker(E1TokenBudget(path)),
        embedder=get_e1_embedder(model_path, threads),
        batch_size=batch_size,
    )


@lru_cache
def get_retrieval_service(model_path: str, threads: int | None) -> RetrievalService:
    return RetrievalService(get_e1_embedder(model_path, threads))
