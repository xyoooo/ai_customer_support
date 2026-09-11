"""Store document titles for deterministic structural lexical scoring.

Revision ID: 20260910_0004
Revises: 20260722_0003
Create Date: 2026-09-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260910_0004"
down_revision: str | None = "20260722_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE rag_lab_chunks ADD COLUMN document_title text NOT NULL DEFAULT ''")


def downgrade() -> None:
    op.execute("ALTER TABLE rag_lab_chunks DROP COLUMN document_title")
