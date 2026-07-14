import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def register(client: TestClient, suffix: str) -> tuple[dict[str, object], str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"member-{suffix}@example.com",
            "display_name": f"Member {suffix}",
            "password": "a-secure-demo-password",
            "workspace_name": f"Workspace {suffix}",
            "workspace_slug": f"workspace-{suffix}",
        },
    )
    assert response.status_code == 201, response.text
    token = response.json()["token"]["access_token"]
    workspace_id = client.get(
        "/api/v1/workspaces", headers={"Authorization": f"Bearer {token}"}
    ).json()[0]["id"]
    return response.json()["user"], token, workspace_id


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_workspace_and_membership_lifecycle(client: TestClient) -> None:
    owner, owner_token, workspace_id = register(client, "owner")
    admin, admin_token, _ = register(client, "admin")
    agent, _, _ = register(client, "agent")

    created = client.post(
        "/api/v1/workspaces",
        headers=auth(owner_token),
        json={"name": "Second Workspace", "slug": "second-workspace"},
    )
    assert created.status_code == 201, created.text
    second_id = created.json()["id"]
    assert (
        client.get(f"/api/v1/workspaces/{second_id}", headers=auth(owner_token)).status_code == 200
    )
    renamed = client.patch(
        f"/api/v1/workspaces/{second_id}",
        headers=auth(owner_token),
        json={"name": "Renamed Workspace"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed Workspace"

    duplicate_slug = client.post(
        "/api/v1/workspaces",
        headers=auth(owner_token),
        json={"name": "Duplicate", "slug": "second-workspace"},
    )
    assert duplicate_slug.status_code == 409

    missing_user = client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        headers=auth(owner_token),
        json={"email": "not-registered@example.com", "role": "viewer"},
    )
    assert missing_user.status_code == 404

    admin_membership = client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        headers=auth(owner_token),
        json={"email": admin["email"], "role": "admin"},
    )
    agent_membership = client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        headers=auth(owner_token),
        json={"email": agent["email"], "role": "agent"},
    )
    assert admin_membership.status_code == agent_membership.status_code == 201

    duplicate_member = client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        headers=auth(owner_token),
        json={"email": agent["email"], "role": "viewer"},
    )
    assert duplicate_member.status_code == 409

    members = client.get(f"/api/v1/workspaces/{workspace_id}/members", headers=auth(owner_token))
    assert members.status_code == 200
    owner_membership_id = next(
        member["id"] for member in members.json() if member["user_id"] == owner["id"]
    )

    agent_id = agent_membership.json()["id"]
    demoted = client.patch(
        f"/api/v1/workspaces/{workspace_id}/members/{agent_id}",
        headers=auth(admin_token),
        json={"role": "viewer"},
    )
    assert demoted.status_code == 200
    assert demoted.json()["role"] == "viewer"

    admin_cannot_manage_owner = client.patch(
        f"/api/v1/workspaces/{workspace_id}/members/{owner_membership_id}",
        headers=auth(admin_token),
        json={"role": "viewer"},
    )
    assert admin_cannot_manage_owner.status_code == 403

    owner_cannot_change_self = client.patch(
        f"/api/v1/workspaces/{workspace_id}/members/{owner_membership_id}",
        headers=auth(owner_token),
        json={"role": "admin"},
    )
    assert owner_cannot_change_self.status_code == 409

    removed = client.delete(
        f"/api/v1/workspaces/{workspace_id}/members/{agent_id}",
        headers=auth(owner_token),
    )
    assert removed.status_code == 204
    assert (
        client.delete(
            f"/api/v1/workspaces/{workspace_id}/members/{agent_id}",
            headers=auth(owner_token),
        ).status_code
        == 404
    )

    owner_cannot_remove_self = client.delete(
        f"/api/v1/workspaces/{workspace_id}/members/{owner_membership_id}",
        headers=auth(owner_token),
    )
    assert owner_cannot_remove_self.status_code == 409


def test_admin_cannot_assign_admin_or_owner(client: TestClient) -> None:
    _, owner_token, workspace_id = register(client, "owner")
    admin, admin_token, _ = register(client, "admin")
    candidate, _, _ = register(client, "candidate")
    assert (
        client.post(
            f"/api/v1/workspaces/{workspace_id}/members",
            headers=auth(owner_token),
            json={"email": admin["email"], "role": "admin"},
        ).status_code
        == 201
    )

    assigning_admin = client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        headers=auth(admin_token),
        json={"email": candidate["email"], "role": "admin"},
    )
    assert assigning_admin.status_code == 403
    assigning_owner = client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        headers=auth(owner_token),
        json={"email": candidate["email"], "role": "owner"},
    )
    assert assigning_owner.status_code == 422
