from __future__ import annotations

import json
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

REQUIRED_CATEGORY_COUNTS = {
    "direct_lookup": 10,
    "semantic_paraphrase": 8,
    "exact_identifier": 6,
    "multi_span": 6,
    "ambiguous": 4,
    "unanswerable": 4,
    "superseded_version": 4,
    "cross_workspace": 4,
    "structure_sensitive": 4,
}
REQUIRED_MEDIA_TYPES = {
    "application/pdf",
    "text/markdown",
    "text/html",
    "text/plain",
}


class EvaluationDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace_id: UUID
    document_id: UUID
    version_id: UUID
    title: str = Field(max_length=255)
    media_type: str
    source_path: str
    active: bool = True

    @model_validator(mode="after")
    def source_must_be_relative(self) -> Self:
        path = PurePosixPath(self.source_path.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or not path.name:
            raise ValueError("dataset source_path must stay within the corpus directory")
        return self


class EvidenceSpan(BaseModel):
    model_config = ConfigDict(frozen=True)

    version_id: UUID
    block_id: str
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)

    @model_validator(mode="after")
    def end_must_follow_start(self) -> Self:
        if self.char_end <= self.char_start:
            raise ValueError("evidence span must be non-empty")
        return self


class EvaluationCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str = Field(min_length=1, max_length=120)
    workspace_id: UUID
    query: str = Field(min_length=1)
    tags: tuple[str, ...] = ()
    evidence: tuple[EvidenceSpan, ...] = ()
    unanswerable: bool = False

    @model_validator(mode="after")
    def answerability_matches_labels(self) -> Self:
        if self.unanswerable and self.evidence:
            raise ValueError("unanswerable cases cannot include evidence labels")
        if not self.unanswerable and not self.evidence:
            raise ValueError("answerable cases require at least one evidence label")
        return self


class EvaluationDataset(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str
    dataset_version: str
    documents: tuple[EvaluationDocument, ...]
    cases: tuple[EvaluationCase, ...]

    @model_validator(mode="after")
    def references_are_consistent(self) -> Self:
        version_ids = {document.version_id for document in self.documents}
        if len(version_ids) != len(self.documents):
            raise ValueError("dataset document versions must be unique")
        case_ids = {case.case_id for case in self.cases}
        if len(case_ids) != len(self.cases):
            raise ValueError("dataset case identifiers must be unique")
        for case in self.cases:
            for evidence in case.evidence:
                if evidence.version_id not in version_ids:
                    raise ValueError(f"case {case.case_id} references an unknown document version")
        return self

    @classmethod
    def load(cls, path: Path) -> EvaluationDataset:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"evaluation dataset could not be loaded: {path}") from exc
        return cls.model_validate(payload)

    def validate_strict_coverage(self) -> None:
        if len(self.cases) < 50:
            raise ValueError("the reviewed Week 3 dataset must contain at least 50 cases")
        category_counts = Counter(tag for case in self.cases for tag in set(case.tags))
        missing = {
            category: minimum - category_counts[category]
            for category, minimum in REQUIRED_CATEGORY_COUNTS.items()
            if category_counts[category] < minimum
        }
        if missing:
            raise ValueError(f"dataset category coverage is incomplete: {missing}")
        media_types = {document.media_type for document in self.documents}
        if missing_media := REQUIRED_MEDIA_TYPES - media_types:
            raise ValueError(f"dataset corpus is missing media types: {sorted(missing_media)}")

    def resolve_source(self, document: EvaluationDocument, corpus_root: Path) -> Path:
        root = corpus_root.resolve()
        source = (root / document.source_path).resolve()
        if not source.is_relative_to(root):
            raise ValueError("dataset source path escapes the corpus directory")
        if not source.is_file():
            raise ValueError(f"dataset source file is missing: {document.source_path}")
        return source
