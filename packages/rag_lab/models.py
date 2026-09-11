from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class BlockKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"


@dataclass(frozen=True, slots=True)
class SourceLocator:
    """A resolvable span within one canonical source block."""

    block_id: str
    block_index: int
    char_start: int
    char_end: int
    page_number: int | None = None

    def __post_init__(self) -> None:
        if not self.block_id:
            raise ValueError("source locator block_id cannot be empty")
        if self.block_index < 0:
            raise ValueError("source locator block_index cannot be negative")
        if self.char_start < 0 or self.char_end <= self.char_start:
            raise ValueError("source locator must contain a non-empty character span")
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
        if not self.block_id:
            raise ValueError("canonical block_id cannot be empty")
        if self.order < 0:
            raise ValueError("canonical block order cannot be negative")
        if not self.text.strip():
            raise ValueError("canonical block text cannot be empty")
        if self.text != self.text.strip():
            raise ValueError("canonical block text must be normalized")
        if self.page_number is not None and self.page_number < 1:
            raise ValueError("PDF page numbers are one-based")


@dataclass(frozen=True, slots=True)
class CanonicalDocument:
    document_id: str
    version_id: str
    title: str
    media_type: str
    blocks: tuple[CanonicalBlock, ...]

    def __post_init__(self) -> None:
        if not self.document_id or not self.version_id:
            raise ValueError("document and version identifiers are required")
        if not self.media_type:
            raise ValueError("document media_type is required")
        if not self.blocks:
            raise ValueError("a canonical document must contain at least one block")
        ids = {block.block_id for block in self.blocks}
        if len(ids) != len(self.blocks):
            raise ValueError("canonical block identifiers must be unique")
        if tuple(block.order for block in self.blocks) != tuple(range(len(self.blocks))):
            raise ValueError("canonical block order must be contiguous and deterministic")

    def resolve(self, locator: SourceLocator) -> str:
        try:
            block = self.blocks[locator.block_index]
        except IndexError as exc:
            raise ValueError("source locator references a missing block") from exc
        if block.block_id != locator.block_id:
            raise ValueError("source locator block identity does not match its index")
        if block.page_number != locator.page_number:
            raise ValueError("source locator page does not match its block")
        if locator.char_end > len(block.text):
            raise ValueError("source locator extends beyond its block")
        return block.text[locator.char_start : locator.char_end]


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    document_id: str
    version_id: str
    order: int
    text: str
    embedding_text: str
    token_count: int
    locators: tuple[SourceLocator, ...]
    heading_path: tuple[str, ...]
    page_number: int | None
    document_title: str = ""

    def __post_init__(self) -> None:
        if not self.chunk_id or not self.document_id or not self.version_id:
            raise ValueError("chunk identity fields are required")
        if self.order < 0:
            raise ValueError("chunk order cannot be negative")
        if not self.text.strip() or not self.embedding_text.strip():
            raise ValueError("chunk text and embedding input cannot be empty")
        if self.token_count < 1:
            raise ValueError("chunk token_count must be positive")
        if not self.locators:
            raise ValueError("chunk citations cannot be empty")

    @classmethod
    def create(
        cls,
        *,
        document_id: str,
        version_id: str,
        order: int,
        text: str,
        embedding_text: str,
        token_count: int,
        locators: tuple[SourceLocator, ...],
        heading_path: tuple[str, ...],
        page_number: int | None,
        document_title: str = "",
    ) -> Chunk:
        identity = {
            "document_id": document_id,
            "version_id": version_id,
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
            embedding_text=embedding_text,
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
            "embedding_text": self.embedding_text,
            "token_count": self.token_count,
            "locators": [locator.as_dict() for locator in self.locators],
            "heading_path": list(self.heading_path),
            "page_number": self.page_number,
            "document_title": self.document_title,
        }


@dataclass(frozen=True, slots=True)
class IndexedChunk:
    workspace_id: str
    chunk: Chunk
    embedding: tuple[float, ...]
    active: bool = True

    def __post_init__(self) -> None:
        if not self.workspace_id:
            raise ValueError("indexed chunks require a workspace")
        if not self.embedding:
            raise ValueError("indexed chunks require an embedding")


@dataclass(frozen=True, slots=True)
class SearchResult:
    workspace_id: str
    chunk: Chunk
    fused_score: float
    dense_rank: int | None
    lexical_rank: int | None


@dataclass(frozen=True, slots=True)
class RetrievalTrace:
    results: tuple[SearchResult, ...]
    dense: tuple[Chunk, ...]
    lexical: tuple[Chunk, ...]
