from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from apps.api.dependencies import (
    AnyWorkspaceAccess,
    AppSettings,
    DatabaseSession,
    RAGServiceDependency,
)
from packages.domain.errors import InvalidQueryError, RetrievalUnavailableError
from packages.domain.schemas import (
    EvidenceLocatorResponse,
    EvidenceResultResponse,
    EvidenceSearchRequest,
    EvidenceSearchResponse,
)
from packages.rag.config import PIPELINE

router = APIRouter(prefix="/workspaces/{workspace_id}/evidence", tags=["retrieval"])


@router.post("/search", response_model=EvidenceSearchResponse)
async def search_evidence(
    workspace_id: UUID,
    payload: EvidenceSearchRequest,
    access: AnyWorkspaceAccess,
    session: DatabaseSession,
    settings: AppSettings,
    service: RAGServiceDependency,
) -> EvidenceSearchResponse:
    del access
    if len(payload.query) > settings.rag_max_query_characters:
        raise InvalidQueryError("retrieval query is too long")
    try:
        results = await service.search(
            session,
            workspace_id=workspace_id,
            query=payload.query,
            result_count=payload.result_count,
        )
    except ValueError as exc:
        raise InvalidQueryError(str(exc)) from exc
    except RuntimeError as exc:
        raise RetrievalUnavailableError("retrieval is temporarily unavailable") from exc
    return EvidenceSearchResponse(
        pipeline_version=PIPELINE.version,
        results=[
            EvidenceResultResponse(
                rank=rank,
                document_id=result.chunk.document_id,
                version_id=result.chunk.version_id,
                text=result.chunk.text,
                heading_path=list(result.chunk.heading_path),
                page_number=result.chunk.page_number,
                locators=[
                    EvidenceLocatorResponse(**locator.as_dict())
                    for locator in result.chunk.locators
                ],
                fused_score=result.fused_score,
                dense_rank=result.dense_rank,
                lexical_rank=result.lexical_rank,
            )
            for rank, result in enumerate(results, start=1)
        ],
    )
