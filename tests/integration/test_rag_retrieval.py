from __future__ import annotations

from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from apps.api.dependencies import get_object_store, get_rag_service
from apps.api.main import app
from apps.worker.main import process_job
from packages.database.session import get_session_factory
from packages.jobs.service import claim_jobs
from packages.rag.chunking import StructureAwareChunker
from packages.rag.parsing import CanonicalParser
from packages.rag.service import RAGIndexer, RetrievalService
from packages.storage.local import LocalObjectStore

pytestmark = pytest.mark.integration
APP_URL = "postgresql://supportpilot_app:local_app_password@localhost:5432/supportpilot_test"


class TestBudget:
    def fits(self, text: str) -> bool:
        return bool(text.strip())

    def assert_fits(self, text: str) -> None:
        assert self.fits(text)


def vector(index: int) -> tuple[float, ...]:
    return tuple(1.0 if position == index else 0.0 for position in range(384))


class TestEmbedder:
    def embed_documents(self, texts):  # type: ignore[no-untyped-def]
        return tuple(vector(0 if "RET-30" in text else 1) for text in texts)

    def embed_queries(self, texts):  # type: ignore[no-untyped-def]
        return tuple(vector(0 if "refund" in text.casefold() else 1) for text in texts)


INDEXER = RAGIndexer(
    parser=CanonicalParser(),
    chunker=StructureAwareChunker(TestBudget()),
    embedder=TestEmbedder(),
    batch_size=2,
)


def register(client: TestClient, suffix: str) -> tuple[str, dict[str, object]]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"rag-{suffix}@example.com",
            "display_name": f"RAG {suffix}",
            "password": "a-secure-demo-password",
            "workspace_name": f"RAG {suffix}",
            "workspace_slug": f"rag-{suffix}",
        },
    )
    assert response.status_code == 201, response.text
    token = response.json()["token"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    workspace = client.get("/api/v1/workspaces", headers=headers).json()[0]
    return token, workspace


async def claim_one(worker_id: str):  # type: ignore[no-untyped-def]
    async with get_session_factory()() as session, session.begin():
        jobs = await claim_jobs(session, worker_id=worker_id, batch_size=1, lease_seconds=60)
        assert len(jobs) == 1
        return jobs[0]


def upload_and_index(
    client: TestClient,
    store: LocalObjectStore,
    *,
    token: str,
    workspace_id: object,
    suffix: str,
    content: bytes,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"rag-{suffix}"},
        files={"file": (f"{suffix}.md", content, "text/markdown")},
    )
    assert response.status_code == 201, response.text
    job = client.portal.call(claim_one, f"rag-worker-{suffix}")
    client.portal.call(process_job, job, f"rag-worker-{suffix}", store, INDEXER)
    return response.json()


def test_selected_pipeline_indexes_searches_and_hides_other_tenants(
    client: TestClient, tmp_path: Path
) -> None:
    store = LocalObjectStore(tmp_path)
    app.dependency_overrides[get_object_store] = lambda: store
    app.dependency_overrides[get_rag_service] = lambda: RetrievalService(TestEmbedder())
    try:
        token_a, workspace_a = register(client, "a")
        upload_a = upload_and_index(
            client,
            store,
            token=token_a,
            workspace_id=workspace_a["id"],
            suffix="a",
            content=(
                b"# Returns\nUse refund code RET-30. Refunds take thirty days.\n\n"
                b"# Shipping\nDelivery takes two days."
            ),
        )
        token_b, workspace_b = register(client, "b")
        upload_b = upload_and_index(
            client,
            store,
            token=token_b,
            workspace_id=workspace_b["id"],
            suffix="b",
            content=b"# Private\nUse secret refund code RET-31.",
        )

        response = client.post(
            f"/api/v1/workspaces/{workspace_a['id']}/evidence/search",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"query": "Which refund uses RET-30?", "result_count": 2},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["pipeline_version"] == "rag-v1-c1-e1"
        assert payload["results"][0]["document_id"] == upload_a["document"]["id"]
        assert payload["results"][0]["dense_rank"] == 1
        assert payload["results"][0]["lexical_rank"] == 1
        assert payload["results"][0]["locators"]
        assert all(
            result["document_id"] != upload_b["document"]["id"] for result in payload["results"]
        )

        with psycopg.connect(APP_URL) as connection, connection.transaction():
            connection.execute(
                "SELECT set_config('app.current_workspace_id', %s, true)",
                (str(workspace_a["id"]),),
            )
            assert connection.execute(
                "SELECT count(DISTINCT document_id), min(pipeline_version) FROM document_chunks"
            ).fetchone() == (1, "rag-v1-c1-e1")

        forbidden = client.post(
            f"/api/v1/workspaces/{workspace_b['id']}/evidence/search",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"query": "RET-31"},
        )
        assert forbidden.status_code == 404
    finally:
        app.dependency_overrides.pop(get_rag_service, None)
        app.dependency_overrides.pop(get_object_store, None)


def test_retrieval_endpoint_maps_query_and_runtime_failures(client: TestClient) -> None:
    token, workspace = register(client, "errors")

    class FailingService:
        def __init__(self, error: Exception) -> None:
            self.error = error

        async def search(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise self.error

    try:
        app.dependency_overrides[get_rag_service] = lambda: FailingService(
            ValueError("query cannot be embedded")
        )
        invalid = client.post(
            f"/api/v1/workspaces/{workspace['id']}/evidence/search",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": "valid shape"},
        )
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "invalid_query"

        app.dependency_overrides[get_rag_service] = lambda: FailingService(RuntimeError("offline"))
        unavailable = client.post(
            f"/api/v1/workspaces/{workspace['id']}/evidence/search",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": "valid shape"},
        )
        assert unavailable.status_code == 503
        assert unavailable.json()["code"] == "retrieval_unavailable"

        too_long = client.post(
            f"/api/v1/workspaces/{workspace['id']}/evidence/search",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": "x" * 2001},
        )
        assert too_long.status_code == 422
    finally:
        app.dependency_overrides.pop(get_rag_service, None)
