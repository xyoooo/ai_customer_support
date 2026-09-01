from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import groupby
from typing import Protocol

from packages.rag_lab.models import CanonicalBlock, CanonicalDocument, Chunk, SourceLocator
from packages.rag_lab.profiles import CANDIDATES, ChunkerSpec
from packages.rag_lab.tokenizer import RegexTokenizer, TokenSpan

_SENTENCE_PATTERN = re.compile(r"[^.!?]+(?:[.!?]+(?=\s|$)|$)", flags=re.DOTALL)


class Chunker(Protocol):
    spec: ChunkerSpec

    def chunk(self, document: CanonicalDocument) -> tuple[Chunk, ...]: ...


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
            block_id=self.block.block_id,
            block_index=self.block.order,
            char_start=self.char_start,
            char_end=self.char_end,
            page_number=self.block.page_number,
        )


def _fragment_from_tokens(
    block: CanonicalBlock,
    tokens: tuple[TokenSpan, ...],
) -> _Fragment:
    if not tokens:
        raise ValueError("cannot create a fragment without tokens")
    return _Fragment(
        block=block,
        char_start=tokens[0].start,
        char_end=tokens[-1].end,
        token_count=len(tokens),
    )


def _merge_fragments(fragments: list[_Fragment]) -> list[_Fragment]:
    merged: list[_Fragment] = []
    for fragment in fragments:
        if merged and merged[-1].block.block_id == fragment.block.block_id:
            previous = merged[-1]
            merged[-1] = _Fragment(
                block=previous.block,
                char_start=min(previous.char_start, fragment.char_start),
                char_end=max(previous.char_end, fragment.char_end),
                token_count=0,
            )
        else:
            merged.append(fragment)
    tokenizer = RegexTokenizer()
    return [
        _Fragment(
            block=fragment.block,
            char_start=fragment.char_start,
            char_end=fragment.char_end,
            token_count=tokenizer.count(fragment.text),
        )
        for fragment in merged
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


def _chunk_from_fragments(
    document: CanonicalDocument,
    fragments: list[_Fragment],
    *,
    order: int,
    contextual: bool,
) -> Chunk:
    merged = _merge_fragments(fragments)
    text = "\n\n".join(fragment.text for fragment in merged)
    heading_path = _common_heading_path(merged)
    page_numbers = {fragment.block.page_number for fragment in merged}
    page_number = next(iter(page_numbers)) if len(page_numbers) == 1 else None
    if contextual:
        title = document.title or "[untitled]"
        section = " > ".join(heading_path) or "[root]"
        embedding_text = f"Document: {title}\nSection: {section}\n\n{text}"
    else:
        embedding_text = text
    tokenizer = RegexTokenizer()
    return Chunk.create(
        document_id=document.document_id,
        version_id=document.version_id,
        order=order,
        text=text,
        embedding_text=embedding_text,
        token_count=tokenizer.count(text),
        locators=tuple(fragment.locator for fragment in merged),
        heading_path=heading_path,
        page_number=page_number,
    )


def _tail_overlap(fragments: list[_Fragment], limit: int) -> list[_Fragment]:
    if limit <= 0:
        return []
    tokenizer = RegexTokenizer()
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
                block=fragment.block,
                char_start=fragment.char_start + suffix[0].start,
                char_end=fragment.char_start + suffix[-1].end,
                token_count=len(suffix),
            )
        )
        remaining = 0
    selected.reverse()
    return selected


class FixedTokenChunker:
    def __init__(self, spec: ChunkerSpec) -> None:
        if spec.candidate_id != "C0":
            raise ValueError("FixedTokenChunker requires the C0 profile")
        self.spec = spec
        self.tokenizer = RegexTokenizer()

    def chunk(self, document: CanonicalDocument) -> tuple[Chunk, ...]:
        grouping = (
            (lambda block: block.page_number)
            if document.media_type == "application/pdf"
            else (lambda block: 0)
        )
        chunks: list[Chunk] = []
        stride = self.spec.target_tokens - self.spec.overlap_tokens
        for _, block_group in groupby(document.blocks, key=grouping):
            token_references: list[tuple[CanonicalBlock, TokenSpan]] = []
            for block in block_group:
                token_references.extend(
                    (block, token) for token in self.tokenizer.spans(block.text)
                )
            for start in range(0, len(token_references), stride):
                window = token_references[start : start + self.spec.target_tokens]
                if not window:
                    continue
                fragments: list[_Fragment] = []
                for block, references in groupby(window, key=lambda item: item[0]):
                    tokens = tuple(reference[1] for reference in references)
                    fragments.append(_fragment_from_tokens(block, tokens))
                chunks.append(
                    _chunk_from_fragments(
                        document,
                        fragments,
                        order=len(chunks),
                        contextual=False,
                    )
                )
                if start + self.spec.target_tokens >= len(token_references):
                    break
        if not chunks:
            raise ValueError("chunking produced no content")
        return tuple(chunks)


class StructureAwareChunker:
    def __init__(self, spec: ChunkerSpec) -> None:
        if spec.candidate_id not in {"C1", "C2"}:
            raise ValueError("StructureAwareChunker requires the C1 or C2 profile")
        self.spec = spec
        self.tokenizer = RegexTokenizer()

    def chunk(self, document: CanonicalDocument) -> tuple[Chunk, ...]:
        chunks: list[Chunk] = []

        def section_key(block: CanonicalBlock) -> tuple[int | None, tuple[str, ...]]:
            return block.page_number, block.heading_path

        for _, block_group in groupby(document.blocks, key=section_key):
            pieces: list[_Fragment] = []
            for block in block_group:
                pieces.extend(self._split_block(block))
            for fragments in self._pack_section(pieces):
                chunks.append(
                    _chunk_from_fragments(
                        document,
                        fragments,
                        order=len(chunks),
                        contextual=self.spec.context_policy != "original",
                    )
                )
        if not chunks:
            raise ValueError("chunking produced no content")
        return tuple(chunks)

    def _split_block(self, block: CanonicalBlock) -> list[_Fragment]:
        all_tokens = self.tokenizer.spans(block.text)
        if len(all_tokens) <= self.spec.max_tokens:
            return [_fragment_from_tokens(block, all_tokens)]
        sentences: list[_Fragment] = []
        for match in _SENTENCE_PATTERN.finditer(block.text):
            sentence_tokens = self.tokenizer.spans(match.group())
            if not sentence_tokens:
                continue
            absolute_tokens = tuple(
                TokenSpan(
                    text=token.text,
                    start=match.start() + token.start,
                    end=match.start() + token.end,
                )
                for token in sentence_tokens
            )
            if len(absolute_tokens) <= self.spec.max_tokens:
                sentences.append(_fragment_from_tokens(block, absolute_tokens))
                continue
            for start in range(0, len(absolute_tokens), self.spec.target_tokens):
                sentences.append(
                    _fragment_from_tokens(
                        block,
                        absolute_tokens[start : start + self.spec.target_tokens],
                    )
                )
        return sentences

    def _pack_section(self, pieces: list[_Fragment]) -> list[list[_Fragment]]:
        packed: list[list[_Fragment]] = []
        current: list[_Fragment] = []
        current_tokens = 0
        for piece in pieces:
            if current and current_tokens + piece.token_count > self.spec.target_tokens:
                packed.append(current)
                overlap_limit = min(
                    self.spec.overlap_tokens,
                    max(0, self.spec.target_tokens - piece.token_count),
                )
                current = _tail_overlap(current, overlap_limit)
                current_tokens = sum(fragment.token_count for fragment in current)
            current.append(piece)
            current_tokens += piece.token_count
            if current_tokens > self.spec.max_tokens:
                raise ValueError("structure-aware chunk exceeded its hard maximum")
        if current:
            packed.append(current)
        return packed


def build_chunker(candidate: str | ChunkerSpec) -> Chunker:
    spec = CANDIDATES.chunker(candidate) if isinstance(candidate, str) else candidate
    if spec.candidate_id == "C0":
        return FixedTokenChunker(spec)
    return StructureAwareChunker(spec)
