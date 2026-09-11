from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace

from packages.rag.chunking import StructureAwareChunker
from packages.rag.embedding import E1Embedder, E1TokenBudget, ModelManifest, normalize_embedding
from packages.rag.lexical import BM25LexicalScorer, lexical_terms
from packages.rag.models import (
    BlockKind,
    CanonicalBlock,
    CanonicalDocument,
    Chunk,
    EmbeddedChunk,
    SourceLocator,
)
from packages.rag.parsing import CanonicalParser, _PdfLine
from packages.rag.repository import _fuse_rankings, _stored_chunk
from packages.rag.service import RAGIndexer, RetrievalService
from packages.rag.tokenizer import ChunkTokenizer

DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000201")
VERSION_ID = UUID("00000000-0000-0000-0000-000000000202")
WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000203")


class PermissiveBudget:
    def fits(self, text: str) -> bool:
        return bool(text.strip())

    def assert_fits(self, text: str) -> None:
        if not self.fits(text):
            raise ValueError("does not fit")


class LengthBudget:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum

    def fits(self, text: str) -> bool:
        return len(text) <= self.maximum

    def assert_fits(self, text: str) -> None:
        if not self.fits(text):
            raise ValueError("does not fit")


def make_chunk(
    identity: str,
    text: str,
    *,
    heading_path: tuple[str, ...] = (),
    document_title: str = "Guide",
) -> Chunk:
    return Chunk(
        chunk_id=identity * 64,
        document_id=DOCUMENT_ID,
        version_id=VERSION_ID,
        order=0,
        text=text,
        embedding_text=text,
        token_count=max(1, ChunkTokenizer().count(text)),
        locators=(SourceLocator("b000000", 0, 0, len(text)),),
        heading_path=heading_path,
        page_number=None,
        document_title=document_title,
    )


def write_tokenizer(path: Path) -> None:
    tokenizer = Tokenizer(
        WordLevel(
            {"[UNK]": 0, "one": 1, "two": 2, "three": 3, "query": 4},
            unk_token="[UNK]",
        )
    )
    tokenizer.pre_tokenizer = Whitespace()
    path.parent.mkdir(parents=True)
    tokenizer.save(str(path))


def test_models_validate_identity_and_resolve_citations() -> None:
    block = CanonicalBlock("b000000", 0, BlockKind.PARAGRAPH, "evidence", page_number=1)
    document = CanonicalDocument(DOCUMENT_ID, VERSION_ID, "Guide", "application/pdf", (block,))
    locator = SourceLocator("b000000", 0, 0, 8, 1)
    assert document.resolve(locator) == "evidence"
    chunk = Chunk.create(
        document_id=DOCUMENT_ID,
        version_id=VERSION_ID,
        order=0,
        text="evidence",
        token_count=1,
        locators=(locator,),
        heading_path=("Guide",),
        page_number=1,
        document_title="Guide",
    )
    assert len(chunk.chunk_id) == 64
    assert chunk.as_storage_dict()["locators"] == [locator.as_dict()]
    assert EmbeddedChunk(chunk, (1.0,)).embedding == (1.0,)

    for factory in (
        lambda: SourceLocator("", 0, 0, 1),
        lambda: SourceLocator("b", -1, 0, 1),
        lambda: SourceLocator("b", 0, 1, 1),
        lambda: SourceLocator("b", 0, 0, 1, 0),
        lambda: CanonicalBlock("", 0, BlockKind.PARAGRAPH, "text"),
        lambda: CanonicalBlock("b", -1, BlockKind.PARAGRAPH, "text"),
        lambda: CanonicalBlock("b", 0, BlockKind.PARAGRAPH, " text "),
        lambda: CanonicalBlock("b", 0, BlockKind.PARAGRAPH, "text", page_number=0),
        lambda: CanonicalDocument(DOCUMENT_ID, VERSION_ID, "", "", (block,)),
        lambda: CanonicalDocument(DOCUMENT_ID, VERSION_ID, "", "text/plain", ()),
        lambda: CanonicalDocument(DOCUMENT_ID, VERSION_ID, "", "text/plain", (block, block)),
        lambda: CanonicalDocument(
            DOCUMENT_ID,
            VERSION_ID,
            "",
            "text/plain",
            (CanonicalBlock("b1", 1, BlockKind.PARAGRAPH, "text"),),
        ),
        lambda: EmbeddedChunk(chunk, ()),
    ):
        with pytest.raises(ValueError):
            factory()

    with pytest.raises(ValueError, match="missing"):
        document.resolve(SourceLocator("b000001", 1, 0, 1, 1))
    with pytest.raises(ValueError, match="identity"):
        document.resolve(SourceLocator("other", 0, 0, 1, 1))
    with pytest.raises(ValueError, match="beyond"):
        document.resolve(SourceLocator("b000000", 0, 0, 9, 1))


def test_parser_preserves_markdown_html_and_plain_structure() -> None:
    parser = CanonicalParser()
    markdown = parser.parse(
        b"# Returns\nInternational returns take 30 days.\n\n## Steps\n- Pack item\n- Add label",
        document_id=DOCUMENT_ID,
        version_id=VERSION_ID,
        title=" Returns ",
        media_type="text/markdown",
    )
    assert [block.kind for block in markdown.blocks] == [
        BlockKind.HEADING,
        BlockKind.PARAGRAPH,
        BlockKind.HEADING,
        BlockKind.LIST_ITEM,
        BlockKind.LIST_ITEM,
    ]
    assert markdown.blocks[-1].heading_path == ("Returns", "Steps")
    assert markdown.title == "Returns"

    html = parser.parse(
        b"<h1>Billing</h1><p>Use <strong>invoice</strong> ID.</p><li>Open portal</li>",
        document_id=DOCUMENT_ID,
        version_id=VERSION_ID,
        title="Billing",
        media_type="text/html",
    )
    assert [block.text for block in html.blocks] == ["Billing", "Use invoice ID.", "Open portal"]

    plain = parser.parse(
        b"First paragraph.\r\n\r\nSecond paragraph.",
        document_id=DOCUMENT_ID,
        version_id=VERSION_ID,
        title="Plain",
        media_type="text/plain",
    )
    assert [block.text for block in plain.blocks] == ["First paragraph.", "Second paragraph."]


def test_parser_rejects_unsafe_or_unindexable_content() -> None:
    parser = CanonicalParser(max_characters=3)
    cases = ((b"", "text/plain"), (b"\xff", "text/plain"), (b"text", "application/json"))
    for content, media_type in cases:
        with pytest.raises(ValueError):
            parser.parse(
                content,
                document_id=DOCUMENT_ID,
                version_id=VERSION_ID,
                title="",
                media_type=media_type,
            )
    with pytest.raises(ValueError, match="limit"):
        parser.parse(
            b"four",
            document_id=DOCUMENT_ID,
            version_id=VERSION_ID,
            title="",
            media_type="text/plain",
        )


def test_pdf_layout_helpers_preserve_reading_order_and_paragraphs() -> None:
    lines = [
        _PdfLine("Section", 50, 66, 54, 150, 17, "Medium"),
        _PdfLine("left first", 100, 110, 54, 200, 9, "Regular"),
        _PdfLine("left second", 112, 122, 54, 200, 9, "Regular"),
        _PdfLine("right first", 100, 110, 343, 500, 9, "Regular"),
        _PdfLine("right second", 112, 122, 343, 500, 9, "Regular"),
    ]
    assert [line.text for line in CanonicalParser._reading_order(lines, 612)] == [
        "Section",
        "left first",
        "left second",
        "right first",
        "right second",
    ]
    paragraphs = CanonicalParser._pdf_paragraphs(
        [
            _PdfLine("Heading", 50, 64, 54, 160, 14, "Bold"),
            _PdfLine("A hyphen-", 80, 90, 54, 200, 9, "Regular"),
            _PdfLine("ated phrase.", 92, 102, 54, 200, 9, "Regular"),
            _PdfLine("• First item", 120, 130, 54, 200, 9, "Regular"),
            _PdfLine("continues here.", 132, 142, 68, 210, 9, "Regular"),
        ]
    )
    assert [paragraph.text for paragraph in paragraphs] == [
        "Heading",
        "A hyphenated phrase.",
        "• First item continues here.",
    ]
    assert CanonicalParser._reading_order([], 612) == []
    assert CanonicalParser._visual_heading_level(_PdfLine("T", 0, 1, 0, 1, 20, "R")) == 1
    assert CanonicalParser._visual_heading_level(_PdfLine("S", 0, 1, 0, 1, 16, "R")) == 2
    assert CanonicalParser._visual_heading_level(_PdfLine("B", 0, 1, 0, 1, 13, "Bold")) == 3
    assert CanonicalParser._visual_heading_level(_PdfLine("C", 0, 1, 0, 1, 11, "Bold")) == 4
    assert CanonicalParser._visual_heading_level(_PdfLine("P", 0, 1, 0, 1, 9, "R")) is None


def test_pdf_word_extraction_filters_margins_and_splits_columns() -> None:
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


def test_c1_is_deterministic_preserves_sections_and_uses_fallback() -> None:
    parser = CanonicalParser()
    document = parser.parse(
        (
            "# Returns\n" + " ".join(f"return{i}" for i in range(560)) + ".\n\n"
            "# Shipping\nDelivery takes two days."
        ).encode(),
        document_id=DOCUMENT_ID,
        version_id=VERSION_ID,
        title="Policies",
        media_type="text/markdown",
    )
    chunker = StructureAwareChunker(PermissiveBudget())
    first = chunker.chunk(document)
    assert first == chunker.chunk(document)
    assert len(first) >= 3
    assert all(chunk.token_count <= 500 for chunk in first)
    assert all("Shipping" not in chunk.text for chunk in first[:-1])
    assert all(document.resolve(locator) for chunk in first for locator in chunk.locators)

    with pytest.raises(ValueError, match="source token"):
        StructureAwareChunker(LengthBudget(1)).chunk(document)


def test_e1_manifest_budget_and_embedding_contract(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(RuntimeError, match="manifest"):
        ModelManifest.load(missing)
    model_path = tmp_path / "model"
    write_tokenizer(model_path / "tokenizer.json")
    (model_path / "supportpilot-model.json").write_text(
        json.dumps(
            {
                "artifact_id": "snowflake/snowflake-arctic-embed-xs",
                "artifact_revision": "d8c86521100d3556476a063fc2342036d45c106f",
                "dimension": 384,
            }
        ),
        encoding="utf-8",
    )
    assert ModelManifest.load(model_path).dimension == 384
    budget = E1TokenBudget(model_path)
    assert budget.fits("one two three")
    budget.assert_fits("one")

    vector = normalize_embedding([1.0] * 384)
    assert len(vector) == 384
    assert math.isclose(sum(value * value for value in vector), 1.0)
    for invalid in ([1.0], [0.0] * 384, [float("nan")] * 384):
        with pytest.raises(RuntimeError):
            normalize_embedding(invalid)

    class FakeModel:
        @staticmethod
        def embed(texts: list[str]):  # type: ignore[no-untyped-def]
            return ([1.0] * 384 for _ in texts)

    embedder = object.__new__(E1Embedder)
    embedder.tokenizer = Tokenizer.from_file(str(model_path / "tokenizer.json"))
    embedder.model = FakeModel()  # type: ignore[assignment]
    assert embedder.embed_documents(()) == ()
    assert len(embedder.embed_documents(("one",))[0]) == 384
    assert len(embedder.embed_queries(("one",))[0]) == 384
    with pytest.raises(ValueError, match="empty"):
        embedder.embed_documents((" ",))


def test_lexical_scorer_rewards_structure_identifiers_and_phrases() -> None:
    scorer = BM25LexicalScorer()
    relevant = make_chunk(
        "a",
        "Emergency Reset immediately stops digital sharing with code RET-30.",
        heading_path=("Safety Check", "Emergency Reset"),
        document_title="Apple Personal Safety User Guide",
    )
    noisy = make_chunk("b", "Apple devices provide settings and general information.")
    assert scorer.rank(
        "What should I use to stop sharing immediately with RET-30?", (noisy, relevant), limit=1
    ) == (relevant,)
    assert scorer.rank("the and what", (relevant,), limit=1) == ()
    assert scorer.rank("reset", (), limit=1) == ()
    assert set(lexical_terms("sharing")) & set(lexical_terms("share"))


def test_rank_fusion_and_stored_record_conversion_are_deterministic() -> None:
    first = make_chunk("a", "first")
    second = make_chunk("b", "second")
    results = _fuse_rankings((first, second), (second,), result_count=2)
    assert [result.chunk for result in results] == [second, first]
    assert results[0].dense_rank == 2
    assert results[0].lexical_rank == 1

    record = SimpleNamespace(
        chunk_id=first.chunk_id,
        document_id=DOCUMENT_ID,
        version_id=VERSION_ID,
        chunk_order=0,
        original_text="first",
        token_count=1,
        locators=[SourceLocator("b000000", 0, 0, 5).as_dict()],
        heading_path=["Heading"],
        page_number=None,
        document_title="Guide",
    )
    assert _stored_chunk(record).heading_path == ("Heading",)


@pytest.mark.asyncio
async def test_indexer_batches_and_retrieval_delegates() -> None:
    class FakeEmbedder:
        def __init__(self) -> None:
            self.document_calls: list[tuple[str, ...]] = []

        def embed_documents(self, texts):  # type: ignore[no-untyped-def]
            self.document_calls.append(tuple(texts))
            return tuple((1.0,) * 384 for _ in texts)

        def embed_queries(self, texts):  # type: ignore[no-untyped-def]
            assert texts == ("refund",)
            return ((1.0,) * 384,)

    embedder = FakeEmbedder()
    indexer = RAGIndexer(
        parser=CanonicalParser(),
        chunker=StructureAwareChunker(PermissiveBudget()),
        embedder=embedder,
        batch_size=1,
    )
    records = indexer.index_content(
        b"# Returns\nRefunds take 30 days.",
        document_id=DOCUMENT_ID,
        version_id=VERSION_ID,
        title="Guide",
        media_type="text/markdown",
    )
    assert records and len(embedder.document_calls) == len(records)

    class FakeRepository:
        async def search(self, session, **kwargs):  # type: ignore[no-untyped-def]
            assert session == "session"
            assert kwargs["workspace_id"] == WORKSPACE_ID
            assert len(kwargs["query_embedding"]) == 384
            return ()

    service = RetrievalService(embedder, FakeRepository())  # type: ignore[arg-type]
    assert (
        await service.search(
            "session",  # type: ignore[arg-type]
            workspace_id=WORKSPACE_ID,
            query="refund",
            result_count=5,
        )
        == ()
    )
