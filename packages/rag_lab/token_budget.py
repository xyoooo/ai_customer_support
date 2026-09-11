from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from tokenizers import Tokenizer

from packages.rag_lab.profiles import EmbeddingSpec
from packages.rag_lab.tokenizer import RegexTokenizer


class EmbeddingInputBudget(Protocol):
    """Validates one shared chunk against every candidate embedding tokenizer."""

    def fits(self, text: str) -> bool: ...

    def assert_fits(self, text: str) -> None: ...

    def largest_prefix_end(self, text: str) -> int: ...


@dataclass(frozen=True, slots=True)
class RegexInputBudget:
    """Dependency-free fallback used by unit tests and non-model smoke runs."""

    max_tokens: int

    def fits(self, text: str) -> bool:
        return RegexTokenizer().count(text) <= self.max_tokens

    def assert_fits(self, text: str) -> None:
        if not self.fits(text):
            raise ValueError("embedding input exceeds the shared token budget")

    def largest_prefix_end(self, text: str) -> int:
        spans = RegexTokenizer().spans(text)
        if not spans:
            return 0
        return spans[min(len(spans), self.max_tokens) - 1].end


@dataclass(frozen=True, slots=True)
class _CandidateTokenizer:
    candidate_id: str
    document_prefix: str
    input_limit: int
    tokenizer: Tokenizer

    def count(self, text: str) -> int:
        prepared = f"{self.document_prefix}{text.strip()}"
        return len(self.tokenizer.encode(prepared, add_special_tokens=True).ids)


class SharedModelInputBudget:
    """Strictest fit across the actual E0-E2 tokenizers and their pinned limits."""

    def __init__(self, candidates: Sequence[_CandidateTokenizer]) -> None:
        if not candidates:
            raise ValueError("a shared model budget requires at least one tokenizer")
        self._candidates = tuple(candidates)
        self._regex = RegexTokenizer()

    @classmethod
    def from_model_root(
        cls,
        model_root: Path,
        specs: Sequence[EmbeddingSpec],
    ) -> SharedModelInputBudget:
        candidates: list[_CandidateTokenizer] = []
        for spec in specs:
            tokenizer_path = model_root / spec.candidate_id / "tokenizer.json"
            if not tokenizer_path.is_file():
                raise RuntimeError(
                    f"offline tokenizer is missing for shared budget: {tokenizer_path}"
                )
            tokenizer = Tokenizer.from_file(str(tokenizer_path))
            tokenizer.no_truncation()
            candidates.append(
                _CandidateTokenizer(
                    candidate_id=spec.candidate_id,
                    document_prefix=spec.document_prefix,
                    input_limit=spec.input_limit,
                    tokenizer=tokenizer,
                )
            )
        return cls(candidates)

    def counts(self, text: str) -> dict[str, int]:
        return {candidate.candidate_id: candidate.count(text) for candidate in self._candidates}

    def fits(self, text: str) -> bool:
        return all(candidate.count(text) <= candidate.input_limit for candidate in self._candidates)

    def assert_fits(self, text: str) -> None:
        overflow = {
            candidate.candidate_id: (candidate.count(text), candidate.input_limit)
            for candidate in self._candidates
            if candidate.count(text) > candidate.input_limit
        }
        if overflow:
            detail = ", ".join(
                f"{candidate}={count}/{limit}"
                for candidate, (count, limit) in sorted(overflow.items())
            )
            raise ValueError(f"embedding input exceeds the shared token budget: {detail}")

    def largest_prefix_end(self, text: str) -> int:
        spans = self._regex.spans(text)
        if not spans:
            return 0
        low = 1
        high = len(spans)
        best = 0
        while low <= high:
            middle = (low + high) // 2
            end = spans[middle - 1].end
            if self.fits(text[:end]):
                best = end
                low = middle + 1
            else:
                high = middle - 1
        return best
