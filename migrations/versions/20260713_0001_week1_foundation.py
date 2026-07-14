"""Create Week 1 identity, workspace, and session foundation.

Revision ID: 20260713_0001
Revises: None
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260713_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "workspaces",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("char_length(name) >= 2", name=op.f("ck_workspaces_name_min_length")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_workspaces_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspaces")),
    )
    op.create_index(op.f("ix_workspaces_slug"), "workspaces", ["slug"], unique=True)

    role_enum = sa.Enum(
        "owner",
        "admin",
        "agent",
        "viewer",
        name="workspace_role",
        native_enum=False,
        create_constraint=True,
    )
    op.create_table(
        "workspace_memberships",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", role_enum, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_workspace_memberships_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_workspace_memberships_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_memberships")),
        sa.UniqueConstraint(
            "workspace_id", "user_id", name="uq_workspace_memberships_workspace_user"
        ),
    )
    op.create_index(op.f("ix_workspace_memberships_user_id"), "workspace_memberships", ["user_id"])
    op.create_index(
        "ix_workspace_memberships_user_workspace",
        "workspace_memberships",
        ["user_id", "workspace_id"],
    )
    op.create_index(
        op.f("ix_workspace_memberships_workspace_id"), "workspace_memberships", ["workspace_id"]
    )

    op.create_table(
        "refresh_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["refresh_sessions.id"],
            name=op.f("fk_refresh_sessions_replaced_by_id_refresh_sessions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_sessions_token_hash")),
    )
    op.create_index(op.f("ix_refresh_sessions_expires_at"), "refresh_sessions", ["expires_at"])
    op.create_index(op.f("ix_refresh_sessions_user_id"), "refresh_sessions", ["user_id"])
    op.create_index("ix_refresh_sessions_user_family", "refresh_sessions", ["user_id", "family_id"])

    op.execute(
        """
        CREATE FUNCTION app_current_user_id() RETURNS uuid
        LANGUAGE sql STABLE PARALLEL SAFE
        RETURN NULLIF(current_setting('app.current_user_id', true), '')::uuid
        """
    )
    op.execute(
        """
        CREATE FUNCTION app_current_workspace_id() RETURNS uuid
        LANGUAGE sql STABLE PARALLEL SAFE
        RETURN NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
        """
    )

    op.execute("ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspaces FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace_memberships ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace_memberships FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE POLICY workspaces_select ON workspaces FOR SELECT
        USING (
            id = app_current_workspace_id()
            OR EXISTS (
                SELECT 1 FROM workspace_memberships membership
                WHERE membership.workspace_id = workspaces.id
                  AND membership.user_id = app_current_user_id()
            )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY workspaces_insert ON workspaces FOR INSERT
        WITH CHECK (id = app_current_workspace_id() AND created_by = app_current_user_id())
        """
    )
    op.execute(
        """
        CREATE POLICY workspaces_update ON workspaces FOR UPDATE
        USING (id = app_current_workspace_id())
        WITH CHECK (id = app_current_workspace_id())
        """
    )
    op.execute(
        """
        CREATE POLICY workspaces_delete ON workspaces FOR DELETE
        USING (id = app_current_workspace_id())
        """
    )
    op.execute(
        """
        CREATE POLICY memberships_select ON workspace_memberships FOR SELECT
        USING (workspace_id = app_current_workspace_id() OR user_id = app_current_user_id())
        """
    )
    op.execute(
        """
        CREATE POLICY memberships_insert ON workspace_memberships FOR INSERT
        WITH CHECK (workspace_id = app_current_workspace_id())
        """
    )
    op.execute(
        """
        CREATE POLICY memberships_update ON workspace_memberships FOR UPDATE
        USING (workspace_id = app_current_workspace_id())
        WITH CHECK (workspace_id = app_current_workspace_id())
        """
    )
    op.execute(
        """
        CREATE POLICY memberships_delete ON workspace_memberships FOR DELETE
        USING (workspace_id = app_current_workspace_id())
        """
    )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO supportpilot_app"
    )
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO supportpilot_app")
    op.execute("GRANT EXECUTE ON FUNCTION app_current_user_id() TO supportpilot_app")
    op.execute("GRANT EXECUTE ON FUNCTION app_current_workspace_id() TO supportpilot_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS memberships_delete ON workspace_memberships")
    op.execute("DROP POLICY IF EXISTS memberships_update ON workspace_memberships")
    op.execute("DROP POLICY IF EXISTS memberships_insert ON workspace_memberships")
    op.execute("DROP POLICY IF EXISTS memberships_select ON workspace_memberships")
    op.execute("DROP POLICY IF EXISTS workspaces_delete ON workspaces")
    op.execute("DROP POLICY IF EXISTS workspaces_update ON workspaces")
    op.execute("DROP POLICY IF EXISTS workspaces_insert ON workspaces")
    op.execute("DROP POLICY IF EXISTS workspaces_select ON workspaces")
    op.execute("DROP FUNCTION IF EXISTS app_current_workspace_id()")
    op.execute("DROP FUNCTION IF EXISTS app_current_user_id()")
    op.drop_table("refresh_sessions")
    op.drop_table("workspace_memberships")
    op.drop_table("workspaces")
    op.drop_table("users")
