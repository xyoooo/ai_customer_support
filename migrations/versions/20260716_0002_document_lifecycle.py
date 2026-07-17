"""Add tenant-safe documents, immutable versions, and durable jobs.

Revision ID: 20260716_0002
Revises: 20260713_0001
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260716_0002"
down_revision: str | None = "20260713_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    version_status = sa.Enum(
        "queued",
        "processing",
        "active",
        "failed",
        name="document_version_status",
        native_enum=False,
        create_constraint=True,
    )
    job_type = sa.Enum(
        "process_document",
        "delete_object",
        name="job_type",
        native_enum=False,
        create_constraint=True,
    )
    job_state = sa.Enum(
        "queued",
        "leased",
        "processing",
        "retrying",
        "failed",
        "dead_letter",
        "completed",
        name="job_state",
        native_enum=False,
        create_constraint=True,
    )

    op.create_table(
        "documents",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("active_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "char_length(display_name) >= 1",
            name=op.f("ck_documents_display_name_not_empty"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_documents_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_documents_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
    )
    op.create_index("ix_documents_workspace_created", "documents", ["workspace_id", "created_at"])

    op.create_table(
        "document_versions",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", version_status, server_default="queued", nullable=False),
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
        sa.CheckConstraint(
            "version_number > 0",
            name=op.f("ck_document_versions_version_number_positive"),
        ),
        sa.CheckConstraint(
            "byte_size >= 0", name=op.f("ck_document_versions_byte_size_nonnegative")
        ),
        sa.CheckConstraint(
            "char_length(sha256) = 64",
            name=op.f("ck_document_versions_sha256_length"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_document_versions_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_versions_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_document_versions_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_versions")),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_versions_document_version_number",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "document_id",
            "sha256",
            name="uq_document_versions_document_content",
        ),
        sa.UniqueConstraint("object_key", name=op.f("uq_document_versions_object_key")),
    )
    op.create_index(
        "ix_document_versions_workspace_document",
        "document_versions",
        ["workspace_id", "document_id"],
    )
    op.create_foreign_key(
        "fk_documents_active_version_id_document_versions",
        "documents",
        "document_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
        use_alter=True,
    )

    op.create_table(
        "jobs",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("job_type", job_type, nullable=False),
        sa.Column("payload_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", job_state, server_default="queued", nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.CheckConstraint("payload_version > 0", name=op.f("ck_jobs_payload_version_positive")),
        sa.CheckConstraint("attempt_count >= 0", name=op.f("ck_jobs_attempt_count_nonnegative")),
        sa.CheckConstraint("max_attempts > 0", name=op.f("ck_jobs_max_attempts_positive")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_jobs_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint(
            "workspace_id", "job_type", "idempotency_key", name="uq_jobs_job_idempotency"
        ),
    )
    op.create_index(
        "ix_jobs_workspace_state_available",
        "jobs",
        ["workspace_id", "state", "available_at"],
    )
    op.create_index("ix_jobs_claim", "jobs", ["state", "available_at", "lease_expires_at"])

    op.execute(
        """
        CREATE FUNCTION app_current_worker_id() RETURNS text
        LANGUAGE sql STABLE PARALLEL SAFE
        RETURN NULLIF(current_setting('app.current_worker_id', true), '')
        """
    )
    op.execute(
        """
        CREATE FUNCTION protect_document_version_immutability() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF (NEW.workspace_id, NEW.document_id, NEW.version_number, NEW.object_key,
                NEW.original_filename, NEW.media_type, NEW.byte_size, NEW.sha256, NEW.created_by)
               IS DISTINCT FROM
               (OLD.workspace_id, OLD.document_id, OLD.version_number, OLD.object_key,
                OLD.original_filename, OLD.media_type, OLD.byte_size, OLD.sha256, OLD.created_by)
            THEN
                RAISE EXCEPTION 'document version content metadata is immutable';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER document_versions_immutable
        BEFORE UPDATE ON document_versions
        FOR EACH ROW EXECUTE FUNCTION protect_document_version_immutability()
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_active_document_version() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.active_version_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM document_versions version
                WHERE version.id = NEW.active_version_id
                  AND version.document_id = NEW.id
                  AND version.workspace_id = NEW.workspace_id
                  AND version.status = 'active'
            ) THEN
                RAISE EXCEPTION 'active version must be an active version of this document';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER documents_active_version_valid
        BEFORE INSERT OR UPDATE OF active_version_id ON documents
        FOR EACH ROW EXECUTE FUNCTION validate_active_document_version()
        """
    )

    for table in ("documents", "document_versions", "jobs"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    for table in ("documents", "document_versions"):
        op.execute(
            f"""
            CREATE POLICY {table}_select ON {table} FOR SELECT
            USING (workspace_id = app_current_workspace_id())
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_insert ON {table} FOR INSERT
            WITH CHECK (workspace_id = app_current_workspace_id())
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_update ON {table} FOR UPDATE
            USING (workspace_id = app_current_workspace_id())
            WITH CHECK (workspace_id = app_current_workspace_id())
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_delete ON {table} FOR DELETE
            USING (workspace_id = app_current_workspace_id())
            """
        )

    op.execute(
        """
        CREATE POLICY jobs_select ON jobs FOR SELECT
        USING (
            workspace_id = app_current_workspace_id()
            OR app_current_worker_id() IS NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE POLICY jobs_insert ON jobs FOR INSERT
        WITH CHECK (workspace_id = app_current_workspace_id())
        """
    )
    op.execute(
        """
        CREATE POLICY jobs_update ON jobs FOR UPDATE
        USING (
            workspace_id = app_current_workspace_id()
            OR app_current_worker_id() IS NOT NULL
        )
        WITH CHECK (
            workspace_id = app_current_workspace_id()
            OR app_current_worker_id() IS NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE POLICY jobs_delete ON jobs FOR DELETE
        USING (
            workspace_id = app_current_workspace_id()
            OR app_current_worker_id() IS NOT NULL
        )
        """
    )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON documents, document_versions, jobs "
        "TO supportpilot_app"
    )
    op.execute("GRANT EXECUTE ON FUNCTION app_current_worker_id() TO supportpilot_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS jobs_delete ON jobs")
    op.execute("DROP POLICY IF EXISTS jobs_update ON jobs")
    op.execute("DROP POLICY IF EXISTS jobs_insert ON jobs")
    op.execute("DROP POLICY IF EXISTS jobs_select ON jobs")
    for table in ("document_versions", "documents"):
        op.execute(f"DROP POLICY IF EXISTS {table}_delete ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_update ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_select ON {table}")
    op.execute("DROP TRIGGER IF EXISTS documents_active_version_valid ON documents")
    op.execute("DROP FUNCTION IF EXISTS validate_active_document_version()")
    op.execute("DROP TRIGGER IF EXISTS document_versions_immutable ON document_versions")
    op.execute("DROP FUNCTION IF EXISTS protect_document_version_immutability()")
    op.execute("DROP FUNCTION IF EXISTS app_current_worker_id()")
    op.drop_table("jobs")
    op.drop_constraint(
        "fk_documents_active_version_id_document_versions", "documents", type_="foreignkey"
    )
    op.drop_table("document_versions")
    op.drop_table("documents")
