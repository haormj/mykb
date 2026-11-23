"""platform-level evaluation tables

Revision ID: 0004_evaluation_tables
Revises: 0003_extraction_items
Create Date: 2026-11-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_evaluation_tables"
down_revision: str | None = "0003_extraction_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eval_sets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("description", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "eval_cases",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "set_id",
            sa.String(length=36),
            sa.ForeignKey("eval_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("reference_answer", sa.Text(), nullable=False),
        sa.Column("expected_concept", sa.String(length=1024), nullable=True),
        sa.Column("domain", sa.String(length=128), nullable=True),
        sa.Column("difficulty", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_eval_cases_set_position", "eval_cases", ["set_id", "position"], unique=False
    )
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "set_id",
            sa.String(length=36),
            sa.ForeignKey("eval_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_kb_id",
            sa.String(length=36),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "triggered_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("knowledge_version", sa.String(length=128), nullable=True),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("coverage", sa.Float(), nullable=False),
        sa.Column("a_score", sa.Float(), nullable=False),
        sa.Column("b_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_eval_runs_kb_created", "eval_runs", ["target_kb_id", "created_at"], unique=False
    )
    op.create_index(
        "ix_eval_runs_set_created", "eval_runs", ["set_id", "created_at"], unique=False
    )
    op.create_table(
        "eval_case_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("eval_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            sa.String(length=36),
            sa.ForeignKey("eval_cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_concept", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("a_score", sa.Float(), nullable=False),
        sa.Column("b_answer", sa.Text(), nullable=False),
        sa.Column("b_score", sa.Float(), nullable=False),
    )
    op.create_index(
        "ix_eval_case_results_run", "eval_case_results", ["run_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_eval_case_results_run", table_name="eval_case_results")
    op.drop_table("eval_case_results")
    op.drop_index("ix_eval_runs_set_created", table_name="eval_runs")
    op.drop_index("ix_eval_runs_kb_created", table_name="eval_runs")
    op.drop_table("eval_runs")
    op.drop_index("ix_eval_cases_set_position", table_name="eval_cases")
    op.drop_table("eval_cases")
    op.drop_table("eval_sets")
