from __future__ import annotations

import pytest

from packages.rag_lab.chunking import FixedTokenChunker, StructureAwareChunker
from packages.rag_lab.models import BlockKind, CanonicalBlock, CanonicalDocument
from packages.rag_lab.parsing import CanonicalParser, _PdfLine
from packages.rag_lab.profiles import ChunkerSpec
from packages.rag_lab.token_budget import RegexInputBudget
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


def test_pdf_layout_helpers_preserve_columns_paragraphs_and_lists() -> None:
    lines = [
        _PdfLine("Section", 50, 66, 54, 150, 17, "SFPro-Medium"),
        _PdfLine("left first", 100, 110, 54, 200, 9, "SFPro-Regular"),
        _PdfLine("left second", 112, 122, 54, 200, 9, "SFPro-Regular"),
        _PdfLine("right first", 100, 110, 343, 500, 9, "SFPro-Regular"),
        _PdfLine("right second", 112, 122, 343, 500, 9, "SFPro-Regular"),
    ]
    ordered = CanonicalParser._reading_order(lines, 612)
    assert [line.text for line in ordered] == [
        "Section",
        "left first",
        "left second",
        "right first",
        "right second",
    ]

    paragraphs = CanonicalParser._pdf_paragraphs(
        [
            _PdfLine("Heading", 50, 64, 54, 160, 14, "SFPro-Medium"),
            _PdfLine("A hyphen-", 80, 90, 54, 200, 9, "SFPro-Regular"),
            _PdfLine("ated phrase.", 92, 102, 54, 200, 9, "SFPro-Regular"),
            _PdfLine("• First item", 120, 130, 54, 200, 9, "SFPro-Regular"),
            _PdfLine("continues here.", 132, 142, 68, 210, 9, "SFPro-Regular"),
        ]
    )
    assert [paragraph.text for paragraph in paragraphs] == [
        "Heading",
        "A hyphenated phrase.",
        "• First item continues here.",
    ]


def test_pdf_word_extraction_filters_margins_and_preserves_segments() -> None:
    class FakePage:
        width = 612
        height = 792

        @staticmethod
        def extract_words(**kwargs: object) -> list[dict[str, object]]:
            assert kwargs["extra_attrs"] == ["fontname", "size"]
            return [
                {
                    "text": "Header",
                    "top": 10,
                    "bottom": 20,
                    "x0": 40,
                    "x1": 80,
                    "size": 9,
                    "fontname": "Regular",
                },
                {
                    "text": "Left",
                    "top": 100,
                    "bottom": 110,
                    "x0": 40,
                    "x1": 80,
                    "size": 11,
                    "fontname": "Regular",
                },
                {
                    "text": "bold",
                    "top": 100.5,
                    "bottom": 111,
                    "x0": 86,
                    "x1": 120,
                    "size": 11,
                    "fontname": "Semibold",
                },
                {
                    "text": "Right",
                    "top": 100,
                    "bottom": 110,
                    "x0": 300,
                    "x1": 345,
                    "size": 9,
                    "fontname": "Regular",
                },
                {
                    "text": "•",
                    "top": 130,
                    "bottom": 140,
                    "x0": 40,
                    "x1": 45,
                    "size": 9,
                    "fontname": "Regular",
                },
                {
                    "text": "Apple Guide 7",
                    "top": 740,
                    "bottom": 750,
                    "x0": 40,
                    "x1": 100,
                    "size": 7,
                    "fontname": "Regular",
                },
                {
                    "text": "Footer",
                    "top": 770,
                    "bottom": 785,
                    "x0": 40,
                    "x1": 80,
                    "size": 9,
                    "fontname": "Regular",
                },
            ]

    lines = CanonicalParser._pdf_lines(FakePage())

    assert [line.text for line in lines] == ["Left bold", "Right"]
    assert lines[0].fontname == "Semibold"
    assert lines[0].is_bold
    assert CanonicalParser._reading_order([], 612) == []
    assert CanonicalParser._visual_heading_level(_PdfLine("Title", 0, 1, 0, 1, 20, "Regular")) == 1
    assert CanonicalParser._visual_heading_level(_PdfLine("Sub", 0, 1, 0, 1, 17, "Regular")) == 2
    assert CanonicalParser._visual_heading_level(_PdfLine("Callout", 0, 1, 0, 1, 11, "Bold")) == 4
    assert CanonicalParser._visual_heading_level(_PdfLine("Body", 0, 1, 0, 1, 9, "Regular")) is None


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


def test_structure_candidates_share_boundaries_under_embedding_budget() -> None:
    document = CanonicalParser().parse(
        b"# Long section\nOne two three four five six seven eight nine ten eleven twelve.",
        document_id="doc",
        version_id="v1",
        title="Budget",
        media_type="text/markdown",
    )
    budget = RegexInputBudget(15)
    c1 = StructureAwareChunker(_spec("C1", target=20, maximum=25, overlap=2), budget=budget).chunk(
        document
    )
    c2 = StructureAwareChunker(_spec("C2", target=20, maximum=25, overlap=2), budget=budget).chunk(
        document
    )

    assert [(chunk.text, chunk.locators) for chunk in c1] == [
        (chunk.text, chunk.locators) for chunk in c2
    ]
    assert len(c1) > 1
    assert all(budget.fits(chunk.embedding_text) for chunk in c2)
