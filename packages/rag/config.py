from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    version: str = "rag-v1-c1-e1"
    parser_version: str = "canonical-parser-v2-layout"
    chunk_target_tokens: int = 350
    chunk_max_tokens: int = 500
    chunk_overlap_tokens: int = 60
    embedding_model_id: str = "snowflake/snowflake-arctic-embed-xs"
    embedding_artifact_id: str = "snowflake/snowflake-arctic-embed-xs"
    embedding_artifact_revision: str = "d8c86521100d3556476a063fc2342036d45c106f"
    embedding_dimension: int = 384
    embedding_input_limit: int = 512
    embedding_query_prefix: str = "Represent this sentence for searching relevant passages: "
    lexical_scorer: str = "bm25-structural-v1"
    bm25_k1: float = 1.2
    bm25_b: float = 0.75
    heading_weight: float = 0.75
    title_weight: float = 0.5
    exact_identifier_bonus: float = 1.5
    phrase_bonus: float = 0.25
    dense_candidates: int = 20
    lexical_candidates: int = 20
    rrf_constant: int = 60
    default_result_count: int = 5
    maximum_result_count: int = 10


PIPELINE = PipelineConfig()
