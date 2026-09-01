"""Add isolated RAG strategy lab storage.

Revision ID: 20260722_0003
Revises: 20260716_0002
Create Date: 2026-07-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260722_0003"
down_revision: str | None = "20260716_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE rag_lab_chunks (
            workspace_id uuid NOT NULL,
            profile_fingerprint varchar(64) NOT NULL,
            chunk_id varchar(64) NOT NULL,
            document_id uuid NOT NULL,
            version_id uuid NOT NULL,
            chunk_order integer NOT NULL,
            original_text text NOT NULL,
            embedding_text text NOT NULL,
            token_count integer NOT NULL,
            locators jsonb NOT NULL,
            heading_path jsonb NOT NULL,
            page_number integer,
            embedding vector NOT NULL,
            embedding_dimension integer NOT NULL,
            active boolean NOT NULL DEFAULT true,
            search_vector tsvector GENERATED ALWAYS AS (
                to_tsvector('english'::regconfig, original_text)
            ) STORED,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_rag_lab_chunks PRIMARY KEY (
                workspace_id, profile_fingerprint, chunk_id
            ),
            CONSTRAINT fk_rag_lab_chunks_workspace
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
            CONSTRAINT fk_rag_lab_chunks_document
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
            CONSTRAINT fk_rag_lab_chunks_version
                FOREIGN KEY (version_id) REFERENCES document_versions(id) ON DELETE CASCADE,
            CONSTRAINT ck_rag_lab_profile_fingerprint_length
                CHECK (char_length(profile_fingerprint) = 64),
            CONSTRAINT ck_rag_lab_chunk_id_length CHECK (char_length(chunk_id) = 64),
            CONSTRAINT ck_rag_lab_chunk_order_nonnegative CHECK (chunk_order >= 0),
            CONSTRAINT ck_rag_lab_original_text_nonempty CHECK (length(original_text) > 0),
            CONSTRAINT ck_rag_lab_embedding_text_nonempty CHECK (length(embedding_text) > 0),
            CONSTRAINT ck_rag_lab_token_count_positive CHECK (token_count > 0),
            CONSTRAINT ck_rag_lab_embedding_dimension_positive CHECK (embedding_dimension > 0),
            CONSTRAINT ck_rag_lab_page_number_positive
                CHECK (page_number IS NULL OR page_number > 0)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_rag_lab_chunks_scope
        ON rag_lab_chunks (workspace_id, profile_fingerprint, active)
        """
    )
    op.execute("CREATE INDEX ix_rag_lab_chunks_search ON rag_lab_chunks USING gin (search_vector)")
    op.execute("ALTER TABLE rag_lab_chunks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rag_lab_chunks FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY rag_lab_chunks_select ON rag_lab_chunks FOR SELECT
        USING (workspace_id = app_current_workspace_id())
        """
    )
    op.execute(
        """
        CREATE POLICY rag_lab_chunks_insert ON rag_lab_chunks FOR INSERT
        WITH CHECK (workspace_id = app_current_workspace_id())
        """
    )
    op.execute(
        """
        CREATE POLICY rag_lab_chunks_update ON rag_lab_chunks FOR UPDATE
        USING (workspace_id = app_current_workspace_id())
        WITH CHECK (workspace_id = app_current_workspace_id())
        """
    )
    op.execute(
        """
        CREATE POLICY rag_lab_chunks_delete ON rag_lab_chunks FOR DELETE
        USING (workspace_id = app_current_workspace_id())
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON rag_lab_chunks TO supportpilot_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS rag_lab_chunks_delete ON rag_lab_chunks")
    op.execute("DROP POLICY IF EXISTS rag_lab_chunks_update ON rag_lab_chunks")
    op.execute("DROP POLICY IF EXISTS rag_lab_chunks_insert ON rag_lab_chunks")
    op.execute("DROP POLICY IF EXISTS rag_lab_chunks_select ON rag_lab_chunks")
    op.execute("DROP TABLE rag_lab_chunks")
