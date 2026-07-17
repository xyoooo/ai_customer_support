from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from apps.api.dependencies import get_object_store
from apps.api.main import app
from apps.worker.main import process_job
from packages.database.models import Job
from packages.database.session import get_session_factory
from packages.database.tenant import set_worker_context
from packages.domain.errors import ConflictError
from packages.jobs.service import claim_jobs, mark_completed, mark_failed
from packages.storage.local import LocalObjectStore

pytestmark = pytest.mark.integration


def setup_upload(client: TestClient, tmp_path: Path, suffix: str):  # type: ignore[no-untyped-def]
    store = LocalObjectStore(tmp_path)
    app.dependency_overrides[get_object_store] = lambda: store
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"worker-{suffix}@example.com",
            "display_name": f"Worker {suffix}",
            "password": "a-secure-demo-password",
            "workspace_name": f"Worker {suffix}",
            "workspace_slug": f"worker-{suffix}",
        },
    )
    token = registered.json()["token"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    uploaded = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers={**headers, "Idempotency-Key": f"worker-upload-{suffix}"},
        files={"file": ("worker.md", b"# Worker fixture\n", "text/markdown")},
    )
    assert uploaded.status_code == 201, uploaded.text
    return store, headers, workspace_id, uploaded.json()


async def claim_one(worker_id: str):  # type: ignore[no-untyped-def]
    async with get_session_factory()() as session, session.begin():
        return await claim_jobs(session, worker_id=worker_id, batch_size=1, lease_seconds=60)


async def expire_job(job_id):  # type: ignore[no-untyped-def]
    async with get_session_factory()() as session, session.begin():
        await set_worker_context(session, worker_id="test-controller")
        job = await session.get(Job, job_id)
        assert job is not None
        job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)


async def stale_complete(job_id):  # type: ignore[no-untyped-def]
    async with get_session_factory()() as session, session.begin():
        await set_worker_context(session, worker_id="worker-old")
        await mark_completed(session, job_id=job_id, worker_id="worker-old")


async def exhaust_job(job_id):  # type: ignore[no-untyped-def]
    resolved_job_id = UUID(str(job_id))
    async with get_session_factory()() as session, session.begin():
        await set_worker_context(session, worker_id="test-controller")
        job = await session.get(Job, resolved_job_id)
        assert job is not None
        job.max_attempts = 1
    claimed = await claim_one("worker-failing")
    async with get_session_factory()() as session, session.begin():
        await set_worker_context(session, worker_id="worker-failing")
        return await mark_failed(
            session,
            job_id=claimed[0].id,
            worker_id="worker-failing",
            error_code="fixture_failure",
            error_message="synthetic processing failure",
        )


def test_worker_claim_is_exclusive_and_processing_activates_version(
    tmp_path: Path, client: TestClient
) -> None:
    store, headers, workspace_id, uploaded = setup_upload(client, tmp_path, "complete")
    try:
        claimed = client.portal.call(claim_one, "worker-one")
        assert [str(job.id) for job in claimed] == [uploaded["job"]["id"]]

        other_claim = client.portal.call(claim_one, "worker-two")
        assert other_claim == []

        client.portal.call(process_job, claimed[0], "worker-one", store)
        detail = client.get(
            f"/api/v1/workspaces/{workspace_id}/documents/{uploaded['document']['id']}",
            headers=headers,
        )
        assert detail.status_code == 200
        assert detail.json()["active_version_id"] == uploaded["version"]["id"]
        assert detail.json()["versions"][0]["status"] == "active"
        assert detail.json()["jobs"][0]["state"] == "completed"
    finally:
        app.dependency_overrides.pop(get_object_store, None)


def test_expired_lease_is_reclaimed_and_stale_worker_is_rejected(
    tmp_path: Path, client: TestClient
) -> None:
    _, _, _, uploaded = setup_upload(client, tmp_path, "lease")
    try:
        first = client.portal.call(claim_one, "worker-old")
        client.portal.call(expire_job, first[0].id)

        reclaimed = client.portal.call(claim_one, "worker-new")
        assert reclaimed[0].attempt_count == 2
        assert reclaimed[0].lease_owner == "worker-new"

        with pytest.raises(ConflictError):
            client.portal.call(stale_complete, reclaimed[0].id)
        assert uploaded["job"]["id"] == str(reclaimed[0].id)
    finally:
        app.dependency_overrides.pop(get_object_store, None)


def test_dead_letter_job_can_be_retried_by_contributor(tmp_path: Path, client: TestClient) -> None:
    _, headers, workspace_id, uploaded = setup_upload(client, tmp_path, "retry")
    try:
        failed = client.portal.call(exhaust_job, uploaded["job"]["id"])
        assert failed.state.value == "dead_letter"
        retried = client.post(
            f"/api/v1/workspaces/{workspace_id}/jobs/{uploaded['job']['id']}/retry",
            headers=headers,
        )
        assert retried.status_code == 200, retried.text
        assert retried.json()["state"] == "retrying"
        assert retried.json()["attempt_count"] == 0
        assert retried.json()["error_message"] is None
    finally:
        app.dependency_overrides.pop(get_object_store, None)
