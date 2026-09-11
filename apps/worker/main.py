from __future__ import annotations

import asyncio
import hashlib
import socket
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import select

from packages.config import Settings, get_settings
from packages.database.models import Document, DocumentVersion, Job
from packages.database.session import get_engine, get_session_factory
from packages.database.tenant import set_tenant_context
from packages.domain.enums import DocumentVersionStatus, JobState, JobType
from packages.jobs.service import (
    claim_jobs,
    mark_completed,
    mark_failed,
    mark_processing,
    renew_lease,
)
from packages.observability import configure_logging
from packages.rag.repository import ChunkRepository
from packages.rag.service import Indexer, get_rag_indexer
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
    indexer: Indexer,
    settings: Settings,
) -> None:
    version_id = UUID(job.payload["document_version_id"])
    async with get_session_factory()() as session, session.begin():
        await set_tenant_context(session, user_id=SERVICE_USER_ID, workspace_id=job.workspace_id)
        version = await session.get(DocumentVersion, version_id)
        if version is None:
            raise RuntimeError("document version does not exist")
        object_key = version.object_key
        expected_size = version.byte_size
        expected_sha256 = version.sha256
        document_id = version.document_id
        media_type = version.media_type
        document = await session.get(Document, document_id)
        if document is None or document.deleted_at is not None:
            raise RuntimeError("document is missing or deleted")
        document_title = document.display_name
    metadata = await store.stat(object_key)
    if metadata.byte_size != expected_size:
        raise RuntimeError("stored object size no longer matches document metadata")

    digest = hashlib.sha256()
    content_parts: list[bytes] = []
    observed_size = 0
    async for part in store.read(object_key):
        observed_size += len(part)
        if observed_size > settings.max_upload_bytes:
            raise RuntimeError("stored object exceeds the configured upload limit")
        digest.update(part)
        content_parts.append(part)
    if observed_size != expected_size or digest.hexdigest() != expected_sha256:
        raise RuntimeError("stored object digest no longer matches document metadata")

    stop_renewal = asyncio.Event()
    renewal = asyncio.create_task(renew_document_lease(job, worker_id, settings, stop_renewal))
    try:
        records = await asyncio.to_thread(
            indexer.index_content,
            b"".join(content_parts),
            document_id=document_id,
            version_id=version_id,
            title=document_title,
            media_type=media_type,
        )
    finally:
        stop_renewal.set()
        await renewal

    async with get_session_factory()() as session, session.begin():
        await set_tenant_context(session, user_id=SERVICE_USER_ID, workspace_id=job.workspace_id)
        version = await session.scalar(
            select(DocumentVersion).where(DocumentVersion.id == version_id).with_for_update()
        )
        if version is None:
            raise RuntimeError("document version does not exist")
        document = await session.scalar(
            select(Document).where(Document.id == version.document_id).with_for_update()
        )
        if document is None or document.deleted_at is not None:
            raise RuntimeError("document is missing or deleted")
        await ChunkRepository().replace_version(
            session,
            workspace_id=job.workspace_id,
            records=records,
        )
        version.status = DocumentVersionStatus.ACTIVE
        await session.flush()
        document.active_version_id = version.id
        await mark_completed(session, job_id=job.id, worker_id=worker_id)


async def renew_document_lease(
    job: Job,
    worker_id: str,
    settings: Settings,
    stop: asyncio.Event,
) -> None:
    interval = max(1.0, settings.job_lease_seconds / 3)
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return
        except TimeoutError:
            async with get_session_factory()() as session, session.begin():
                await set_tenant_context(
                    session,
                    user_id=SERVICE_USER_ID,
                    workspace_id=job.workspace_id,
                )
                await renew_lease(
                    session,
                    job_id=job.id,
                    worker_id=worker_id,
                    lease_seconds=settings.job_lease_seconds,
                )


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
        await ChunkRepository().delete_document(
            session,
            workspace_id=job.workspace_id,
            document_id=document_id,
        )
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


async def process_job(
    job: Job,
    worker_id: str,
    store: LocalObjectStore,
    indexer: Indexer | None = None,
) -> None:
    logger = structlog.get_logger().bind(
        worker_id=worker_id,
        workspace_id=str(job.workspace_id),
        job_id=str(job.id),
    )
    try:
        await begin_processing(job, worker_id)
        if job.job_type is JobType.PROCESS_DOCUMENT:
            settings = get_settings()
            resolved_indexer = indexer or get_rag_indexer(
                str(settings.rag_model_path),
                settings.rag_embedding_threads,
                settings.rag_embedding_batch_size,
            )
            await finish_document_job(job, worker_id, store, resolved_indexer, settings)
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
