from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import PurePath
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from packages.config import Settings
from packages.database.models import Document, DocumentVersion, Job
from packages.database.tenant import set_tenant_context
from packages.domain.enums import DocumentVersionStatus, JobState, JobType
from packages.domain.errors import (
    ConflictError,
    NotFoundError,
    UploadRejectedError,
    UploadTooLargeError,
)
from packages.storage import MalwareScanner, ObjectStore

_SAFE_FILENAME = re.compile(r"[^\w.() -]+", flags=re.UNICODE)
_MEDIA_BY_EXTENSION = {
    ".pdf": ("application/pdf",),
    ".txt": ("text/plain",),
    ".md": ("text/markdown", "text/plain"),
    ".html": ("text/html",),
    ".htm": ("text/html",),
}


@dataclass(frozen=True)
class UploadResult:
    document: Document
    version: DocumentVersion
    job: Job


def sanitize_filename(filename: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", filename or "upload")
    leaf = PurePath(normalized.replace("\\", "/")).name
    cleaned = "".join(character for character in leaf if character.isprintable())
    cleaned = _SAFE_FILENAME.sub("_", cleaned).strip(" .")
    if not cleaned:
        cleaned = "upload"
    return cleaned[:255]


def validate_media_type(filename: str, declared_type: str | None, prefix: bytes) -> str:
    extension = PurePath(filename).suffix.lower()
    accepted_types = _MEDIA_BY_EXTENSION.get(extension)
    if accepted_types is None:
        raise UploadRejectedError("supported file types are PDF, Markdown, text, and HTML")
    normalized_type = (declared_type or "").split(";", 1)[0].strip().lower()
    if normalized_type not in accepted_types:
        raise UploadRejectedError("declared media type does not match the file extension")
    if extension == ".pdf":
        if not prefix.startswith(b"%PDF-"):
            raise UploadRejectedError("PDF signature is missing or invalid")
        return "application/pdf"
    if b"\x00" in prefix:
        raise UploadRejectedError("text documents cannot contain binary null bytes")
    try:
        decoded = prefix.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UploadRejectedError("text documents must be UTF-8 encoded") from exc
    if extension in {".html", ".htm"} and "<" not in decoded:
        raise UploadRejectedError("HTML content does not contain an HTML tag")
    return accepted_types[0]


async def _existing_result(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    idempotency_key: str,
) -> UploadResult | None:
    job = await session.scalar(
        select(Job).where(
            Job.workspace_id == workspace_id,
            Job.job_type == JobType.PROCESS_DOCUMENT,
            Job.idempotency_key == idempotency_key,
        )
    )
    if job is None:
        return None
    try:
        document_id = UUID(job.payload["document_id"])
        version_id = UUID(job.payload["document_version_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ConflictError("existing idempotent job has an incompatible payload") from exc
    document = await session.get(Document, document_id)
    version = await session.get(DocumentVersion, version_id)
    if document is None or version is None:
        raise ConflictError("existing idempotent job references missing document data")
    return UploadResult(document=document, version=version, job=job)


async def upload_document_version(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    upload: UploadFile,
    idempotency_key: str,
    store: ObjectStore,
    scanner: MalwareScanner,
    settings: Settings,
    document_id: UUID | None = None,
    display_name: str | None = None,
) -> UploadResult:
    key = idempotency_key.strip()
    if not key or len(key) > 255:
        raise UploadRejectedError("Idempotency-Key must contain 1 to 255 characters")
    existing = await _existing_result(session, workspace_id=workspace_id, idempotency_key=key)
    if existing is not None:
        return existing

    safe_filename = sanitize_filename(upload.filename)
    staging_key = f"staging/{workspace_id}/{uuid4()}"
    digest = hashlib.sha256()
    prefix = bytearray()
    byte_size = 0
    promoted_key: str | None = None

    async def chunks() -> AsyncIterator[bytes]:
        nonlocal byte_size
        while chunk := await upload.read(settings.upload_chunk_bytes):
            byte_size += len(chunk)
            if byte_size > settings.max_upload_bytes:
                raise UploadTooLargeError(
                    f"upload exceeds the {settings.max_upload_bytes}-byte limit"
                )
            digest.update(chunk)
            if len(prefix) < 8192:
                prefix.extend(chunk[: 8192 - len(prefix)])
            yield chunk

    try:
        staged = await store.write(staging_key, chunks())
        if byte_size == 0:
            raise UploadRejectedError("empty documents are not accepted")
        media_type = validate_media_type(safe_filename, upload.content_type, bytes(prefix))
        await scanner.scan(store=store, metadata=staged, media_type=media_type)

        used_bytes = await session.scalar(
            select(func.coalesce(func.sum(DocumentVersion.byte_size), 0)).where(
                DocumentVersion.workspace_id == workspace_id
            )
        )
        if int(used_bytes or 0) + byte_size > settings.max_workspace_storage_bytes:
            raise UploadTooLargeError("workspace document storage quota would be exceeded")

        document: Document
        if document_id is None:
            resolved_name = (display_name or PurePath(safe_filename).stem or safe_filename).strip()[
                :255
            ]
            document = Document(
                id=uuid4(),
                workspace_id=workspace_id,
                display_name=resolved_name,
                created_by=user_id,
            )
            version_number = 1
            session.add(document)
        else:
            existing_document = await session.scalar(
                select(Document)
                .where(
                    Document.id == document_id,
                    Document.workspace_id == workspace_id,
                    Document.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if existing_document is None:
                raise NotFoundError("document not found")
            document = existing_document
            version_number = (
                int(
                    await session.scalar(
                        select(func.coalesce(func.max(DocumentVersion.version_number), 0)).where(
                            DocumentVersion.document_id == document.id
                        )
                    )
                    or 0
                )
                + 1
            )

        sha256 = digest.hexdigest()
        duplicate = await session.scalar(
            select(DocumentVersion.id).where(
                DocumentVersion.workspace_id == workspace_id,
                DocumentVersion.document_id == document.id,
                DocumentVersion.sha256 == sha256,
            )
        )
        if duplicate is not None:
            raise ConflictError("this document already has a version with identical content")

        version = DocumentVersion(
            id=uuid4(),
            workspace_id=workspace_id,
            document_id=document.id,
            version_number=version_number,
            object_key="",
            original_filename=safe_filename,
            media_type=media_type,
            byte_size=byte_size,
            sha256=sha256,
            status=DocumentVersionStatus.QUEUED,
            created_by=user_id,
        )
        final_key = (
            f"workspaces/{workspace_id}/documents/{document.id}/versions/{version.id}/"
            f"{safe_filename}"
        )
        await store.move(staging_key, final_key)
        promoted_key = final_key
        version.object_key = final_key
        job = Job(
            id=uuid4(),
            workspace_id=workspace_id,
            job_type=JobType.PROCESS_DOCUMENT,
            payload={
                "document_id": str(document.id),
                "document_version_id": str(version.id),
            },
            state=JobState.QUEUED,
            idempotency_key=key,
            max_attempts=settings.job_max_attempts,
        )
        session.add_all([version, job])
        try:
            await session.flush()
            await session.commit()
        except BaseException:
            await session.rollback()
            await store.delete(final_key)
            promoted_key = None
            raise
        await set_tenant_context(session, user_id=user_id, workspace_id=workspace_id)
        return UploadResult(document=document, version=version, job=job)
    except IntegrityError as exc:
        await store.delete(staging_key)
        raise ConflictError("document version or idempotency key already exists") from exc
    except BaseException:
        await store.delete(staging_key)
        if promoted_key is not None:
            await store.delete(promoted_key)
        raise
    finally:
        await upload.close()
