from __future__ import annotations

import pytest

from packages.rag_lab.chunking import FixedTokenChunker, StructureAwareChunker
from packages.rag_lab.models import BlockKind, CanonicalBlock, CanonicalDocument
from packages.rag_lab.parsing import CanonicalParser
from packages.rag_lab.profiles import ChunkerSpec
from packages.rag_lab.tokenizer import RegexTokenizer


def _spec(candidate: str, *, target: int, maximum: int, overlap: int) -> ChunkerSpec:
    return ChunkerSpec(
        candidate_id=candidate,
        implementation_version="test",
        target_tokens=target,
        max_tokens=maximum,
        overlap_tokens=overlap,
        boundary_policy="test",
        context_policy=("original" if candidate != "C2" else "document-title-and-heading-path"),
    )


def test_canonical_parser_preserves_markdown_and_html_structure() -> None:
    parser = CanonicalParser()
    markdown = parser.parse(
        b"# Returns\nInternational returns take 30 days.\n\n## Steps\n- Pack item\n- Add label",
        document_id="doc",
        version_id="v1",
        title="Returns",
        media_type="text/markdown",
    )
    assert [block.kind for block in markdown.blocks] == [
        BlockKind.HEADING,
        BlockKind.PARAGRAPH,
        BlockKind.HEADING,
        BlockKind.LIST_ITEM,
        BlockKind.LIST_ITEM,
    ]
    assert markdown.blocks[1].heading_path == ("Returns",)
    assert markdown.blocks[-1].heading_path == ("Returns", "Steps")

    html = parser.parse(
        b"<h1>Billing</h1><p>Use <strong>invoice</strong> ID.</p><ul><li>Open portal</li></ul>",
        document_id="doc-html",
        version_id="v2",
        title="Billing",
        media_type="text/html",
    )
    assert [block.text for block in html.blocks] == ["Billing", "Use invoice ID.", "Open portal"]
    assert html.blocks[-1].kind is BlockKind.LIST_ITEM


def test_parser_rejects_empty_unknown_and_malformed_documents() -> None:
    parser = CanonicalParser()
    with pytest.raises(ValueError, match="empty"):
        parser.parse(
            b"",
            document_id="d",
            version_id="v",
            title="",
            media_type="text/plain",
        )
    with pytest.raises(ValueError, match="UTF-8"):
        parser.parse(
            b"\xff",
            document_id="d",
            version_id="v",
            title="",
            media_type="text/plain",
        )
    with pytest.raises(ValueError, match="unsupported"):
        parser.parse(
            b"content",
            document_id="d",
            version_id="v",
            title="",
            media_type="application/json",
        )


def test_fixed_token_control_has_stable_overlap_and_no_duplicate_final_chunk() -> None:
    document = CanonicalParser().parse(
        b"one two three four five six seven eight",
        document_id="doc",
        version_id="v1",
        title="Numbers",
        media_type="text/plain",
    )
    chunker = FixedTokenChunker(_spec("C0", target=5, maximum=5, overlap=2))
    first = chunker.chunk(document)
    second = chunker.chunk(document)

    assert first == second
    assert [chunk.text for chunk in first] == [
        "one two three four five",
        "four five six seven eight",
    ]
    assert all(chunk.token_count <= 5 for chunk in first)
    assert len({chunk.chunk_id for chunk in first}) == 2
    for chunk in first:
        assert "\n\n".join(document.resolve(locator) for locator in chunk.locators) == chunk.text


def test_fixed_token_control_never_crosses_pdf_pages() -> None:
    document = CanonicalDocument(
        "doc",
        "version",
        "PDF",
        "application/pdf",
        (
            CanonicalBlock("b000000", 0, BlockKind.PARAGRAPH, "one two three", page_number=1),
            CanonicalBlock("b000001", 1, BlockKind.PARAGRAPH, "four five", page_number=2),
        ),
    )
    chunks = FixedTokenChunker(_spec("C0", target=4, maximum=4, overlap=1)).chunk(document)
    assert [chunk.page_number for chunk in chunks] == [1, 2]
    assert all(len({locator.page_number for locator in chunk.locators}) == 1 for chunk in chunks)


def test_structure_candidates_share_chunks_but_only_c2_adds_context() -> None:
    document = CanonicalParser().parse(
        b"# Returns\nItems may be returned within thirty days.\n\n"
        b"# Shipping\nDelivery takes two days.",
        document_id="doc",
        version_id="v1",
        title="Customer Policies",
        media_type="text/markdown",
    )
    c1 = StructureAwareChunker(_spec("C1", target=20, maximum=25, overlap=3)).chunk(document)
    c2 = StructureAwareChunker(_spec("C2", target=20, maximum=25, overlap=3)).chunk(document)

    assert len(c1) == len(c2) == 2
    assert [(chunk.chunk_id, chunk.text, chunk.locators) for chunk in c1] == [
        (chunk.chunk_id, chunk.text, chunk.locators) for chunk in c2
    ]
    assert all(chunk.embedding_text == chunk.text for chunk in c1)
    assert c2[0].embedding_text.startswith("Document: Customer Policies\nSection: Returns\n\n")
    assert "Shipping" not in c1[0].text


def test_structure_chunker_uses_sentence_then_token_fallback_under_hard_limit() -> None:
    text = " ".join(f"token{index}" for index in range(22)) + "."
    document = CanonicalParser().parse(
        text.encode(),
        document_id="doc",
        version_id="v1",
        title="Long",
        media_type="text/plain",
    )
    chunker = StructureAwareChunker(_spec("C1", target=6, maximum=8, overlap=2))
    chunks = chunker.chunk(document)

    assert len(chunks) >= 4
    assert all(chunk.token_count <= 8 for chunk in chunks)
    assert chunks == chunker.chunk(document)
    source_tokens = {token.text for token in RegexTokenizer().spans(text)}
    chunk_tokens = {token.text for chunk in chunks for token in RegexTokenizer().spans(chunk.text)}
    assert source_tokens <= chunk_tokens
