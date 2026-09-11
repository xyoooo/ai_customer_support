from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID


class BlockKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"


@dataclass(frozen=True, slots=True)
class SourceLocator:
    block_id: str
    block_index: int
    char_start: int
    char_end: int
    page_number: int | None = None

    def __post_init__(self) -> None:
        if not self.block_id or self.block_index < 0:
            raise ValueError("source locator block identity is invalid")
        if self.char_start < 0 or self.char_end <= self.char_start:
            raise ValueError("source locator must contain a non-empty span")
        if self.page_number is not None and self.page_number < 1:
            raise ValueError("PDF page numbers are one-based")

    def as_dict(self) -> dict[str, int | str | None]:
        return {
            "block_id": self.block_id,
            "block_index": self.block_index,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "page_number": self.page_number,
        }


@dataclass(frozen=True, slots=True)
class CanonicalBlock:
    block_id: str
    order: int
    kind: BlockKind
    text: str
    heading_path: tuple[str, ...] = ()
    page_number: int | None = None

    def __post_init__(self) -> None:
        if not self.block_id or self.order < 0:
            raise ValueError("canonical block identity is invalid")
        if not self.text.strip() or self.text != self.text.strip():
            raise ValueError("canonical block text must be non-empty and normalized")
        if self.page_number is not None and self.page_number < 1:
            raise ValueError("PDF page numbers are one-based")


@dataclass(frozen=True, slots=True)
class CanonicalDocument:
    document_id: UUID
    version_id: UUID
    title: str
    media_type: str
    blocks: tuple[CanonicalBlock, ...]

    def __post_init__(self) -> None:
        if not self.media_type or not self.blocks:
            raise ValueError("canonical document requires a media type and blocks")
        if len({block.block_id for block in self.blocks}) != len(self.blocks):
            raise ValueError("canonical block identifiers must be unique")
        if tuple(block.order for block in self.blocks) != tuple(range(len(self.blocks))):
            raise ValueError("canonical block order must be contiguous")

    def resolve(self, locator: SourceLocator) -> str:
        try:
            block = self.blocks[locator.block_index]
        except IndexError as exc:
            raise ValueError("source locator references a missing block") from exc
        if block.block_id != locator.block_id or block.page_number != locator.page_number:
            raise ValueError("source locator identity does not match its block")
        if locator.char_end > len(block.text):
            raise ValueError("source locator extends beyond its block")
        return block.text[locator.char_start : locator.char_end]


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    document_id: UUID
    version_id: UUID
    order: int
    text: str
    embedding_text: str
    token_count: int
    locators: tuple[SourceLocator, ...]
    heading_path: tuple[str, ...]
    page_number: int | None
    document_title: str

    def __post_init__(self) -> None:
        if len(self.chunk_id) != 64 or self.order < 0:
            raise ValueError("chunk identity is invalid")
        if not self.text.strip() or not self.embedding_text.strip():
            raise ValueError("chunk text and embedding input cannot be empty")
        if self.token_count < 1 or not self.locators:
            raise ValueError("chunk requires tokens and source locators")

    @classmethod
    def create(
        cls,
        *,
        document_id: UUID,
        version_id: UUID,
        order: int,
        text: str,
        token_count: int,
        locators: tuple[SourceLocator, ...],
        heading_path: tuple[str, ...],
        page_number: int | None,
        document_title: str,
    ) -> Chunk:
        identity = {
            "document_id": str(document_id),
            "version_id": str(version_id),
            "text": text,
            "locators": [locator.as_dict() for locator in locators],
        }
        chunk_id = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return cls(
            chunk_id=chunk_id,
            document_id=document_id,
            version_id=version_id,
            order=order,
            text=text,
            embedding_text=text,
            token_count=token_count,
            locators=locators,
            heading_path=heading_path,
            page_number=page_number,
            document_title=document_title,
        )

    def as_storage_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "version_id": self.version_id,
            "chunk_order": self.order,
            "original_text": self.text,
            "token_count": self.token_count,
            "locators": [locator.as_dict() for locator in self.locators],
            "heading_path": list(self.heading_path),
            "page_number": self.page_number,
            "document_title": self.document_title,
        }


@dataclass(frozen=True, slots=True)
class SearchResult:
    chunk: Chunk
    fused_score: float
    dense_rank: int | None
    lexical_rank: int | None


@dataclass(frozen=True, slots=True)
class EmbeddedChunk:
    chunk: Chunk
    embedding: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.embedding:
            raise ValueError("embedded chunk requires a vector")
