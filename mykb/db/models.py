"""Platform metadata models.

Content (documents and business knowledge) lives in git-backed OKF bundles.
These tables hold only platform data: accounts, roles, tokens, knowledge-base
registration and membership.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("sso_provider", "sso_user_id", name="uq_users_sso"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sso_provider: Mapped[str | None] = mapped_column(String(64))
    sso_user_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    permissions: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id", ondelete="CASCADE"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserToken(Base):
    __tablename__ = "user_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    git_url: Mapped[str | None] = mapped_column(String(1024))
    git_branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)
    local_path: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    git_credential_enc: Mapped[str | None] = mapped_column(String(2048))
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class KbMember(Base):
    __tablename__ = "kb_members"

    kb_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ImportTask(Base):
    __tablename__ = "import_tasks"
    __table_args__ = (Index("ix_import_tasks_kb_created", "kb_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kb_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), default="upload", nullable=False)
    source_config: Mapped[dict[str, Any]] = mapped_column(
        JSONType, default=dict, nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(String(2048))
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExtractionItem(Base):
    """One source document waiting for review as a document-level change set."""

    __tablename__ = "extraction_items"
    __table_args__ = (Index("ix_extraction_items_kb_status", "kb_id", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kb_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    import_task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("import_tasks.id", ondelete="CASCADE")
    )
    concept_id: Mapped[str] = mapped_column(String(1024), nullable=False)
    action: Mapped[str] = mapped_column(String(16), default="add", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    branch: Mapped[str | None] = mapped_column(String(255))
    source_hash: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(512))
    error: Mapped[str | None] = mapped_column(String(2048))
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class EvalSet(Base):
    """A platform-level, reusable evaluation set owned by a single user."""

    __tablename__ = "eval_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    cases: Mapped[list[EvalCase]] = relationship(
        back_populates="eval_set",
        cascade="all, delete-orphan",
        order_by="EvalCase.position",
    )


class EvalCase(Base):
    """One question inside an :class:`EvalSet`."""

    __tablename__ = "eval_cases"
    __table_args__ = (Index("ix_eval_cases_set_position", "set_id", "position"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_sets.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    reference_answer: Mapped[str] = mapped_column(Text, nullable=False)
    expected_concept: Mapped[str | None] = mapped_column(String(1024))
    domain: Mapped[str | None] = mapped_column(String(128))
    difficulty: Mapped[str | None] = mapped_column(String(64))

    eval_set: Mapped[EvalSet] = relationship(back_populates="cases")


class EvalRun(Base):
    """One run of an eval set against a single target knowledge base."""

    __tablename__ = "eval_runs"
    __table_args__ = (
        Index("ix_eval_runs_kb_created", "target_kb_id", "created_at"),
        Index("ix_eval_runs_set_created", "set_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_sets.id", ondelete="CASCADE"), nullable=False
    )
    target_kb_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    triggered_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    knowledge_version: Mapped[str | None] = mapped_column(String(128))
    case_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coverage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    a_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    b_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EvalCaseResult(Base):
    """Per-question snapshot of an :class:`EvalRun`.

    Question text is snapshotted so editing the set later never rewrites the
    meaning of a historical run.
    """

    __tablename__ = "eval_case_results"
    __table_args__ = (Index("ix_eval_case_results_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("eval_cases.id", ondelete="SET NULL")
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_concept: Mapped[str | None] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    a_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    b_answer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    b_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
