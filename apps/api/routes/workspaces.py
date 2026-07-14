from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from apps.api.dependencies import (
    AnyWorkspaceAccess,
    CurrentPrincipal,
    DatabaseSession,
    WorkspaceManagerAccess,
)
from packages.database.models import User, Workspace, WorkspaceMembership
from packages.database.tenant import set_tenant_context
from packages.domain.enums import WorkspaceRole
from packages.domain.errors import ConflictError, NotFoundError
from packages.domain.schemas import (
    MembershipCreate,
    MembershipResponse,
    MembershipUpdate,
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from packages.security.rbac import can_manage_role

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def workspace_response(workspace: Workspace, role: WorkspaceRole) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        role=role,
        created_at=workspace.created_at,
    )


def membership_response(membership: WorkspaceMembership) -> MembershipResponse:
    return MembershipResponse(
        id=membership.id,
        user_id=membership.user_id,
        email=membership.user.email,
        display_name=membership.user.display_name,
        role=membership.role,
        created_at=membership.created_at,
    )


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    principal: CurrentPrincipal,
    session: DatabaseSession,
) -> list[WorkspaceResponse]:
    rows = (
        await session.execute(
            select(Workspace, WorkspaceMembership.role)
            .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
            .where(WorkspaceMembership.user_id == principal.user.id)
            .order_by(Workspace.name)
        )
    ).all()
    return [workspace_response(workspace, role) for workspace, role in rows]


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreate,
    principal: CurrentPrincipal,
    session: DatabaseSession,
) -> WorkspaceResponse:
    workspace = Workspace(
        id=uuid4(),
        name=payload.name.strip(),
        slug=payload.slug,
        created_by=principal.user.id,
    )
    await set_tenant_context(session, user_id=principal.user.id, workspace_id=workspace.id)
    session.add(workspace)
    session.add(
        WorkspaceMembership(
            id=uuid4(),
            workspace_id=workspace.id,
            user_id=principal.user.id,
            role=WorkspaceRole.OWNER,
        )
    )
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("workspace slug is already in use") from exc
    return workspace_response(workspace, WorkspaceRole.OWNER)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: UUID,
    access: AnyWorkspaceAccess,
    session: DatabaseSession,
) -> WorkspaceResponse:
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFoundError("workspace not found")
    return workspace_response(workspace, access.membership.role)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: UUID,
    payload: WorkspaceUpdate,
    access: WorkspaceManagerAccess,
    session: DatabaseSession,
) -> WorkspaceResponse:
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFoundError("workspace not found")
    workspace.name = payload.name.strip()
    await session.flush()
    return workspace_response(workspace, access.membership.role)


@router.get("/{workspace_id}/members", response_model=list[MembershipResponse])
async def list_members(
    workspace_id: UUID,
    access: AnyWorkspaceAccess,
    session: DatabaseSession,
) -> list[MembershipResponse]:
    del access
    memberships = (
        (
            await session.scalars(
                select(WorkspaceMembership)
                .options(joinedload(WorkspaceMembership.user))
                .where(WorkspaceMembership.workspace_id == workspace_id)
                .order_by(WorkspaceMembership.created_at)
            )
        )
        .unique()
        .all()
    )
    return [membership_response(membership) for membership in memberships]


@router.post(
    "/{workspace_id}/members",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    workspace_id: UUID,
    payload: MembershipCreate,
    access: WorkspaceManagerAccess,
    session: DatabaseSession,
) -> MembershipResponse:
    if not can_manage_role(access.membership.role, payload.role):
        raise HTTPException(status_code=403, detail="role cannot be assigned by this actor")
    user = await session.scalar(
        select(User).where(User.email == str(payload.email).strip().lower())
    )
    if user is None:
        raise NotFoundError("user must register before being added")
    membership = WorkspaceMembership(
        id=uuid4(),
        workspace_id=workspace_id,
        user_id=user.id,
        role=payload.role,
        user=user,
    )
    session.add(membership)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("user is already a workspace member") from exc
    return membership_response(membership)


async def load_target_membership(
    session: DatabaseSession,
    workspace_id: UUID,
    membership_id: UUID,
) -> WorkspaceMembership:
    membership = await session.scalar(
        select(WorkspaceMembership)
        .options(joinedload(WorkspaceMembership.user))
        .where(
            WorkspaceMembership.id == membership_id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
    )
    if membership is None:
        raise NotFoundError("membership not found")
    return membership


@router.patch("/{workspace_id}/members/{membership_id}", response_model=MembershipResponse)
async def update_member(
    workspace_id: UUID,
    membership_id: UUID,
    payload: MembershipUpdate,
    access: WorkspaceManagerAccess,
    session: DatabaseSession,
) -> MembershipResponse:
    target = await load_target_membership(session, workspace_id, membership_id)
    if target.user_id == access.principal.user.id:
        raise ConflictError("you cannot change your own role")
    if not can_manage_role(access.membership.role, target.role) or not can_manage_role(
        access.membership.role, payload.role
    ):
        raise HTTPException(status_code=403, detail="membership cannot be managed by this actor")
    target.role = payload.role
    await session.flush()
    return membership_response(target)


@router.delete("/{workspace_id}/members/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    workspace_id: UUID,
    membership_id: UUID,
    access: WorkspaceManagerAccess,
    session: DatabaseSession,
) -> None:
    target = await load_target_membership(session, workspace_id, membership_id)
    if target.user_id == access.principal.user.id:
        raise ConflictError("you cannot remove yourself")
    if not can_manage_role(access.membership.role, target.role):
        raise HTTPException(status_code=403, detail="membership cannot be managed by this actor")
    await session.delete(target)
