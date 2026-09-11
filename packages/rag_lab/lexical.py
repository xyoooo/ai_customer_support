from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise

from packages.rag_lab.models import Chunk
from packages.rag_lab.profiles import RetrievalSpec

_TERM_PATTERN = re.compile(
    r"[A-Za-z0-9]+(?:[-_.][A-Za-z0-9]+)+|[^\W_]+(?:['\u2019][^\W_]+)*|\d+",
    flags=re.UNICODE,
)
_STOP_WORDS = frozenset(
    {
        "a",
        "about",
        "after",
        "all",
        "also",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "for",
        "from",
        "had",
        "has",
        "have",
        "having",
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
        "so",
        "than",
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
        "under",
        "use",
        "using",
        "want",
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
        root = term[:-3]
        variants.extend((root, root + "e"))
    elif len(term) > 5 and term.endswith("ed"):
        root = term[:-2]
        variants.extend((root, root + "e"))
    elif len(term) > 4 and term.endswith("s") and not term.endswith(("ss", "us", "is")):
        variants.append(term[:-1])
    return tuple(dict.fromkeys(variants))


def lexical_terms(text: str) -> tuple[str, ...]:
    terms: list[str] = []
    for match in _TERM_PATTERN.finditer(text.replace("\u2019", "'")):
        term = match.group().casefold()
        if term in _STOP_WORDS:
            continue
        terms.extend(_variants(term))
    return tuple(terms)


def _identifiers(text: str) -> frozenset[str]:
    identifiers = set()
    for match in _TERM_PATTERN.finditer(text):
        value = match.group().casefold()
        if any(character.isdigit() for character in value) or any(
            separator in value for separator in "-_."
        ):
            identifiers.add(value)
    return frozenset(identifiers)


@dataclass(frozen=True, slots=True)
class _PreparedDocument:
    chunk: Chunk
    weighted_terms: dict[str, float]
    present_terms: frozenset[str]
    sequences: tuple[tuple[str, ...], ...]
    identifiers: frozenset[str]
    length: float


class BM25LexicalScorer:
    """Deterministic lab-scale BM25 over source text and trusted structure."""

    def __init__(self, spec: RetrievalSpec) -> None:
        self.spec = spec

    @lru_cache(maxsize=100_000)  # noqa: B019 - cache belongs to this long-lived scorer instance
    def _prepare(self, chunk: Chunk) -> _PreparedDocument:
        text_terms = lexical_terms(chunk.text)
        heading_sequences = tuple(lexical_terms(heading) for heading in chunk.heading_path)
        title_terms = lexical_terms(chunk.document_title)
        weighted = {term: float(count) for term, count in Counter(text_terms).items()}
        for sequence in heading_sequences:
            for term in sequence:
                weighted[term] = weighted.get(term, 0.0) + self.spec.heading_weight
        for term in title_terms:
            weighted[term] = weighted.get(term, 0.0) + self.spec.title_weight
        sequences = (text_terms, *heading_sequences, title_terms)
        present = frozenset(term for sequence in sequences for term in sequence)
        source_text = " ".join((chunk.text, *chunk.heading_path, chunk.document_title))
        return _PreparedDocument(
            chunk=chunk,
            weighted_terms=weighted,
            present_terms=present,
            sequences=sequences,
            identifiers=_identifiers(source_text),
            length=(
                len(text_terms)
                + self.spec.heading_weight * sum(len(value) for value in heading_sequences)
                + self.spec.title_weight * len(title_terms)
            ),
        )

    def rank(
        self,
        query: str,
        chunks: Sequence[Chunk],
        *,
        limit: int,
    ) -> tuple[Chunk, ...]:
        query_terms = lexical_terms(query)
        if not query_terms or not chunks or limit < 1:
            return ()
        prepared = tuple(self._prepare(chunk) for chunk in chunks)
        document_count = len(prepared)
        average_length = sum(document.length for document in prepared) / document_count
        document_frequency = {
            term: sum(term in document.present_terms for document in prepared)
            for term in set(query_terms)
        }
        inverse_document_frequency = {
            term: math.log(1 + (document_count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }
        query_counts = Counter(query_terms)
        query_identifiers = _identifiers(query)
        query_bigrams = set(pairwise(query_terms))
        scored: list[tuple[float, Chunk]] = []
        for document in prepared:
            score = 0.0
            length_ratio = document.length / average_length if average_length else 1.0
            normalization = self.spec.bm25_k1 * (
                1 - self.spec.bm25_b + self.spec.bm25_b * length_ratio
            )
            for term, query_frequency in query_counts.items():
                term_frequency = document.weighted_terms.get(term, 0.0)
                if term_frequency <= 0:
                    continue
                score += (
                    inverse_document_frequency[term]
                    * query_frequency
                    * term_frequency
                    * (self.spec.bm25_k1 + 1)
                    / (term_frequency + normalization)
                )
            identifier_matches = query_identifiers & document.identifiers
            score += self.spec.exact_identifier_bonus * sum(
                inverse_document_frequency.get(identifier, 1.0) for identifier in identifier_matches
            )
            document_bigrams = {
                pair for sequence in document.sequences for pair in pairwise(sequence)
            }
            phrase_matches = query_bigrams & document_bigrams
            score += self.spec.phrase_bonus * sum(
                (
                    inverse_document_frequency.get(left, 0.0)
                    + inverse_document_frequency.get(right, 0.0)
                )
                / 2
                for left, right in phrase_matches
            )
            if score > 0:
                scored.append((score, document.chunk))
        scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
        return tuple(chunk for _, chunk in scored[:limit])
