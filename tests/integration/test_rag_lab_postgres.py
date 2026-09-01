from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.config import get_settings
from packages.database.tenant import set_tenant_context
from packages.rag_lab.models import Chunk, IndexedChunk, SourceLocator
from packages.rag_lab.profiles import RetrievalSpec
from packages.rag_lab.retrieval import PostgresHybridIndex

pytestmark = pytest.mark.integration


def _register_and_upload(client: TestClient) -> tuple[dict[str, object], dict[str, object]]:
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": "rag-lab@example.com",
            "display_name": "RAG Lab",
            "password": "a-secure-demo-password",
            "workspace_name": "RAG Lab",
            "workspace_slug": "rag-lab",
        },
    )
    assert registered.status_code == 201, registered.text
    payload = registered.json()
    token = payload["token"]["access_token"]
    workspace = client.get(
        "/api/v1/workspaces", headers={"Authorization": f"Bearer {token}"}
    ).json()[0]
    uploaded = client.post(
        f"/api/v1/workspaces/{workspace['id']}/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "rag-lab-postgres",
        },
        files={"file": ("returns.txt", b"refund code RET-30", "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    return payload, {"workspace": workspace, "upload": uploaded.json()}


@pytest.mark.asyncio
async def test_postgres_exact_hybrid_index_is_idempotent_and_tenant_scoped(
    client: TestClient,
) -> None:
    user_payload, seeded = _register_and_upload(client)
    workspace_id = str(seeded["workspace"]["id"])
    upload = seeded["upload"]
    document_id = str(upload["document"]["id"])
    version_id = str(upload["version"]["id"])
    source_text = "refund code RET-30"
    chunk = Chunk(
        chunk_id="a" * 64,
        document_id=document_id,
        version_id=version_id,
        order=0,
        text=source_text,
        embedding_text=source_text,
        token_count=4,
        locators=(SourceLocator("b000000", 0, 0, len(source_text)),),
        heading_path=(),
        page_number=None,
    )
    record = IndexedChunk(workspace_id, chunk, (1.0, 0.0, 0.0))
    index = PostgresHybridIndex(RetrievalSpec(result_count=5))
    profile = "f" * 64

    engine = create_async_engine(str(get_settings().database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session, session.begin():
            await set_tenant_context(
                session,
                user_id=UUID(str(user_payload["user"]["id"])),
                workspace_id=UUID(workspace_id),
            )
            await index.replace_version(
                session,
                workspace_id=workspace_id,
                profile_fingerprint=profile,
                records=(record,),
            )
            await index.replace_version(
                session,
                workspace_id=workspace_id,
                profile_fingerprint=profile,
                records=(record,),
            )
            trace = await index.search_with_trace(
                session,
                workspace_id=workspace_id,
                profile_fingerprint=profile,
                query="RET-30 refund",
                query_embedding=(1.0, 0.0, 0.0),
            )
    finally:
        await engine.dispose()

    assert len(trace.results) == 1
    assert trace.results[0].chunk.chunk_id == chunk.chunk_id
    assert trace.results[0].dense_rank == 1
    assert trace.results[0].lexical_rank == 1
    assert trace.results[0].workspace_id == workspace_id
