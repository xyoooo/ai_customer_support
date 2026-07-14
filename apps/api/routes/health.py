from fastapi import APIRouter
from sqlalchemy import text

from apps.api.dependencies import DatabaseSession

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", include_in_schema=False)
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", include_in_schema=False)
async def readiness(session: DatabaseSession) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ready"}
