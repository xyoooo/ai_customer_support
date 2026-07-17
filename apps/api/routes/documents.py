from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, Header, UploadFile, status
from sqlalchemy import select

from apps.api.dependencies import (
    AnyWorkspaceAccess,
    AppSettings,
    DatabaseSession,
    MalwareScannerDependency,
    ObjectStoreDependency,
    WorkspaceContributorAccess,
    WorkspaceManagerAccess,
)
from packages.database.models import Document, DocumentVersion, Job
from packages.documents.service import UploadResult, upload_document_version
from packages.domain.enums import JobState, JobType
from packages.domain.errors import NotFoundError
from packages.domain.schemas import (
    DocumentDetailResponse,
    DocumentResponse,
    DocumentUpdate,
    DocumentUploadResponse,
    DocumentVersionResponse,
    JobResponse,
)
from packages.jobs.service import retry_job

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["documents"])


def version_response(version: DocumentVersion) -> DocumentVersionResponse:
    return DocumentVersionResponse.model_validate(version)


def job_response(job: Job) -> JobResponse:
    return JobResponse.model_validate(job)


async def document_response(
    session: DatabaseSession,
    document: Document,
) -> DocumentResponse:
    latest = await session.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    )
    return DocumentResponse(
        id=document.id,
        workspace_id=document.workspace_id,
        display_name=document.display_name,
        active_version_id=document.active_version_id,
        created_by=document.created_by,
        deleted_at=document.deleted_at,
        created_at=document.created_at,
        updated_at=document.updated_at,
        latest_version=version_response(latest) if latest else None,
    )


async def upload_response(
    session: DatabaseSession,
    result: UploadResult,
) -> DocumentUploadResponse:
    return DocumentUploadResponse(
        document=await document_response(session, result.document),
        version=version_response(result.version),
        job=job_response(result.job),
    )


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(
    workspace_id: UUID,
    access: AnyWorkspaceAccess,
    session: DatabaseSession,
) -> list[DocumentResponse]:
    del access
    documents = list(
        await session.scalars(
            select(Document)
            .where(Document.workspace_id == workspace_id, Document.deleted_at.is_(None))
            .order_by(Document.created_at.desc())
        )
    )
    return [await document_response(session, document) for document in documents]


@router.post(
    "/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_document(
    workspace_id: UUID,
    access: WorkspaceContributorAccess,
    session: DatabaseSession,
    settings: AppSettings,
    store: ObjectStoreDependency,
    scanner: MalwareScannerDependency,
    file: Annotated[UploadFile, File()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    display_name: Annotated[str | None, Form(max_length=255)] = None,
) -> DocumentUploadResponse:
    result = await upload_document_version(
        session,
        workspace_id=workspace_id,
        user_id=access.principal.user.id,
        upload=file,
        idempotency_key=idempotency_key,
        store=store,
        scanner=scanner,
        settings=settings,
        display_name=display_name,
    )
    return await upload_response(session, result)


@router.post(
    "/documents/{document_id}/versions",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_document_version(
    workspace_id: UUID,
    document_id: UUID,
    access: WorkspaceContributorAccess,
    session: DatabaseSession,
    settings: AppSettings,
    store: ObjectStoreDependency,
    scanner: MalwareScannerDependency,
    file: Annotated[UploadFile, File()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> DocumentUploadResponse:
    result = await upload_document_version(
        session,
        workspace_id=workspace_id,
        user_id=access.principal.user.id,
        upload=file,
        idempotency_key=idempotency_key,
        store=store,
        scanner=scanner,
        settings=settings,
        document_id=document_id,
    )
    return await upload_response(session, result)


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    workspace_id: UUID,
    document_id: UUID,
    access: AnyWorkspaceAccess,
    session: DatabaseSession,
) -> DocumentDetailResponse:
    del access
    document = await session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
            Document.deleted_at.is_(None),
        )
    )
    if document is None:
        raise NotFoundError("document not found")
    versions = list(
        await session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_number.desc())
        )
    )
    jobs = list(
        await session.scalars(
            select(Job).where(Job.workspace_id == workspace_id).order_by(Job.created_at.desc())
        )
    )
    document_jobs = [job for job in jobs if job.payload.get("document_id") == str(document.id)]
    base = await document_response(session, document)
    return DocumentDetailResponse(
        **base.model_dump(),
        versions=[version_response(version) for version in versions],
        jobs=[job_response(job) for job in document_jobs],
    )


@router.patch("/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    workspace_id: UUID,
    document_id: UUID,
    payload: DocumentUpdate,
    access: WorkspaceManagerAccess,
    session: DatabaseSession,
) -> DocumentResponse:
    del access
    document = await session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
            Document.deleted_at.is_(None),
        )
    )
    if document is None:
        raise NotFoundError("document not found")
    document.display_name = payload.display_name
    await session.flush()
    await session.refresh(document)
    return await document_response(session, document)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    workspace_id: UUID,
    document_id: UUID,
    access: WorkspaceManagerAccess,
    session: DatabaseSession,
) -> None:
    del access
    document = await session.scalar(
        select(Document)
        .where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
            Document.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if document is None:
        raise NotFoundError("document not found")
    document.deleted_at = datetime.now(UTC)
    document.active_version_id = None
    job = Job(
        id=uuid4(),
        workspace_id=workspace_id,
        job_type=JobType.DELETE_OBJECT,
        payload={"document_id": str(document.id)},
        state=JobState.QUEUED,
        idempotency_key=f"delete:{document.id}",
    )
    session.add(job)
    await session.flush()


@router.post("/jobs/{job_id}/retry", response_model=JobResponse)
async def retry_document_job(
    workspace_id: UUID,
    job_id: UUID,
    access: WorkspaceContributorAccess,
    session: DatabaseSession,
) -> JobResponse:
    del access
    job = await retry_job(session, job_id=job_id, workspace_id=workspace_id)
    return job_response(job)
