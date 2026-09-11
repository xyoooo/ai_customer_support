from __future__ import annotations

import pytest

from packages.rag_lab.models import (
    BlockKind,
    CanonicalBlock,
    CanonicalDocument,
    Chunk,
    IndexedChunk,
    SourceLocator,
)


def _block(*, block_id: str = "b0", order: int = 0, page: int | None = 1) -> CanonicalBlock:
    return CanonicalBlock(block_id, order, BlockKind.PARAGRAPH, "evidence", page_number=page)


def _locator(
    *, block_id: str = "b0", index: int = 0, end: int = 8, page: int | None = 1
) -> SourceLocator:
    return SourceLocator(block_id, index, 0, end, page)


def test_source_locator_and_block_validation_fail_closed() -> None:
    with pytest.raises(ValueError, match="block_id"):
        SourceLocator("", 0, 0, 1)
    with pytest.raises(ValueError, match="negative"):
        SourceLocator("b0", -1, 0, 1)
    with pytest.raises(ValueError, match="non-empty"):
        SourceLocator("b0", 0, 1, 1)
    with pytest.raises(ValueError, match="one-based"):
        SourceLocator("b0", 0, 0, 1, 0)

    with pytest.raises(ValueError, match="block_id"):
        CanonicalBlock("", 0, BlockKind.PARAGRAPH, "text")
    with pytest.raises(ValueError, match="negative"):
        CanonicalBlock("b0", -1, BlockKind.PARAGRAPH, "text")
    with pytest.raises(ValueError, match="empty"):
        CanonicalBlock("b0", 0, BlockKind.PARAGRAPH, " ")
    with pytest.raises(ValueError, match="normalized"):
        CanonicalBlock("b0", 0, BlockKind.PARAGRAPH, " text ")
    with pytest.raises(ValueError, match="one-based"):
        CanonicalBlock("b0", 0, BlockKind.PARAGRAPH, "text", page_number=0)


def test_document_validation_and_locator_resolution_fail_closed() -> None:
    block = _block()
    document = CanonicalDocument("doc", "version", "Guide", "application/pdf", (block,))
    assert document.resolve(_locator()) == "evidence"

    with pytest.raises(ValueError, match="identifiers"):
        CanonicalDocument("", "version", "Guide", "text/plain", (block,))
    with pytest.raises(ValueError, match="media_type"):
        CanonicalDocument("doc", "version", "Guide", "", (block,))
    with pytest.raises(ValueError, match="at least one"):
        CanonicalDocument("doc", "version", "Guide", "text/plain", ())
    with pytest.raises(ValueError, match="unique"):
        CanonicalDocument("doc", "version", "Guide", "text/plain", (block, block))
    with pytest.raises(ValueError, match="contiguous"):
        CanonicalDocument("doc", "version", "Guide", "text/plain", (_block(order=1),))

    with pytest.raises(ValueError, match="missing block"):
        document.resolve(_locator(index=1))
    with pytest.raises(ValueError, match="identity"):
        document.resolve(_locator(block_id="other"))
    with pytest.raises(ValueError, match="page"):
        document.resolve(_locator(page=2))
    with pytest.raises(ValueError, match="beyond"):
        document.resolve(_locator(end=9))


def test_chunk_creation_storage_and_validation() -> None:
    locator = _locator()
    chunk = Chunk.create(
        document_id="doc",
        version_id="version",
        order=0,
        text="evidence",
        embedding_text="evidence",
        token_count=1,
        locators=(locator,),
        heading_path=("Guide",),
        page_number=1,
        document_title="Guide",
    )
    assert len(chunk.chunk_id) == 64
    assert chunk.as_storage_dict()["locators"] == [locator.as_dict()]

    values = {
        "chunk_id": chunk.chunk_id,
        "document_id": "doc",
        "version_id": "version",
        "order": 0,
        "text": "evidence",
        "embedding_text": "evidence",
        "token_count": 1,
        "locators": (locator,),
        "heading_path": (),
        "page_number": 1,
    }
    for field, invalid, message in (
        ("chunk_id", "", "identity"),
        ("order", -1, "negative"),
        ("text", " ", "cannot be empty"),
        ("token_count", 0, "positive"),
        ("locators", (), "citations"),
    ):
        candidate = values | {field: invalid}
        with pytest.raises(ValueError, match=message):
            Chunk(**candidate)

    with pytest.raises(ValueError, match="workspace"):
        IndexedChunk("", chunk, (1.0,))
    with pytest.raises(ValueError, match="embedding"):
        IndexedChunk("workspace", chunk, ())
