"""manual publish tasks

Revision ID: 0006_publish_tasks
Revises: 0005_weknora_index_tables
Create Date: 2026-11-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_publish_tasks"
down_revision: str | None = "0005_weknora_index_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "publish_tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "kb_id",
            sa.String(length=36),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("git_commit", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "version_id",
            sa.String(length=36),
            sa.ForeignKey("weknora_index_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("doc_total", sa.Integer(), nullable=False),
        sa.Column("doc_completed", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(length=2048), nullable=True),
        sa.Column(
            "created_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_publish_tasks_kb_created", "publish_tasks", ["kb_id", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_publish_tasks_kb_created", table_name="publish_tasks")
    op.drop_table("publish_tasks")
