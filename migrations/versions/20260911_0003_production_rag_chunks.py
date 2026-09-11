"""Add tenant-safe storage for the selected production RAG pipeline.

Revision ID: 20260911_0003
Revises: 20260716_0002
Create Date: 2026-09-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260911_0003"
down_revision: str | None = "20260716_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE document_chunks (
            chunk_id varchar(64) PRIMARY KEY,
            workspace_id uuid NOT NULL,
            document_id uuid NOT NULL,
            version_id uuid NOT NULL,
            pipeline_version varchar(64) NOT NULL,
            chunk_order integer NOT NULL,
            original_text text NOT NULL,
            token_count integer NOT NULL,
            locators jsonb NOT NULL,
            heading_path jsonb NOT NULL,
            page_number integer,
            document_title varchar(255) NOT NULL,
            embedding vector(384) NOT NULL,
            search_vector tsvector GENERATED ALWAYS AS (
                to_tsvector(
                    'english'::regconfig,
                    coalesce(document_title, '') || ' ' || original_text
                )
            ) STORED,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_document_chunks_workspace
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
            CONSTRAINT fk_document_chunks_document
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
            CONSTRAINT fk_document_chunks_version
                FOREIGN KEY (version_id) REFERENCES document_versions(id) ON DELETE CASCADE,
            CONSTRAINT uq_document_chunks_version_order
                UNIQUE (version_id, pipeline_version, chunk_order),
            CONSTRAINT ck_document_chunks_chunk_id CHECK (char_length(chunk_id) = 64),
            CONSTRAINT ck_document_chunks_pipeline
                CHECK (pipeline_version = 'rag-v1-c1-e1'),
            CONSTRAINT ck_document_chunks_order CHECK (chunk_order >= 0),
            CONSTRAINT ck_document_chunks_text CHECK (length(original_text) > 0),
            CONSTRAINT ck_document_chunks_tokens CHECK (token_count > 0),
            CONSTRAINT ck_document_chunks_page CHECK (page_number IS NULL OR page_number > 0)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_document_chunks_workspace_version
        ON document_chunks (workspace_id, version_id, pipeline_version, chunk_order)
        """
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_search ON document_chunks USING gin (search_vector)"
    )
    op.execute(
        """
        CREATE FUNCTION validate_document_chunk_scope() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM document_versions version_row
                JOIN documents document_row ON document_row.id = version_row.document_id
                WHERE version_row.id = NEW.version_id
                  AND version_row.document_id = NEW.document_id
                  AND version_row.workspace_id = NEW.workspace_id
                  AND document_row.workspace_id = NEW.workspace_id
            ) THEN
                RAISE EXCEPTION 'document chunk scope does not match its document version';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER document_chunks_validate_scope
        BEFORE INSERT OR UPDATE ON document_chunks
        FOR EACH ROW EXECUTE FUNCTION validate_document_chunk_scope()
        """
    )
    op.execute("ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_chunks FORCE ROW LEVEL SECURITY")
    for operation in ("SELECT", "UPDATE", "DELETE"):
        op.execute(
            f"""
            CREATE POLICY document_chunks_{operation.lower()} ON document_chunks
            FOR {operation}
            USING (workspace_id = app_current_workspace_id())
            """
        )
    op.execute(
        """
        CREATE POLICY document_chunks_insert ON document_chunks FOR INSERT
        WITH CHECK (workspace_id = app_current_workspace_id())
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON document_chunks TO supportpilot_app")


def downgrade() -> None:
    for operation in ("insert", "delete", "update", "select"):
        op.execute(f"DROP POLICY IF EXISTS document_chunks_{operation} ON document_chunks")
    op.execute("DROP TABLE document_chunks")
    op.execute("DROP FUNCTION validate_document_chunk_scope()")
