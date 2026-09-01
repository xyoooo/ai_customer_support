from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN_PATTERN = re.compile(r"\w+(?:['\u2019]\w+)*|[^\w\s]", flags=re.UNICODE)


@dataclass(frozen=True, slots=True)
class TokenSpan:
    text: str
    start: int
    end: int


class RegexTokenizer:
    """Versioned deterministic chunking tokenizer, independent of model tokenizers."""

    identifier = "unicode-wordpunct-v1"

    def spans(self, text: str) -> tuple[TokenSpan, ...]:
        return tuple(
            TokenSpan(text=match.group(), start=match.start(), end=match.end())
            for match in _TOKEN_PATTERN.finditer(text)
        )

    def count(self, text: str) -> int:
        return len(self.spans(text))
