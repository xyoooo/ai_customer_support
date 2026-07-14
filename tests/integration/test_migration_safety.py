from __future__ import annotations

from uuid import UUID

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

pytestmark = [pytest.mark.integration, pytest.mark.security]

MIGRATION_URL = (
    "postgresql://supportpilot_migrator:local_migrator_password@localhost:5432/supportpilot_test"
)
FOUNDATION_REVISION = "20260713_0001"
USER_ID = UUID("00000000-0000-0000-0000-000000000101")
WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000102")
MEMBERSHIP_ID = UUID("00000000-0000-0000-0000-000000000103")


def seed_foundation_data() -> None:
    with psycopg.connect(MIGRATION_URL) as connection:
        connection.execute(
            """
            INSERT INTO users (id, email, display_name, password_hash)
            VALUES (%s, 'migration-owner@example.com', 'Migration Owner', 'not-used')
            """,
            (USER_ID,),
        )
        connection.execute(
            "SELECT set_config('app.current_user_id', %s, true)",
            (str(USER_ID),),
        )
        connection.execute(
            "SELECT set_config('app.current_workspace_id', %s, true)",
            (str(WORKSPACE_ID),),
        )
        connection.execute(
            """
            INSERT INTO workspaces (id, name, slug, created_by)
            VALUES (%s, 'Migration Workspace', 'migration-workspace', %s)
            """,
            (WORKSPACE_ID, USER_ID),
        )
        connection.execute(
            """
            INSERT INTO workspace_memberships (id, workspace_id, user_id, role)
            VALUES (%s, %s, %s, 'owner')
            """,
            (MEMBERSHIP_ID, WORKSPACE_ID, USER_ID),
        )


def assert_foundation_data_is_intact() -> None:
    with psycopg.connect(MIGRATION_URL) as connection:
        connection.execute(
            "SELECT set_config('app.current_user_id', %s, true)",
            (str(USER_ID),),
        )
        connection.execute(
            "SELECT set_config('app.current_workspace_id', %s, true)",
            (str(WORKSPACE_ID),),
        )
        user = connection.execute("SELECT email FROM users WHERE id = %s", (USER_ID,)).fetchone()
        workspace = connection.execute(
            "SELECT slug, created_by FROM workspaces WHERE id = %s", (WORKSPACE_ID,)
        ).fetchone()
        membership = connection.execute(
            """
            SELECT role FROM workspace_memberships
            WHERE id = %s AND workspace_id = %s AND user_id = %s
            """,
            (MEMBERSHIP_ID, WORKSPACE_ID, USER_ID),
        ).fetchone()
    assert user == ("migration-owner@example.com",)
    assert workspace == ("migration-workspace", USER_ID)
    assert membership == ("owner",)


def test_every_post_foundation_migration_preserves_existing_data(
    migrated_database: None,
) -> None:
    del migrated_database
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    revisions = list(reversed(list(script.walk_revisions(base="base", head="heads"))))

    command.downgrade(config, "base")
    seeded = False
    for revision in revisions:
        command.upgrade(config, revision.revision)
        if revision.revision == FOUNDATION_REVISION:
            seed_foundation_data()
            seeded = True
        if seeded:
            assert_foundation_data_is_intact()

    assert seeded, "the foundation migration must remain in Alembic history"
    command.upgrade(config, "heads")
    assert_foundation_data_is_intact()


def test_tenant_tables_have_forced_rls_and_least_privilege(
    migrated_database: None,
) -> None:
    del migrated_database
    with psycopg.connect(MIGRATION_URL) as connection:
        discovered = {
            row[0]
            for row in connection.execute(
                """
                SELECT table_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND column_name = 'workspace_id'
                """
            ).fetchall()
        }
        tenant_tables = discovered | {"workspaces"}
        assert tenant_tables >= {"workspaces", "workspace_memberships"}

        role = connection.execute(
            """
            SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls
            FROM pg_roles WHERE rolname = 'supportpilot_app'
            """
        ).fetchone()
        assert role == (False, False, False, False)
        assert connection.execute(
            "SELECT has_schema_privilege('supportpilot_app', 'public', 'CREATE')"
        ).fetchone() == (False,)

        for table in sorted(tenant_tables):
            security = connection.execute(
                """
                SELECT c.relrowsecurity, c.relforcerowsecurity, pg_get_userbyid(c.relowner)
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relname = %s
                """,
                (table,),
            ).fetchone()
            assert security is not None
            assert security[:2] == (True, True), f"{table} must enable and force RLS"
            assert security[2] != "supportpilot_app", f"{table} cannot be owned by the runtime role"

            policies = connection.execute(
                """
                SELECT cmd, COALESCE(qual, '') || ' ' || COALESCE(with_check, '')
                FROM pg_policies
                WHERE schemaname = 'public' AND tablename = %s
                """,
                (table,),
            ).fetchall()
            assert policies, f"{table} must define explicit RLS policies"
            assert any(command_name == "SELECT" for command_name, _ in policies)
            assert all("app_current_" in expression for _, expression in policies)

            allowed = connection.execute(
                """
                SELECT
                    has_table_privilege('supportpilot_app', %s, 'SELECT'),
                    has_table_privilege('supportpilot_app', %s, 'INSERT'),
                    has_table_privilege('supportpilot_app', %s, 'UPDATE'),
                    has_table_privilege('supportpilot_app', %s, 'DELETE')
                """,
                (table, table, table, table),
            ).fetchone()
            dangerous = connection.execute(
                """
                SELECT
                    has_table_privilege('supportpilot_app', %s, 'TRUNCATE'),
                    has_table_privilege('supportpilot_app', %s, 'REFERENCES'),
                    has_table_privilege('supportpilot_app', %s, 'TRIGGER')
                """,
                (table, table, table),
            ).fetchone()
            assert allowed == (True, True, True, True)
            assert dangerous == (False, False, False)

        for table in sorted(discovered):
            workspace_column = connection.execute(
                """
                SELECT is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s AND column_name = 'workspace_id'
                """,
                (table,),
            ).fetchone()
            assert workspace_column == ("NO",), f"{table}.workspace_id must be required"

            has_workspace_fk = connection.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_constraint constraint_row
                    JOIN pg_class source_table ON source_table.oid = constraint_row.conrelid
                    JOIN pg_class target_table ON target_table.oid = constraint_row.confrelid
                    WHERE constraint_row.contype = 'f'
                      AND source_table.relname = %s
                      AND target_table.relname = 'workspaces'
                      AND starts_with(
                          pg_get_constraintdef(constraint_row.oid),
                          'FOREIGN KEY (workspace_id)'
                      )
                )
                """,
                (table,),
            ).fetchone()
            assert has_workspace_fk == (True,), f"{table}.workspace_id must reference workspaces"

            has_workspace_index = connection.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND tablename = %s
                      AND indexdef ~ '\\(workspace_id([, )])'
                )
                """,
                (table,),
            ).fetchone()
            assert has_workspace_index == (True,), f"{table}.workspace_id must be indexed"
