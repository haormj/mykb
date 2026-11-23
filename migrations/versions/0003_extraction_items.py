"""pending extraction review queue

Revision ID: 0003_extraction_items
Revises: 0002_import_tasks
Create Date: 2026-11-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_extraction_items"
down_revision: str | None = "0002_import_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("import_tasks") as batch:
        batch.alter_column(
            "status",
            existing_type=sa.String(length=16),
            type_=sa.String(length=32),
            existing_nullable=False,
        )
    op.create_table(
        "extraction_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "kb_id",
            sa.String(length=36),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "import_task_id",
            sa.String(length=36),
            sa.ForeignKey("import_tasks.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("concept_id", sa.String(length=1024), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("error", sa.String(length=2048), nullable=True),
        sa.Column(
            "created_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_extraction_items_kb_status",
        "extraction_items",
        ["kb_id", "status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_extraction_items_kb_status", table_name="extraction_items")
    op.drop_table("extraction_items")
    with op.batch_alter_table("import_tasks") as batch:
        batch.alter_column(
            "status",
            existing_type=sa.String(length=32),
            type_=sa.String(length=16),
            existing_nullable=False,
        )
