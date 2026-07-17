from __future__ import annotations

import asyncio
import socket
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import select

from packages.config import get_settings
from packages.database.models import Document, DocumentVersion, Job
from packages.database.session import get_engine, get_session_factory
from packages.database.tenant import set_tenant_context
from packages.domain.enums import DocumentVersionStatus, JobState, JobType
from packages.jobs.service import (
    claim_jobs,
    mark_completed,
    mark_failed,
    mark_processing,
)
from packages.observability import configure_logging
from packages.storage import LocalObjectStore

SERVICE_USER_ID = UUID(int=0)


async def begin_processing(job: Job, worker_id: str) -> None:
    async with get_session_factory()() as session, session.begin():
        await set_tenant_context(session, user_id=SERVICE_USER_ID, workspace_id=job.workspace_id)
        owned = await mark_processing(session, job_id=job.id, worker_id=worker_id)
        if owned.job_type is JobType.PROCESS_DOCUMENT:
            version = await session.get(DocumentVersion, UUID(owned.payload["document_version_id"]))
            if version is None:
                raise RuntimeError("document version does not exist")
            version.status = DocumentVersionStatus.PROCESSING


async def finish_document_job(
    job: Job,
    worker_id: str,
    store: LocalObjectStore,
) -> None:
    version_id = UUID(job.payload["document_version_id"])
    async with get_session_factory()() as session, session.begin():
        await set_tenant_context(session, user_id=SERVICE_USER_ID, workspace_id=job.workspace_id)
        version = await session.get(DocumentVersion, version_id)
        if version is None:
            raise RuntimeError("document version does not exist")
        object_key = version.object_key
        expected_size = version.byte_size
    metadata = await store.stat(object_key)
    if metadata.byte_size != expected_size:
        raise RuntimeError("stored object size no longer matches document metadata")
    async with get_session_factory()() as session, session.begin():
        await set_tenant_context(session, user_id=SERVICE_USER_ID, workspace_id=job.workspace_id)
        version = await session.get(DocumentVersion, version_id)
        if version is None:
            raise RuntimeError("document version does not exist")
        document = await session.get(Document, version.document_id)
        if document is None or document.deleted_at is not None:
            raise RuntimeError("document is missing or deleted")
        version.status = DocumentVersionStatus.ACTIVE
        await session.flush()
        document.active_version_id = version.id
        await mark_completed(session, job_id=job.id, worker_id=worker_id)


async def finish_delete_job(
    job: Job,
    worker_id: str,
    store: LocalObjectStore,
) -> None:
    document_id = UUID(job.payload["document_id"])
    async with get_session_factory()() as session, session.begin():
        await set_tenant_context(session, user_id=SERVICE_USER_ID, workspace_id=job.workspace_id)
        versions = list(
            await session.scalars(
                select(DocumentVersion).where(DocumentVersion.document_id == document_id)
            )
        )
        keys = [version.object_key for version in versions]
    for key in keys:
        await store.delete(key)
    async with get_session_factory()() as session, session.begin():
        await set_tenant_context(session, user_id=SERVICE_USER_ID, workspace_id=job.workspace_id)
        await mark_completed(session, job_id=job.id, worker_id=worker_id)


async def fail_job(job: Job, worker_id: str, exc: Exception) -> None:
    async with get_session_factory()() as session, session.begin():
        await set_tenant_context(session, user_id=SERVICE_USER_ID, workspace_id=job.workspace_id)
        failed = await mark_failed(
            session,
            job_id=job.id,
            worker_id=worker_id,
            error_code="processing_failed",
            error_message=str(exc) or exc.__class__.__name__,
        )
        if failed.job_type is JobType.PROCESS_DOCUMENT:
            version = await session.get(
                DocumentVersion, UUID(failed.payload["document_version_id"])
            )
            if version is not None:
                version.status = (
                    DocumentVersionStatus.FAILED
                    if failed.state in {JobState.FAILED, JobState.DEAD_LETTER}
                    else DocumentVersionStatus.QUEUED
                )


async def process_job(job: Job, worker_id: str, store: LocalObjectStore) -> None:
    logger = structlog.get_logger().bind(
        worker_id=worker_id,
        workspace_id=str(job.workspace_id),
        job_id=str(job.id),
    )
    try:
        await begin_processing(job, worker_id)
        if job.job_type is JobType.PROCESS_DOCUMENT:
            await finish_document_job(job, worker_id, store)
        elif job.job_type is JobType.DELETE_OBJECT:
            await finish_delete_job(job, worker_id, store)
        else:
            raise RuntimeError("unsupported job type")
        logger.info("job_completed", job_type=job.job_type.value)
    except Exception as exc:
        logger.warning("job_failed", error_type=exc.__class__.__name__)
        try:
            await fail_job(job, worker_id, exc)
        except Exception:
            logger.exception("job_failure_recording_failed")


async def run() -> None:
    settings = get_settings()
    configure_logging(development=settings.environment == "development")
    logger = structlog.get_logger()
    worker_id = f"{socket.gethostname()}-{id(asyncio.current_task())}"[:128]
    store = LocalObjectStore(
        settings.object_store_root, read_chunk_bytes=settings.upload_chunk_bytes
    )
    stop = asyncio.Event()
    logger.info("worker_started", worker_id=worker_id)
    try:
        while not stop.is_set():
            async with get_session_factory()() as session, session.begin():
                jobs = await claim_jobs(
                    session,
                    worker_id=worker_id,
                    batch_size=settings.job_batch_size,
                    lease_seconds=settings.job_lease_seconds,
                )
            for job in jobs:
                if stop.is_set():
                    break
                await process_job(job, worker_id, store)
            await store.delete_stale_staging(older_than=datetime.now(UTC) - timedelta(hours=1))
            if not jobs:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=settings.job_poll_seconds)
                except TimeoutError:
                    pass
    except (KeyboardInterrupt, asyncio.CancelledError):
        stop.set()
    finally:
        await get_engine().dispose()
        logger.info("worker_stopped", worker_id=worker_id)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
