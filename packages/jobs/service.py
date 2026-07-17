from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models import Job
from packages.database.tenant import set_worker_context
from packages.domain.enums import JobState
from packages.domain.errors import ConflictError, NotFoundError


async def claim_jobs(
    session: AsyncSession,
    *,
    worker_id: str,
    batch_size: int,
    lease_seconds: int,
) -> list[Job]:
    await set_worker_context(session, worker_id=worker_id)
    now = datetime.now(UTC)
    due = and_(
        Job.state.in_([JobState.QUEUED, JobState.RETRYING]),
        Job.available_at <= now,
    )
    expired = and_(
        Job.state.in_([JobState.LEASED, JobState.PROCESSING]),
        Job.lease_expires_at.is_not(None),
        Job.lease_expires_at < now,
    )
    jobs = list(
        await session.scalars(
            select(Job)
            .where(or_(due, expired))
            .order_by(Job.available_at, Job.created_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
    )
    for job in jobs:
        job.state = JobState.LEASED
        job.lease_owner = worker_id[:128]
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.attempt_count += 1
        job.error_code = None
        job.error_message = None
    await session.flush()
    return jobs


async def require_owned_job(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: str,
) -> Job:
    job = await session.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if job is None:
        raise NotFoundError("job not found")
    if job.lease_owner != worker_id or job.state not in {JobState.LEASED, JobState.PROCESSING}:
        raise ConflictError("job lease is no longer owned by this worker")
    if job.lease_expires_at is None or job.lease_expires_at <= datetime.now(UTC):
        raise ConflictError("job lease has expired")
    return job


async def mark_processing(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: str,
) -> Job:
    job = await require_owned_job(session, job_id=job_id, worker_id=worker_id)
    job.state = JobState.PROCESSING
    await session.flush()
    return job


async def renew_lease(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: str,
    lease_seconds: int,
) -> Job:
    job = await require_owned_job(session, job_id=job_id, worker_id=worker_id)
    job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
    await session.flush()
    return job


async def mark_completed(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: str,
) -> Job:
    job = await require_owned_job(session, job_id=job_id, worker_id=worker_id)
    job.state = JobState.COMPLETED
    job.lease_owner = None
    job.lease_expires_at = None
    job.error_code = None
    job.error_message = None
    await session.flush()
    await session.refresh(job)
    return job


async def mark_failed(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: str,
    error_code: str,
    error_message: str,
    retryable: bool = True,
) -> Job:
    job = await require_owned_job(session, job_id=job_id, worker_id=worker_id)
    job.error_code = error_code[:64]
    job.error_message = error_message[:1000]
    job.lease_owner = None
    job.lease_expires_at = None
    if retryable and job.attempt_count < job.max_attempts:
        base_delay = min(300, 2 ** max(0, job.attempt_count - 1))
        jitter = secrets.randbelow(max(1, base_delay // 2 + 1))
        job.state = JobState.RETRYING
        job.available_at = datetime.now(UTC) + timedelta(seconds=base_delay + jitter)
    else:
        job.state = (
            JobState.DEAD_LETTER if job.attempt_count >= job.max_attempts else JobState.FAILED
        )
    await session.flush()
    return job


async def retry_job(session: AsyncSession, *, job_id: UUID, workspace_id: UUID) -> Job:
    job = await session.scalar(
        select(Job).where(Job.id == job_id, Job.workspace_id == workspace_id).with_for_update()
    )
    if job is None:
        raise NotFoundError("job not found")
    if job.state not in {JobState.FAILED, JobState.DEAD_LETTER}:
        raise ConflictError("only failed or dead-letter jobs can be retried")
    job.state = JobState.RETRYING
    job.available_at = datetime.now(UTC)
    job.attempt_count = 0
    job.lease_owner = None
    job.lease_expires_at = None
    job.error_code = None
    job.error_message = None
    await session.flush()
    await session.refresh(job)
    return job
