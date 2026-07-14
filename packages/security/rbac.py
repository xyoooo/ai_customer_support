from collections.abc import Collection

from packages.domain.enums import WorkspaceRole

ROLE_RANK = {
    WorkspaceRole.VIEWER: 10,
    WorkspaceRole.AGENT: 20,
    WorkspaceRole.ADMIN: 30,
    WorkspaceRole.OWNER: 40,
}


def has_minimum_role(actual: WorkspaceRole, required: WorkspaceRole) -> bool:
    return ROLE_RANK[actual] >= ROLE_RANK[required]


def can_manage_role(actor: WorkspaceRole, target: WorkspaceRole) -> bool:
    if target is WorkspaceRole.OWNER:
        return False
    if actor is WorkspaceRole.OWNER:
        return True
    if actor is WorkspaceRole.ADMIN:
        return target in {WorkspaceRole.AGENT, WorkspaceRole.VIEWER}
    return False


def role_is_allowed(actual: WorkspaceRole, allowed: Collection[WorkspaceRole]) -> bool:
    return actual in allowed
