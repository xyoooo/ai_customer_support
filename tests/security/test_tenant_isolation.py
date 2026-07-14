from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.integration, pytest.mark.security]
APP_URL = "postgresql://supportpilot_app:local_app_password@localhost:5432/supportpilot_test"


def register(client: TestClient, suffix: str) -> tuple[dict[str, object], str, dict[str, object]]:
    payload = {
        "email": f"user-{suffix}@example.com",
        "display_name": f"User {suffix}",
        "password": "a-secure-demo-password",
        "workspace_name": f"Workspace {suffix}",
        "workspace_slug": f"workspace-{suffix}",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    token = response.json()["token"]["access_token"]
    workspace = client.get(
        "/api/v1/workspaces", headers={"Authorization": f"Bearer {token}"}
    ).json()[0]
    return response.json()["user"], token, workspace


def test_api_rbac_and_cross_workspace_access(client: TestClient) -> None:
    owner_a, token_a, workspace_a = register(client, "a")
    user_b, token_b, workspace_b = register(client, "b")

    added = client.post(
        f"/api/v1/workspaces/{workspace_a['id']}/members",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"email": user_b["email"], "role": "viewer"},
    )
    assert added.status_code == 201, added.text
    assert added.json()["role"] == "viewer"

    viewer_can_read = client.get(
        f"/api/v1/workspaces/{workspace_a['id']}/members",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert viewer_can_read.status_code == 200
    assert {member["user_id"] for member in viewer_can_read.json()} == {
        owner_a["id"],
        user_b["id"],
    }

    viewer_cannot_manage = client.post(
        f"/api/v1/workspaces/{workspace_a['id']}/members",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"email": owner_a["email"], "role": "agent"},
    )
    assert viewer_cannot_manage.status_code == 403

    tenant_a_cannot_read_b = client.get(
        f"/api/v1/workspaces/{workspace_b['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert tenant_a_cannot_read_b.status_code == 404


def test_rls_filters_select_and_update_for_runtime_role(client: TestClient) -> None:
    user_a, _, workspace_a = register(client, "a")
    _, _, workspace_b = register(client, "b")

    with psycopg.connect(APP_URL) as connection:
        with connection.transaction():
            connection.execute(
                "SELECT set_config('app.current_user_id', %s, true)",
                (str(user_a["id"]),),
            )
            connection.execute(
                "SELECT set_config('app.current_workspace_id', %s, true)",
                (str(workspace_a["id"]),),
            )
            visible_ids = {
                row[0] for row in connection.execute("SELECT id FROM workspaces").fetchall()
            }
            assert visible_ids == {UUID(str(workspace_a["id"]))}

            changed = connection.execute(
                "UPDATE workspaces SET name = 'cross-tenant write' WHERE id = %s RETURNING id",
                (str(workspace_b["id"]),),
            ).fetchall()
            assert changed == []

            deleted = connection.execute(
                "DELETE FROM workspaces WHERE id = %s RETURNING id",
                (str(workspace_b["id"]),),
            ).fetchall()
            assert deleted == []

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with connection.transaction():
                    connection.execute(
                        """
                        INSERT INTO workspaces (id, name, slug, created_by)
                        VALUES (%s, 'Blocked', %s, %s)
                        """,
                        (uuid4(), f"blocked-{uuid4()}", str(user_a["id"])),
                    )


def test_transaction_local_context_does_not_leak(client: TestClient) -> None:
    user_a, _, workspace_a = register(client, "a")
    with psycopg.connect(APP_URL) as connection:
        with connection.transaction():
            connection.execute(
                "SELECT set_config('app.current_user_id', %s, true)",
                (str(user_a["id"]),),
            )
            connection.execute(
                "SELECT set_config('app.current_workspace_id', %s, true)",
                (str(workspace_a["id"]),),
            )
            assert connection.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 1

        with connection.transaction():
            assert (
                connection.execute(
                    "SELECT current_setting('app.current_workspace_id', true)"
                ).fetchone()[0]
                == ""
            )
            assert connection.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 0
