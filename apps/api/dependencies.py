from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.config import Settings, get_settings
from packages.database.models import User, WorkspaceMembership
from packages.database.session import get_db_session
from packages.database.tenant import set_tenant_context
from packages.domain.enums import WorkspaceRole
from packages.security.rbac import role_is_allowed
from packages.security.tokens import TokenError, decode_access_token
from packages.storage import LocalObjectStore, MalwareScanner, NoopMalwareScanner, ObjectStore

DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
bearer = HTTPBearer(auto_error=False)


@lru_cache
def get_object_store() -> ObjectStore:
    settings = get_settings()
    return LocalObjectStore(
        settings.object_store_root,
        read_chunk_bytes=settings.upload_chunk_bytes,
    )


@lru_cache
def get_malware_scanner() -> MalwareScanner:
    settings = get_settings()
    if not settings.allow_noop_malware_scanner:
        raise RuntimeError("a production malware scanner adapter is not configured")
    return NoopMalwareScanner()


ObjectStoreDependency = Annotated[ObjectStore, Depends(get_object_store)]
MalwareScannerDependency = Annotated[MalwareScanner, Depends(get_malware_scanner)]


@dataclass(frozen=True)
class Principal:
    user: User


@dataclass(frozen=True)
class WorkspaceAccess:
    principal: Principal
    membership: WorkspaceMembership


async def get_current_principal(
    session: DatabaseSession,
    settings: AppSettings,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    auth_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise auth_error
    try:
        claims = decode_access_token(credentials.credentials, settings)
    except TokenError as exc:
        raise auth_error from exc
    user = await session.get(User, claims.sub)
    if user is None or not user.is_active:
        raise auth_error
    await set_tenant_context(session, user_id=user.id)
    return Principal(user=user)


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def require_workspace_roles(*roles: WorkspaceRole) -> object:
    async def dependency(
        session: DatabaseSession,
        principal: CurrentPrincipal,
        workspace_id: Annotated[UUID, Path()],
    ) -> WorkspaceAccess:
        await set_tenant_context(
            session,
            user_id=principal.user.id,
            workspace_id=workspace_id,
        )
        membership = await session.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == principal.user.id,
            )
        )
        if membership is None:
            raise HTTPException(status_code=404, detail="workspace not found")
        if roles and not role_is_allowed(membership.role, roles):
            raise HTTPException(status_code=403, detail="insufficient workspace role")
        return WorkspaceAccess(principal=principal, membership=membership)

    return dependency


AnyWorkspaceAccess = Annotated[WorkspaceAccess, Depends(require_workspace_roles())]
WorkspaceManagerAccess = Annotated[
    WorkspaceAccess,
    Depends(require_workspace_roles(WorkspaceRole.OWNER, WorkspaceRole.ADMIN)),
]
WorkspaceContributorAccess = Annotated[
    WorkspaceAccess,
    Depends(
        require_workspace_roles(
            WorkspaceRole.OWNER,
            WorkspaceRole.ADMIN,
            WorkspaceRole.AGENT,
        )
    ),
]
