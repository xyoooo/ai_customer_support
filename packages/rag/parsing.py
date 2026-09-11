from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from typing import Any, ClassVar
from uuid import UUID

import pdfplumber
from pypdf import PdfReader

from packages.rag.models import BlockKind, CanonicalBlock, CanonicalDocument

_BLANK_LINES = re.compile(r"\n\s*\n+", flags=re.MULTILINE)
_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_MARKDOWN_LIST_ITEM = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+(.+)$")
_WHITESPACE = re.compile(r"\s+")
_BULLET = re.compile(r"^\s*(?:[•◦▪‣]|[-\u2013\u2014])\s*")
_PAGE_FOOTER = re.compile(r"^(?:Apple .+?\s+)?\d+$")


def normalize_block_text(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


@dataclass(slots=True)
class _BlockCollector:
    blocks: list[CanonicalBlock]
    headings: list[str]
    characters: int = 0

    def add(
        self,
        kind: BlockKind,
        text: str,
        *,
        page_number: int | None = None,
        heading_level: int | None = None,
    ) -> None:
        normalized = normalize_block_text(text)
        if not normalized:
            return
        if heading_level is not None:
            self.headings = self.headings[: heading_level - 1]
            self.headings.append(normalized)
        order = len(self.blocks)
        self.blocks.append(
            CanonicalBlock(
                f"b{order:06d}",
                order,
                kind,
                normalized,
                tuple(self.headings),
                page_number,
            )
        )
        self.characters += len(normalized)


@dataclass(frozen=True, slots=True)
class _PdfLine:
    text: str
    top: float
    bottom: float
    x0: float
    x1: float
    size: float
    fontname: str

    @property
    def is_bold(self) -> bool:
        name = self.fontname.casefold()
        return "bold" in name or "semibold" in name or "medium" in name


@dataclass(frozen=True, slots=True)
class _PdfParagraph:
    lines: tuple[_PdfLine, ...]

    @property
    def text(self) -> str:
        combined = self.lines[0].text
        for line in self.lines[1:]:
            if combined.endswith("-") and line.text[:1].islower():
                combined = combined[:-1] + line.text
            else:
                combined += " " + line.text
        return normalize_block_text(combined)


class _CanonicalHTMLParser(HTMLParser):
    _CAPTURE_TAGS: ClassVar[set[str]] = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self, collector: _BlockCollector) -> None:
        super().__init__(convert_charrefs=True)
        self.collector = collector
        self.capture_tag: str | None = None
        self.capture_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized = tag.lower()
        if self.capture_tag is None and normalized in self._CAPTURE_TAGS:
            self.capture_tag = normalized
            self.capture_depth = 1
            self.parts = []
        elif self.capture_tag is not None:
            self.capture_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self.capture_tag is None:
            return
        self.capture_depth -= 1
        if self.capture_depth > 0 or tag.lower() != self.capture_tag:
            return
        captured = self.capture_tag
        text = " ".join(self.parts)
        self.capture_tag = None
        self.parts = []
        if captured.startswith("h"):
            self.collector.add(BlockKind.HEADING, text, heading_level=int(captured[1]))
        elif captured == "li":
            self.collector.add(BlockKind.LIST_ITEM, text)
        else:
            self.collector.add(BlockKind.PARAGRAPH, text)

    def handle_data(self, data: str) -> None:
        if self.capture_tag is not None:
            self.parts.append(data)


class CanonicalParser:
    identifier = "canonical-parser-v2-layout"

    def __init__(self, *, max_pages: int = 1000, max_characters: int = 5_000_000) -> None:
        self.max_pages = max_pages
        self.max_characters = max_characters

    def parse(
        self,
        content: bytes,
        *,
        document_id: UUID,
        version_id: UUID,
        title: str,
        media_type: str,
    ) -> CanonicalDocument:
        if not content:
            raise ValueError("cannot parse an empty document")
        collector = _BlockCollector([], [])
        if media_type == "application/pdf":
            self._parse_pdf(content, collector)
        else:
            try:
                decoded = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("text documents must be UTF-8 encoded") from exc
            if len(decoded) > self.max_characters:
                raise ValueError("document exceeds the parsed text limit")
            if media_type == "text/markdown":
                self._parse_markdown(decoded, collector)
            elif media_type == "text/html":
                parser = _CanonicalHTMLParser(collector)
                parser.feed(decoded)
                parser.close()
            elif media_type == "text/plain":
                self._parse_plain_text(decoded, collector)
            else:
                raise ValueError(f"unsupported media type: {media_type}")
        if not collector.blocks:
            raise ValueError("document contains no indexable text")
        if collector.characters > self.max_characters:
            raise ValueError("document exceeds the parsed text limit")
        return CanonicalDocument(
            document_id,
            version_id,
            normalize_block_text(title),
            media_type,
            tuple(collector.blocks),
        )

    @staticmethod
    def _parse_plain_text(text: str, collector: _BlockCollector) -> None:
        for paragraph in _BLANK_LINES.split(text.replace("\r\n", "\n")):
            collector.add(BlockKind.PARAGRAPH, paragraph)

    @staticmethod
    def _parse_markdown(text: str, collector: _BlockCollector) -> None:
        paragraph: list[str] = []

        def flush() -> None:
            if paragraph:
                collector.add(BlockKind.PARAGRAPH, " ".join(paragraph))
                paragraph.clear()

        for raw_line in text.replace("\r\n", "\n").split("\n"):
            line = raw_line.rstrip()
            heading = _MARKDOWN_HEADING.match(line)
            item = _MARKDOWN_LIST_ITEM.match(line)
            if heading:
                flush()
                collector.add(
                    BlockKind.HEADING,
                    heading.group(2),
                    heading_level=len(heading.group(1)),
                )
            elif item:
                flush()
                collector.add(BlockKind.LIST_ITEM, item.group(1))
            elif not line.strip():
                flush()
            else:
                paragraph.append(line.strip())
        flush()

    def _parse_pdf(self, content: bytes, collector: _BlockCollector) -> None:
        try:
            reader = PdfReader(BytesIO(content))
            if len(reader.pages) > self.max_pages:
                raise ValueError("PDF exceeds the page limit")
            outlines = self._outline_levels(reader)
            with pdfplumber.open(BytesIO(content)) as pdf:
                for page_number, page in enumerate(pdf.pages, start=1):
                    page_outline = outlines.get(page_number, {})
                    for paragraph in self._pdf_paragraphs(self._pdf_lines(page)):
                        text = paragraph.text
                        first = paragraph.lines[0]
                        heading_level = page_outline.get(text.casefold())
                        if heading_level is None:
                            heading_level = self._visual_heading_level(first)
                        if heading_level is not None:
                            collector.add(
                                BlockKind.HEADING,
                                text,
                                page_number=page_number,
                                heading_level=heading_level,
                            )
                        elif _BULLET.match(text):
                            collector.add(
                                BlockKind.LIST_ITEM,
                                _BULLET.sub("", text, count=1),
                                page_number=page_number,
                            )
                        else:
                            collector.add(BlockKind.PARAGRAPH, text, page_number=page_number)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("PDF could not be parsed") from exc

    @staticmethod
    def _outline_levels(reader: PdfReader) -> dict[int, dict[str, int]]:
        result: dict[int, dict[str, int]] = {}

        def visit(items: list[Any], depth: int = 0) -> None:
            for item in items:
                if isinstance(item, list):
                    visit(item, depth + 1)
                    continue
                try:
                    page_index = reader.get_destination_page_number(item)
                except Exception:
                    page_index = None
                if page_index is None:
                    continue
                title = normalize_block_text(str(getattr(item, "title", "")))
                if title:
                    result.setdefault(page_index + 1, {})[title.casefold()] = min(depth + 1, 6)

        visit(reader.outline)
        return result

    @staticmethod
    def _pdf_lines(page: Any) -> list[_PdfLine]:
        words = page.extract_words(
            extra_attrs=["fontname", "size"],
            keep_blank_chars=False,
            use_text_flow=False,
        )
        rows: list[list[dict[str, Any]]] = []
        for word in sorted(words, key=lambda value: (round(float(value["top"]), 1), value["x0"])):
            top = float(word["top"])
            row = next(
                (
                    candidate
                    for candidate in reversed(rows[-3:])
                    if abs(float(candidate[0]["top"]) - top) <= 2.0
                ),
                None,
            )
            if row is None:
                row = []
                rows.append(row)
            row.append(word)

        lines: list[_PdfLine] = []
        for row in rows:
            segments: list[list[dict[str, Any]]] = []
            for word in sorted(row, key=lambda value: float(value["x0"])):
                if segments and float(word["x0"]) - float(segments[-1][-1]["x1"]) > 36:
                    segments.append([])
                if not segments:
                    segments.append([])
                segments[-1].append(word)
            for segment in segments:
                text = normalize_block_text(" ".join(str(word["text"]) for word in segment))
                top = min(float(word["top"]) for word in segment)
                bottom = max(float(word["bottom"]) for word in segment)
                size = max(float(word["size"]) for word in segment)
                if not text or (len(text) <= 2 and not text.isalnum()):
                    continue
                if top < 35 or bottom > float(page.height) - 35:
                    continue
                if size <= 7.5 and _PAGE_FOOTER.match(text):
                    continue
                fonts = [str(word["fontname"]) for word in segment]
                font = max(fonts, key=lambda value: ("bold" in value.casefold(), len(value)))
                lines.append(
                    _PdfLine(
                        text,
                        top,
                        bottom,
                        min(float(word["x0"]) for word in segment),
                        max(float(word["x1"]) for word in segment),
                        size,
                        font,
                    )
                )
        return CanonicalParser._reading_order(lines, float(page.width))

    @staticmethod
    def _reading_order(lines: list[_PdfLine], page_width: float) -> list[_PdfLine]:
        if not lines:
            return []
        ordered = sorted(lines, key=lambda line: (line.top, line.x0))
        bands: list[list[_PdfLine]] = []
        for line in ordered:
            if bands and line.top - max(item.bottom for item in bands[-1]) > 45:
                bands.append([])
            if not bands:
                bands.append([])
            bands[-1].append(line)
        result: list[_PdfLine] = []
        midpoint = page_width / 2
        for band in bands:
            left = [line for line in band if line.x1 < midpoint - 5]
            right = [line for line in band if line.x0 > midpoint + 5]
            spanning = [line for line in band if line not in left and line not in right]
            if len(left) < 2 or len(right) < 2:
                result.extend(sorted(band, key=lambda line: (line.top, line.x0)))
            else:
                result.extend(sorted(spanning, key=lambda line: (line.top, line.x0)))
                result.extend(sorted(left, key=lambda line: (line.top, line.x0)))
                result.extend(sorted(right, key=lambda line: (line.top, line.x0)))
        return result

    @staticmethod
    def _visual_heading_level(line: _PdfLine) -> int | None:
        if line.size >= 19:
            return 1
        if line.size >= 16:
            return 2
        if line.size >= 13 and line.is_bold:
            return 3
        if line.size >= 10.5 and line.is_bold:
            return 4
        return None

    @classmethod
    def _pdf_paragraphs(cls, lines: list[_PdfLine]) -> list[_PdfParagraph]:
        paragraphs: list[list[_PdfLine]] = []
        for line in lines:
            heading = cls._visual_heading_level(line) is not None
            bullet = _BULLET.match(line.text) is not None
            callout = line.is_bold and len(line.text) <= 24
            if not paragraphs or heading or bullet or callout:
                paragraphs.append([line])
                continue
            previous = paragraphs[-1][-1]
            previous_heading = cls._visual_heading_level(previous) is not None
            previous_bullet = _BULLET.match(paragraphs[-1][0].text) is not None
            if previous_bullet:
                same_column = 8 <= line.x0 - paragraphs[-1][0].x0 <= 40
            else:
                same_column = abs(line.x0 - previous.x0) <= 24
            close = 0 <= line.top - previous.bottom <= max(9, previous.size * 1.2)
            if not previous_heading and same_column and close:
                paragraphs[-1].append(line)
            else:
                paragraphs.append([line])
        return [_PdfParagraph(tuple(paragraph)) for paragraph in paragraphs]
