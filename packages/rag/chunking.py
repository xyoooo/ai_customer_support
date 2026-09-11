from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import groupby
from typing import Protocol

from packages.rag.config import PIPELINE
from packages.rag.models import CanonicalBlock, CanonicalDocument, Chunk, SourceLocator
from packages.rag.tokenizer import ChunkTokenizer, TokenSpan

_SENTENCE_PATTERN = re.compile(r"[^.!?]+(?:[.!?]+(?=\s|$)|$)", flags=re.DOTALL)


class InputBudget(Protocol):
    def fits(self, text: str) -> bool: ...

    def assert_fits(self, text: str) -> None: ...


@dataclass(frozen=True, slots=True)
class _Fragment:
    block: CanonicalBlock
    char_start: int
    char_end: int
    token_count: int

    @property
    def text(self) -> str:
        return self.block.text[self.char_start : self.char_end]

    @property
    def locator(self) -> SourceLocator:
        return SourceLocator(
            self.block.block_id,
            self.block.order,
            self.char_start,
            self.char_end,
            self.block.page_number,
        )


def _fragment_from_tokens(block: CanonicalBlock, tokens: tuple[TokenSpan, ...]) -> _Fragment:
    if not tokens:
        raise ValueError("cannot create a fragment without tokens")
    return _Fragment(block, tokens[0].start, tokens[-1].end, len(tokens))


def _merge_fragments(fragments: list[_Fragment]) -> list[_Fragment]:
    merged: list[_Fragment] = []
    for fragment in fragments:
        if merged and merged[-1].block.block_id == fragment.block.block_id:
            previous = merged[-1]
            merged[-1] = _Fragment(
                previous.block,
                min(previous.char_start, fragment.char_start),
                max(previous.char_end, fragment.char_end),
                0,
            )
        else:
            merged.append(fragment)
    tokenizer = ChunkTokenizer()
    return [
        _Fragment(item.block, item.char_start, item.char_end, tokenizer.count(item.text))
        for item in merged
    ]


def _common_heading_path(fragments: list[_Fragment]) -> tuple[str, ...]:
    paths = [fragment.block.heading_path for fragment in fragments]
    if not paths:
        return ()
    common: list[str] = []
    for values in zip(*paths, strict=False):
        if len(set(values)) != 1:
            break
        common.append(values[0])
    return tuple(common)


def _budget_text(document: CanonicalDocument, fragments: list[_Fragment]) -> str:
    merged = _merge_fragments(fragments)
    text = "\n\n".join(fragment.text for fragment in merged)
    section = " > ".join(_common_heading_path(merged)) or "[root]"
    title = document.title or "[untitled]"
    return f"Document: {title}\nSection: {section}\n\n{text}"


def _tail_overlap(fragments: list[_Fragment], limit: int) -> list[_Fragment]:
    if limit <= 0:
        return []
    tokenizer = ChunkTokenizer()
    selected: list[_Fragment] = []
    remaining = limit
    for fragment in reversed(fragments):
        if remaining <= 0:
            break
        tokens = tokenizer.spans(fragment.text)
        if len(tokens) <= remaining:
            selected.append(fragment)
            remaining -= len(tokens)
            continue
        suffix = tokens[-remaining:]
        selected.append(
            _Fragment(
                fragment.block,
                fragment.char_start + suffix[0].start,
                fragment.char_start + suffix[-1].end,
                len(suffix),
            )
        )
        remaining = 0
    selected.reverse()
    return selected


class StructureAwareChunker:
    """The selected C1 heading/paragraph/sentence/token chunker."""

    def __init__(self, budget: InputBudget) -> None:
        self.budget = budget
        self.tokenizer = ChunkTokenizer()

    def chunk(self, document: CanonicalDocument) -> tuple[Chunk, ...]:
        chunks: list[Chunk] = []

        def section_key(block: CanonicalBlock) -> tuple[int | None, tuple[str, ...]]:
            return block.page_number, block.heading_path

        for _, block_group in groupby(document.blocks, key=section_key):
            pieces = [piece for block in block_group for piece in self._split_block(block)]
            for fragments in self._pack_section(document, pieces):
                merged = _merge_fragments(fragments)
                text = "\n\n".join(fragment.text for fragment in merged)
                heading_path = _common_heading_path(merged)
                pages = {fragment.block.page_number for fragment in merged}
                chunk = Chunk.create(
                    document_id=document.document_id,
                    version_id=document.version_id,
                    order=len(chunks),
                    text=text,
                    token_count=self.tokenizer.count(text),
                    locators=tuple(fragment.locator for fragment in merged),
                    heading_path=heading_path,
                    page_number=next(iter(pages)) if len(pages) == 1 else None,
                    document_title=document.title,
                )
                self.budget.assert_fits(chunk.embedding_text)
                chunks.append(chunk)
        if not chunks:
            raise ValueError("chunking produced no content")
        return tuple(chunks)

    def _split_block(self, block: CanonicalBlock) -> list[_Fragment]:
        tokens = self.tokenizer.spans(block.text)
        if len(tokens) <= PIPELINE.chunk_max_tokens:
            return [_fragment_from_tokens(block, tokens)]
        sentences: list[_Fragment] = []
        for match in _SENTENCE_PATTERN.finditer(block.text):
            sentence_tokens = self.tokenizer.spans(match.group())
            if not sentence_tokens:
                continue
            absolute = tuple(
                TokenSpan(token.text, match.start() + token.start, match.start() + token.end)
                for token in sentence_tokens
            )
            for start in range(0, len(absolute), PIPELINE.chunk_target_tokens):
                sentences.append(
                    _fragment_from_tokens(
                        block,
                        absolute[start : start + PIPELINE.chunk_target_tokens],
                    )
                )
        return sentences

    def _fit_piece(self, document: CanonicalDocument, piece: _Fragment) -> list[_Fragment]:
        if self.budget.fits(_budget_text(document, [piece])):
            return [piece]
        tokens = self.tokenizer.spans(piece.text)
        fitted: list[_Fragment] = []
        start = 0
        while start < len(tokens):
            low, high, best = start + 1, len(tokens), start
            while low <= high:
                middle = (low + high) // 2
                relative = _fragment_from_tokens(piece.block, tokens[start:middle])
                candidate = _Fragment(
                    relative.block,
                    piece.char_start + relative.char_start,
                    piece.char_start + relative.char_end,
                    relative.token_count,
                )
                if self.budget.fits(_budget_text(document, [candidate])):
                    best = middle
                    low = middle + 1
                else:
                    high = middle - 1
            if best == start:
                raise ValueError("one source token cannot fit the E1 budget")
            relative = _fragment_from_tokens(piece.block, tokens[start:best])
            fitted.append(
                _Fragment(
                    relative.block,
                    piece.char_start + relative.char_start,
                    piece.char_start + relative.char_end,
                    relative.token_count,
                )
            )
            start = best
        return fitted

    def _pack_section(
        self,
        document: CanonicalDocument,
        pieces: list[_Fragment],
    ) -> list[list[_Fragment]]:
        packed: list[list[_Fragment]] = []
        current: list[_Fragment] = []
        current_tokens = 0
        fitted = [part for piece in pieces for part in self._fit_piece(document, piece)]
        for piece in fitted:
            proposed = [*current, piece]
            exceeds_target = current_tokens + piece.token_count > PIPELINE.chunk_target_tokens
            exceeds_budget = not self.budget.fits(_budget_text(document, proposed))
            if current and (exceeds_target or exceeds_budget):
                packed.append(current)
                overlap = min(
                    PIPELINE.chunk_overlap_tokens,
                    max(0, PIPELINE.chunk_target_tokens - piece.token_count),
                )
                current = _tail_overlap(current, overlap)
                current_tokens = sum(fragment.token_count for fragment in current)
                while current and not self.budget.fits(_budget_text(document, [*current, piece])):
                    current = current[1:]
                    current_tokens = sum(fragment.token_count for fragment in current)
            current.append(piece)
            current_tokens += piece.token_count
            if current_tokens > PIPELINE.chunk_max_tokens:
                raise ValueError("C1 chunk exceeded its hard maximum")
        if current:
            packed.append(current)
        return packed
