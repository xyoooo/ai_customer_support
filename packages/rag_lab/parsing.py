from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from typing import ClassVar

from pypdf import PdfReader

from packages.rag_lab.models import BlockKind, CanonicalBlock, CanonicalDocument

_BLANK_LINES = re.compile(r"\n\s*\n+", flags=re.MULTILINE)
_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_MARKDOWN_LIST_ITEM = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+(.+)$")
_WHITESPACE = re.compile(r"\s+")


def normalize_block_text(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


@dataclass(slots=True)
class _BlockCollector:
    blocks: list[CanonicalBlock]
    heading_levels: list[str]

    @classmethod
    def create(cls) -> _BlockCollector:
        return cls(blocks=[], heading_levels=[])

    @property
    def heading_path(self) -> tuple[str, ...]:
        return tuple(self.heading_levels)

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
            self.heading_levels = self.heading_levels[: heading_level - 1]
            self.heading_levels.append(normalized)
        order = len(self.blocks)
        self.blocks.append(
            CanonicalBlock(
                block_id=f"b{order:06d}",
                order=order,
                kind=kind,
                text=normalized,
                heading_path=self.heading_path,
                page_number=page_number,
            )
        )


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
        captured_tag = self.capture_tag
        text = " ".join(self.parts)
        self.capture_tag = None
        self.parts = []
        if captured_tag.startswith("h"):
            self.collector.add(
                BlockKind.HEADING,
                text,
                heading_level=int(captured_tag[1]),
            )
        elif captured_tag == "li":
            self.collector.add(BlockKind.LIST_ITEM, text)
        else:
            self.collector.add(BlockKind.PARAGRAPH, text)

    def handle_data(self, data: str) -> None:
        if self.capture_tag is not None:
            self.parts.append(data)


class CanonicalParser:
    identifier = "canonical-parser-v1"

    def parse(
        self,
        content: bytes,
        *,
        document_id: str,
        version_id: str,
        title: str,
        media_type: str,
    ) -> CanonicalDocument:
        if not content:
            raise ValueError("cannot parse an empty document")
        collector = _BlockCollector.create()
        if media_type == "application/pdf":
            self._parse_pdf(content, collector)
        else:
            try:
                decoded = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("text documents must be UTF-8 encoded") from exc
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
        return CanonicalDocument(
            document_id=document_id,
            version_id=version_id,
            title=normalize_block_text(title),
            media_type=media_type,
            blocks=tuple(collector.blocks),
        )

    def _parse_plain_text(
        self,
        text: str,
        collector: _BlockCollector,
        *,
        page_number: int | None = None,
    ) -> None:
        for paragraph in _BLANK_LINES.split(text.replace("\r\n", "\n")):
            collector.add(BlockKind.PARAGRAPH, paragraph, page_number=page_number)

    def _parse_markdown(self, text: str, collector: _BlockCollector) -> None:
        paragraph_lines: list[str] = []

        def flush_paragraph() -> None:
            if paragraph_lines:
                collector.add(BlockKind.PARAGRAPH, " ".join(paragraph_lines))
                paragraph_lines.clear()

        for raw_line in text.replace("\r\n", "\n").split("\n"):
            line = raw_line.rstrip()
            heading = _MARKDOWN_HEADING.match(line)
            list_item = _MARKDOWN_LIST_ITEM.match(line)
            if heading:
                flush_paragraph()
                collector.add(
                    BlockKind.HEADING,
                    heading.group(2),
                    heading_level=len(heading.group(1)),
                )
            elif list_item:
                flush_paragraph()
                collector.add(BlockKind.LIST_ITEM, list_item.group(1))
            elif not line.strip():
                flush_paragraph()
            else:
                paragraph_lines.append(line.strip())
        flush_paragraph()

    def _parse_pdf(self, content: bytes, collector: _BlockCollector) -> None:
        try:
            reader = PdfReader(BytesIO(content))
            for page_number, page in enumerate(reader.pages, start=1):
                self._parse_plain_text(
                    page.extract_text() or "",
                    collector,
                    page_number=page_number,
                )
        except Exception as exc:
            raise ValueError("PDF could not be parsed") from exc
