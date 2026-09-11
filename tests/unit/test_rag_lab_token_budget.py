from __future__ import annotations

from pathlib import Path

import pytest
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace

from packages.rag_lab.profiles import EmbeddingSpec
from packages.rag_lab.token_budget import SharedModelInputBudget


def _spec(candidate_id: str, *, prefix: str, limit: int) -> EmbeddingSpec:
    return EmbeddingSpec(
        candidate_id=candidate_id,
        provider="test",
        model_id=f"test/{candidate_id}",
        artifact_id=f"test/{candidate_id}",
        artifact_revision="a" * 40,
        dimension=8,
        input_limit=limit,
        pooling="mean",
        normalized=True,
        query_prefix="",
        document_prefix=prefix,
        license="MIT",
    )


def _write_tokenizer(path: Path) -> None:
    tokenizer = Tokenizer(
        WordLevel(
            {
                "[UNK]": 0,
                "prefix": 1,
                "one": 2,
                "two": 3,
                "three": 4,
                "four": 5,
            },
            unk_token="[UNK]",
        )
    )
    tokenizer.pre_tokenizer = Whitespace()
    path.parent.mkdir(parents=True)
    tokenizer.save(str(path))


def test_shared_model_budget_loads_and_enforces_every_candidate(tmp_path: Path) -> None:
    specs = (
        _spec("E0", prefix="", limit=3),
        _spec("E1", prefix="prefix ", limit=4),
    )
    for spec in specs:
        _write_tokenizer(tmp_path / spec.candidate_id / "tokenizer.json")

    budget = SharedModelInputBudget.from_model_root(tmp_path, specs)

    assert budget.counts("one two three") == {"E0": 3, "E1": 4}
    assert budget.fits("one two three")
    budget.assert_fits("one two three")
    assert not budget.fits("one two three four")
    with pytest.raises(ValueError, match=r"E0=4/3, E1=5/4"):
        budget.assert_fits("one two three four")
    assert budget.largest_prefix_end("one two three four") == len("one two three")
    assert budget.largest_prefix_end("   ") == 0


def test_shared_model_budget_rejects_missing_or_empty_configuration(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one tokenizer"):
        SharedModelInputBudget(())
    with pytest.raises(RuntimeError, match="offline tokenizer is missing"):
        SharedModelInputBudget.from_model_root(
            tmp_path,
            (_spec("E0", prefix="", limit=3),),
        )
