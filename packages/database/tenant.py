from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_tenant_context(
    session: AsyncSession,
    *,
    user_id: UUID,
    workspace_id: UUID | None = None,
) -> None:
    """Set identity values locally for the current database transaction.

    `is_local=true` ensures pooled connections cannot leak tenant state into the
    next request after commit or rollback.
    """

    await session.execute(
        text("SELECT set_config('app.current_user_id', :user_id, true)"),
        {"user_id": str(user_id)},
    )
    await session.execute(
        text("SELECT set_config('app.current_workspace_id', :workspace_id, true)"),
        {"workspace_id": str(workspace_id) if workspace_id else ""},
    )
