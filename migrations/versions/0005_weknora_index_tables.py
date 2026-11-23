"""weknora snapshot index tables

Revision ID: 0005_weknora_index_tables
Revises: 0004_evaluation_tables
Create Date: 2026-11-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_weknora_index_tables"
down_revision: str | None = "0004_evaluation_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "weknora_index_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "kb_id",
            sa.String(length=36),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("git_commit", sa.String(length=255), nullable=False),
        sa.Column("weknora_kb_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("doc_total", sa.Integer(), nullable=False),
        sa.Column("doc_completed", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "kb_id", "git_commit", name="uq_weknora_versions_kb_commit"
        ),
        sa.UniqueConstraint("weknora_kb_id", name="uq_weknora_versions_kb"),
    )
    op.create_index(
        "ix_weknora_versions_kb_status",
        "weknora_index_versions",
        ["kb_id", "status"],
        unique=False,
    )
    op.create_table(
        "weknora_concept_map",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "version_id",
            sa.String(length=36),
            sa.ForeignKey("weknora_index_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("concept_id", sa.String(length=1024), nullable=False),
        sa.Column("doc_ref", sa.String(length=1024), nullable=False),
        sa.UniqueConstraint(
            "version_id", "concept_id", name="uq_weknora_concept_version_concept"
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("active_weknora_version_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_knowledge_bases_active_weknora_version_id",
        "knowledge_bases",
        ["active_weknora_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_bases_active_weknora_version_id",
        table_name="knowledge_bases",
    )
    op.drop_column("knowledge_bases", "active_weknora_version_id")
    op.drop_table("weknora_concept_map")
    op.drop_index(
        "ix_weknora_versions_kb_status", table_name="weknora_index_versions"
    )
    op.drop_table("weknora_index_versions")
