from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.dependencies import get_object_store
from apps.api.main import app
from packages.storage.local import LocalObjectStore

pytestmark = pytest.mark.integration


def auth(token: str, *, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def register(client: TestClient, suffix: str) -> tuple[dict[str, object], str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"documents-{suffix}@example.com",
            "display_name": f"Documents {suffix}",
            "password": "a-secure-demo-password",
            "workspace_name": f"Documents {suffix}",
            "workspace_slug": f"documents-{suffix}",
        },
    )
    assert response.status_code == 201, response.text
    token = response.json()["token"]["access_token"]
    workspace_id = client.get("/api/v1/workspaces", headers=auth(token)).json()[0]["id"]
    return response.json()["user"], token, workspace_id


def upload_markdown(
    client: TestClient,
    *,
    workspace_id: str,
    token: str,
    key: str,
    content: bytes = b"# Support guide\n\nSynthetic content only.\n",
):
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=auth(token, idempotency_key=key),
        data={"display_name": "Support guide"},
        files={"file": ("support-guide.md", content, "text/markdown")},
    )


def test_upload_is_idempotent_versioned_and_visible(tmp_path: Path, client: TestClient) -> None:
    store = LocalObjectStore(tmp_path)
    app.dependency_overrides[get_object_store] = lambda: store
    try:
        _, token, workspace_id = register(client, "owner")
        created = upload_markdown(
            client, workspace_id=workspace_id, token=token, key="upload-guide-v1"
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["document"]["display_name"] == "Support guide"
        assert body["version"]["version_number"] == 1
        assert body["version"]["status"] == "queued"
        assert body["version"]["sha256"]
        assert body["job"]["state"] == "queued"

        replay = upload_markdown(
            client, workspace_id=workspace_id, token=token, key="upload-guide-v1"
        )
        assert replay.status_code == 201
        assert replay.json()["version"]["id"] == body["version"]["id"]
        assert replay.json()["job"]["id"] == body["job"]["id"]

        documents = client.get(f"/api/v1/workspaces/{workspace_id}/documents", headers=auth(token))
        assert documents.status_code == 200
        assert len(documents.json()) == 1
        assert documents.json()[0]["latest_version"]["version_number"] == 1

        duplicate = client.post(
            f"/api/v1/workspaces/{workspace_id}/documents/{body['document']['id']}/versions",
            headers=auth(token, idempotency_key="duplicate-content"),
            files={
                "file": (
                    "support-guide.md",
                    b"# Support guide\n\nSynthetic content only.\n",
                    "text/markdown",
                )
            },
        )
        assert duplicate.status_code == 409

        version_two = client.post(
            f"/api/v1/workspaces/{workspace_id}/documents/{body['document']['id']}/versions",
            headers=auth(token, idempotency_key="upload-guide-v2"),
            files={"file": ("support-guide.md", b"# Support guide v2\n", "text/markdown")},
        )
        assert version_two.status_code == 201, version_two.text
        assert version_two.json()["version"]["version_number"] == 2

        detail = client.get(
            f"/api/v1/workspaces/{workspace_id}/documents/{body['document']['id']}",
            headers=auth(token),
        )
        assert [version["version_number"] for version in detail.json()["versions"]] == [2, 1]
        assert len(detail.json()["jobs"]) == 2
        assert len(list(tmp_path.rglob("*.md"))) == 2
    finally:
        app.dependency_overrides.pop(get_object_store, None)


def test_upload_validation_permissions_and_soft_delete(tmp_path: Path, client: TestClient) -> None:
    app.dependency_overrides[get_object_store] = lambda: LocalObjectStore(tmp_path)
    try:
        owner, owner_token, workspace_id = register(client, "secure-owner")
        viewer, viewer_token, _ = register(client, "secure-viewer")
        added = client.post(
            f"/api/v1/workspaces/{workspace_id}/members",
            headers=auth(owner_token),
            json={"email": viewer["email"], "role": "viewer"},
        )
        assert added.status_code == 201

        blocked = upload_markdown(
            client, workspace_id=workspace_id, token=viewer_token, key="viewer-upload"
        )
        assert blocked.status_code == 403

        bad_signature = client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            headers=auth(owner_token, idempotency_key="bad-pdf"),
            files={"file": ("fake.pdf", b"not-pdf", "application/pdf")},
        )
        assert bad_signature.status_code == 422
        assert not list(tmp_path.rglob("*.*"))

        created = upload_markdown(
            client, workspace_id=workspace_id, token=owner_token, key="deletable"
        )
        document_id = created.json()["document"]["id"]
        assert (
            client.delete(
                f"/api/v1/workspaces/{workspace_id}/documents/{document_id}",
                headers=auth(owner_token),
            ).status_code
            == 204
        )
        assert (
            client.get(
                f"/api/v1/workspaces/{workspace_id}/documents/{document_id}",
                headers=auth(owner_token),
            ).status_code
            == 404
        )
        assert owner["id"]
    finally:
        app.dependency_overrides.pop(get_object_store, None)
