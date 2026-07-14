import pytest

from packages.domain.enums import WorkspaceRole
from packages.security.rbac import can_manage_role, has_minimum_role


@pytest.mark.parametrize(
    ("actor", "target", "expected"),
    [
        (WorkspaceRole.OWNER, WorkspaceRole.ADMIN, True),
        (WorkspaceRole.OWNER, WorkspaceRole.AGENT, True),
        (WorkspaceRole.OWNER, WorkspaceRole.VIEWER, True),
        (WorkspaceRole.OWNER, WorkspaceRole.OWNER, False),
        (WorkspaceRole.ADMIN, WorkspaceRole.ADMIN, False),
        (WorkspaceRole.ADMIN, WorkspaceRole.AGENT, True),
        (WorkspaceRole.ADMIN, WorkspaceRole.VIEWER, True),
        (WorkspaceRole.AGENT, WorkspaceRole.VIEWER, False),
        (WorkspaceRole.VIEWER, WorkspaceRole.VIEWER, False),
    ],
)
def test_role_management_matrix(
    actor: WorkspaceRole,
    target: WorkspaceRole,
    expected: bool,
) -> None:
    assert can_manage_role(actor, target) is expected


@pytest.mark.parametrize("role", list(WorkspaceRole))
def test_every_role_meets_its_own_minimum(role: WorkspaceRole) -> None:
    assert has_minimum_role(role, role)


def test_viewer_does_not_meet_agent_minimum() -> None:
    assert not has_minimum_role(WorkspaceRole.VIEWER, WorkspaceRole.AGENT)
