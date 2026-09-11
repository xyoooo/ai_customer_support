from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise

from packages.rag.config import PIPELINE
from packages.rag.models import Chunk

_TERM_PATTERN = re.compile(r"[\w]+(?:[-_.'][\w]+)*", flags=re.UNICODE)
_STOP_WORDS = frozenset(
    {
        "a",
        "about",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "before",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "should",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "use",
        "using",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
    }
)


def _variants(term: str) -> tuple[str, ...]:
    if any(character.isdigit() for character in term) or any(
        separator in term for separator in "-_."
    ):
        return (term,)
    variants = [term]
    if len(term) > 5 and term.endswith("ies"):
        variants.append(term[:-3] + "y")
    elif len(term) > 6 and term.endswith("ing"):
        variants.extend((term[:-3], term[:-3] + "e"))
    elif len(term) > 5 and term.endswith("ed"):
        variants.extend((term[:-2], term[:-2] + "e"))
    elif len(term) > 4 and term.endswith("s") and not term.endswith(("ss", "us", "is")):
        variants.append(term[:-1])
    return tuple(dict.fromkeys(variants))


def lexical_terms(text: str) -> tuple[str, ...]:
    terms: list[str] = []
    for match in _TERM_PATTERN.finditer(text.replace("\u2019", "'")):
        term = match.group().casefold()
        if term not in _STOP_WORDS:
            terms.extend(_variants(term))
    return tuple(terms)


def _identifiers(text: str) -> frozenset[str]:
    return frozenset(
        value
        for match in _TERM_PATTERN.finditer(text)
        if (value := match.group().casefold())
        and (
            any(character.isdigit() for character in value)
            or any(separator in value for separator in "-_.")
        )
    )


@dataclass(frozen=True, slots=True)
class _PreparedDocument:
    chunk: Chunk
    weighted_terms: dict[str, float]
    present_terms: frozenset[str]
    sequences: tuple[tuple[str, ...], ...]
    identifiers: frozenset[str]
    length: float


class BM25LexicalScorer:
    """Selected deterministic structural BM25 scorer."""

    @lru_cache(maxsize=100_000)  # noqa: B019
    def _prepare(self, chunk: Chunk) -> _PreparedDocument:
        text_terms = lexical_terms(chunk.text)
        headings = tuple(lexical_terms(heading) for heading in chunk.heading_path)
        title_terms = lexical_terms(chunk.document_title)
        weighted = {term: float(count) for term, count in Counter(text_terms).items()}
        for sequence in headings:
            for term in sequence:
                weighted[term] = weighted.get(term, 0.0) + PIPELINE.heading_weight
        for term in title_terms:
            weighted[term] = weighted.get(term, 0.0) + PIPELINE.title_weight
        sequences = (text_terms, *headings, title_terms)
        source = " ".join((chunk.text, *chunk.heading_path, chunk.document_title))
        return _PreparedDocument(
            chunk,
            weighted,
            frozenset(term for sequence in sequences for term in sequence),
            sequences,
            _identifiers(source),
            len(text_terms)
            + PIPELINE.heading_weight * sum(len(value) for value in headings)
            + PIPELINE.title_weight * len(title_terms),
        )

    def rank(self, query: str, chunks: Sequence[Chunk], *, limit: int) -> tuple[Chunk, ...]:
        query_terms = lexical_terms(query)
        if not query_terms or not chunks or limit < 1:
            return ()
        prepared = tuple(self._prepare(chunk) for chunk in chunks)
        count = len(prepared)
        average_length = sum(document.length for document in prepared) / count
        frequencies = {
            term: sum(term in document.present_terms for document in prepared)
            for term in set(query_terms)
        }
        inverse = {
            term: math.log(1 + (count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in frequencies.items()
        }
        query_counts = Counter(query_terms)
        query_identifiers = _identifiers(query)
        query_bigrams = set(pairwise(query_terms))
        scored: list[tuple[float, Chunk]] = []
        for document in prepared:
            normalization = PIPELINE.bm25_k1 * (
                1
                - PIPELINE.bm25_b
                + PIPELINE.bm25_b * (document.length / average_length if average_length else 1)
            )
            score = 0.0
            for term, query_frequency in query_counts.items():
                term_frequency = document.weighted_terms.get(term, 0.0)
                if term_frequency > 0:
                    score += (
                        inverse[term]
                        * query_frequency
                        * term_frequency
                        * (PIPELINE.bm25_k1 + 1)
                        / (term_frequency + normalization)
                    )
            score += PIPELINE.exact_identifier_bonus * sum(
                inverse.get(identifier, 1.0)
                for identifier in query_identifiers & document.identifiers
            )
            document_bigrams = {
                pair for sequence in document.sequences for pair in pairwise(sequence)
            }
            score += PIPELINE.phrase_bonus * sum(
                (inverse.get(left, 0.0) + inverse.get(right, 0.0)) / 2
                for left, right in query_bigrams & document_bigrams
            )
            if score > 0:
                scored.append((score, document.chunk))
        scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
        return tuple(chunk for _, chunk in scored[:limit])
