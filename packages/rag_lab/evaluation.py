from __future__ import annotations

import json
import math
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.rag_lab.chunking import Chunker
from packages.rag_lab.dataset import EvaluationCase, EvaluationDataset, EvidenceSpan
from packages.rag_lab.embeddings import EmbeddingAdapter
from packages.rag_lab.models import CanonicalDocument, Chunk, IndexedChunk, RetrievalTrace
from packages.rag_lab.parsing import CanonicalParser
from packages.rag_lab.profiles import ExperimentProfile
from packages.rag_lab.retrieval import InMemoryHybridIndex
from packages.rag_lab.tokenizer import RegexTokenizer


@dataclass(frozen=True, slots=True)
class QueryEvaluation:
    case_id: str
    returned_chunk_ids: tuple[str, ...]
    relevant_ranks: tuple[int, ...]
    dense_hit_at_5: bool
    lexical_hit_at_5: bool
    citation_span_coverage: float
    cross_workspace_results: int
    latency_ms: float


@dataclass(frozen=True, slots=True)
class QualityMetrics:
    evaluated_answerable_cases: int
    recall_at_1: float
    recall_at_5: float
    mean_reciprocal_rank: float
    ndcg_at_5: float
    dense_recall_at_5: float
    lexical_recall_at_5: float
    citation_span_coverage: float
    citation_locator_resolution: float
    cross_workspace_results: int
    unanswerable_cases_with_results: int


@dataclass(frozen=True, slots=True)
class ResourceMetrics:
    indexing_duration_ms: float
    document_count: int
    chunk_count: int
    embedded_token_count: int
    vector_bytes: int
    retrieval_p50_ms: float
    retrieval_p95_ms: float
    truncated_embedding_inputs: int


@dataclass(frozen=True, slots=True)
class ExperimentReport:
    report_schema: str
    generated_at: str
    profile: dict[str, Any]
    profile_fingerprint: str
    quality: QualityMetrics
    resources: ResourceMetrics
    queries: tuple[QueryEvaluation, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "report_schema": self.report_schema,
            "generated_at": self.generated_at,
            "profile": self.profile,
            "profile_fingerprint": self.profile_fingerprint,
            "quality": asdict(self.quality),
            "resources": asdict(self.resources),
            "queries": [asdict(query) for query in self.queries],
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.as_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _overlap(locator_start: int, locator_end: int, evidence: EvidenceSpan) -> int:
    return max(0, min(locator_end, evidence.char_end) - max(locator_start, evidence.char_start))


def chunk_is_relevant(chunk: Chunk, evidence: tuple[EvidenceSpan, ...]) -> bool:
    return any(
        str(label.version_id) == chunk.version_id
        and locator.block_id == label.block_id
        and _overlap(locator.char_start, locator.char_end, label) > 0
        for label in evidence
        for locator in chunk.locators
    )


def _citation_coverage(results: tuple[Chunk, ...], evidence: tuple[EvidenceSpan, ...]) -> float:
    if not evidence:
        return 1.0
    covered = 0
    total = 0
    for label in evidence:
        total += label.char_end - label.char_start
        intervals = []
        for chunk in results:
            if chunk.version_id != str(label.version_id):
                continue
            for locator in chunk.locators:
                if locator.block_id != label.block_id:
                    continue
                start = max(locator.char_start, label.char_start)
                end = min(locator.char_end, label.char_end)
                if end > start:
                    intervals.append((start, end))
        intervals.sort()
        merged: list[tuple[int, int]] = []
        for start, end in intervals:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        covered += sum(end - start for start, end in merged)
    return covered / total if total else 1.0


def _ndcg(relevant: list[bool], evidence_count: int, limit: int = 5) -> float:
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, is_relevant in enumerate(relevant[:limit], start=1)
        if is_relevant
    )
    ideal_count = min(limit, max(1, evidence_count))
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return min(1.0, dcg / ideal)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


class ExperimentRunner:
    def __init__(self, parser: CanonicalParser | None = None) -> None:
        self.parser = parser or CanonicalParser()
        self.tokenizer = RegexTokenizer()

    def run(
        self,
        *,
        dataset: EvaluationDataset,
        corpus_root: Path,
        profile: ExperimentProfile,
        chunker: Chunker,
        embedder: EmbeddingAdapter,
    ) -> ExperimentReport:
        if dataset.dataset_version != profile.dataset_version:
            raise ValueError("profile and dataset versions do not match")
        if chunker.spec != profile.chunker or embedder.spec != profile.embedding:
            raise ValueError("runtime strategies do not match the immutable profile")
        index = InMemoryHybridIndex(profile.retrieval)
        documents: dict[str, CanonicalDocument] = {}
        chunk_count = 0
        embedded_token_count = 0
        indexing_started = time.perf_counter()
        for document_spec in dataset.documents:
            source = dataset.resolve_source(document_spec, corpus_root)
            document = self.parser.parse(
                source.read_bytes(),
                document_id=str(document_spec.document_id),
                version_id=str(document_spec.version_id),
                title=document_spec.title,
                media_type=document_spec.media_type,
            )
            documents[document.version_id] = document
            chunks = chunker.chunk(document)
            for chunk in chunks:
                for locator in chunk.locators:
                    document.resolve(locator)
            vectors = embedder.embed_documents([chunk.embedding_text for chunk in chunks])
            records = tuple(
                IndexedChunk(
                    workspace_id=str(document_spec.workspace_id),
                    chunk=chunk,
                    embedding=vector,
                    active=document_spec.active,
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            )
            index.replace_version(
                workspace_id=str(document_spec.workspace_id),
                profile_fingerprint=profile.fingerprint,
                version_id=document.version_id,
                records=records,
            )
            chunk_count += len(chunks)
            embedded_token_count += sum(
                self.tokenizer.count(chunk.embedding_text) for chunk in chunks
            )
        indexing_duration_ms = (time.perf_counter() - indexing_started) * 1000
        self._validate_evidence(dataset, documents)

        query_evaluations: list[QueryEvaluation] = []
        citation_resolved = 0
        citation_total = 0
        for case in dataset.cases:
            started = time.perf_counter()
            query_vector = embedder.embed_queries([case.query])[0]
            trace = index.search_with_trace(
                workspace_id=str(case.workspace_id),
                profile_fingerprint=profile.fingerprint,
                query=case.query,
                query_embedding=query_vector,
            )
            latency_ms = (time.perf_counter() - started) * 1000
            query_evaluations.append(self._evaluate_case(case, trace, latency_ms=latency_ms))
            for result in trace.results:
                citation_total += len(result.chunk.locators)
                source_document = documents.get(result.chunk.version_id)
                if source_document is None:
                    continue
                for locator in result.chunk.locators:
                    try:
                        source_document.resolve(locator)
                    except ValueError:
                        continue
                    citation_resolved += 1

        quality = self._aggregate_quality(
            dataset,
            tuple(query_evaluations),
            citation_resolved=citation_resolved,
            citation_total=citation_total,
        )
        latencies = [evaluation.latency_ms for evaluation in query_evaluations]
        resources = ResourceMetrics(
            indexing_duration_ms=indexing_duration_ms,
            document_count=len(dataset.documents),
            chunk_count=chunk_count,
            embedded_token_count=embedded_token_count,
            vector_bytes=chunk_count * profile.embedding.dimension * 4,
            retrieval_p50_ms=statistics.median(latencies) if latencies else 0.0,
            retrieval_p95_ms=_percentile(latencies, 0.95),
            truncated_embedding_inputs=embedder.truncated_input_count,
        )
        return ExperimentReport(
            report_schema="rag-lab-report-v1",
            generated_at=datetime.now(UTC).isoformat(),
            profile=profile.as_dict(),
            profile_fingerprint=profile.fingerprint,
            quality=quality,
            resources=resources,
            queries=tuple(query_evaluations),
        )

    def _validate_evidence(
        self,
        dataset: EvaluationDataset,
        documents: dict[str, CanonicalDocument],
    ) -> None:
        for case in dataset.cases:
            for evidence in case.evidence:
                document = documents[str(evidence.version_id)]
                block = next(
                    (block for block in document.blocks if block.block_id == evidence.block_id),
                    None,
                )
                if block is None:
                    raise ValueError(f"case {case.case_id} references a missing source block")
                if evidence.char_end > len(block.text):
                    raise ValueError(f"case {case.case_id} evidence extends beyond its block")

    def _evaluate_case(
        self,
        case: EvaluationCase,
        trace: RetrievalTrace,
        *,
        latency_ms: float,
    ) -> QueryEvaluation:
        relevant_ranks = tuple(
            rank
            for rank, result in enumerate(trace.results, start=1)
            if chunk_is_relevant(result.chunk, case.evidence)
        )
        dense_hit = any(chunk_is_relevant(chunk, case.evidence) for chunk in trace.dense[:5])
        lexical_hit = any(chunk_is_relevant(chunk, case.evidence) for chunk in trace.lexical[:5])
        returned_chunks = tuple(result.chunk for result in trace.results)
        return QueryEvaluation(
            case_id=case.case_id,
            returned_chunk_ids=tuple(chunk.chunk_id for chunk in returned_chunks),
            relevant_ranks=relevant_ranks,
            dense_hit_at_5=dense_hit,
            lexical_hit_at_5=lexical_hit,
            citation_span_coverage=_citation_coverage(returned_chunks, case.evidence),
            cross_workspace_results=sum(
                result.workspace_id != str(case.workspace_id) for result in trace.results
            ),
            latency_ms=latency_ms,
        )

    def _aggregate_quality(
        self,
        dataset: EvaluationDataset,
        evaluations: tuple[QueryEvaluation, ...],
        *,
        citation_resolved: int,
        citation_total: int,
    ) -> QualityMetrics:
        by_case = {evaluation.case_id: evaluation for evaluation in evaluations}
        answerable = [case for case in dataset.cases if not case.unanswerable]
        denominator = max(1, len(answerable))
        answerable_evaluations = [by_case[case.case_id] for case in answerable]
        recall_at_1 = sum(1 in result.relevant_ranks for result in answerable_evaluations)
        recall_at_5 = sum(bool(result.relevant_ranks) for result in answerable_evaluations)
        reciprocal_rank = sum(
            1.0 / min(result.relevant_ranks) if result.relevant_ranks else 0.0
            for result in answerable_evaluations
        )
        ndcg_total = 0.0
        for case in answerable:
            evaluation = by_case[case.case_id]
            relevant = [
                rank in evaluation.relevant_ranks
                for rank in range(1, len(evaluation.returned_chunk_ids) + 1)
            ]
            ndcg_total += _ndcg(relevant, len(case.evidence))
        return QualityMetrics(
            evaluated_answerable_cases=len(answerable),
            recall_at_1=recall_at_1 / denominator,
            recall_at_5=recall_at_5 / denominator,
            mean_reciprocal_rank=reciprocal_rank / denominator,
            ndcg_at_5=ndcg_total / denominator,
            dense_recall_at_5=sum(result.dense_hit_at_5 for result in answerable_evaluations)
            / denominator,
            lexical_recall_at_5=sum(result.lexical_hit_at_5 for result in answerable_evaluations)
            / denominator,
            citation_span_coverage=sum(
                result.citation_span_coverage for result in answerable_evaluations
            )
            / denominator,
            citation_locator_resolution=(
                citation_resolved / citation_total if citation_total else 1.0
            ),
            cross_workspace_results=sum(result.cross_workspace_results for result in evaluations),
            unanswerable_cases_with_results=sum(
                bool(by_case[case.case_id].returned_chunk_ids)
                for case in dataset.cases
                if case.unanswerable
            ),
        )
