import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def registration_payload(*, suffix: str = "one") -> dict[str, str]:
    return {
        "email": f"owner-{suffix}@example.com",
        "display_name": f"Owner {suffix}",
        "password": "a-secure-demo-password",
        "workspace_name": f"Workspace {suffix}",
        "workspace_slug": f"workspace-{suffix}",
    }


def test_registration_login_and_workspace_listing(client: TestClient) -> None:
    payload = registration_payload()
    registered = client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201, registered.text
    assert registered.json()["user"]["email"] == payload["email"]
    assert "httponly" in registered.headers["set-cookie"].lower()
    assert "samesite=lax" in registered.headers["set-cookie"].lower()

    token = registered.json()["token"]["access_token"]
    workspaces = client.get("/api/v1/workspaces", headers={"Authorization": f"Bearer {token}"})
    assert workspaces.status_code == 200, workspaces.text
    assert workspaces.json()[0]["slug"] == payload["workspace_slug"]
    assert workspaces.json()[0]["role"] == "owner"

    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": "wrong"},
    )
    unknown_email = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "wrong"},
    )
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["message"] == unknown_email.json()["message"]


def test_refresh_rotation_detects_replay_and_revokes_family(client: TestClient) -> None:
    registered = client.post("/api/v1/auth/register", json=registration_payload())
    original_cookie = registered.cookies.get("supportpilot_refresh")
    assert original_cookie

    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    replacement_cookie = refreshed.cookies.get("supportpilot_refresh")
    assert replacement_cookie and replacement_cookie != original_cookie

    client.cookies.delete("supportpilot_refresh")
    client.cookies.set("supportpilot_refresh", original_cookie, path="/api/v1/auth")
    replay = client.post("/api/v1/auth/refresh")
    assert replay.status_code == 401
    assert "reuse" in replay.json()["message"]

    client.cookies.delete("supportpilot_refresh")
    client.cookies.set("supportpilot_refresh", replacement_cookie, path="/api/v1/auth")
    family_is_revoked = client.post("/api/v1/auth/refresh")
    assert family_is_revoked.status_code == 401


def test_logout_revokes_refresh_session(client: TestClient) -> None:
    client.post("/api/v1/auth/register", json=registration_payload())
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_login_me_duplicate_registration_and_unauthorized_requests(client: TestClient) -> None:
    payload = registration_payload()
    registered = client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201

    duplicate = client.post("/api/v1/auth/register", json=payload)
    assert duplicate.status_code == 409

    logged_in = client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"].upper(), "password": payload["password"]},
    )
    assert logged_in.status_code == 200
    token = logged_in.json()["token"]["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == payload["email"]

    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid-token"}).status_code
        == 401
    )

    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh").status_code == 401
    assert client.post("/api/v1/auth/logout").status_code == 204


def test_health_and_api_metadata(client: TestClient) -> None:
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready"}
    assert client.get("/api/v1").json()["version"] == "v1"
