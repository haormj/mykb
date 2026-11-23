"""Durable pending-review queue and task lifecycle for document extraction."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import ExtractionItem, ImportTask

ACTION_ADD = "add"
ACTION_MODIFY = "modify"
ACTION_DELETE = "delete"

STATUS_QUEUED = "queued"
STATUS_PROCESSING = "processing"
STATUS_QUEUED_FOR_REVIEW = "queued-for-review"
STATUS_REVIEWING = "reviewing"
STATUS_MERGED = "merged"
STATUS_REJECTED = "rejected"
STATUS_FAILED = "failed"

TERMINAL_ITEM_STATUSES = {STATUS_MERGED, STATUS_REJECTED, STATUS_FAILED}

# Import task aggregate statuses.
TASK_CONVERTING = "converting"
TASK_QUEUED_FOR_REVIEW = "queued-for-review"
TASK_REVIEWING = "reviewing"
TASK_MERGED = "merged"
TASK_REJECTED = "rejected"


def _now() -> datetime:
    return datetime.now(UTC)


def enqueue_item(
    session: Session,
    *,
    kb_id: str,
    import_task_id: str | None,
    concept_id: str,
    action: str,
    source_hash: str | None,
    title: str | None,
    created_by: str | None,
) -> ExtractionItem:
    item = ExtractionItem(
        kb_id=kb_id,
        import_task_id=import_task_id,
        concept_id=concept_id,
        action=action,
        status=STATUS_QUEUED,
        source_hash=source_hash,
        title=title,
        created_by=created_by,
    )
    session.add(item)
    session.flush()
    return item


def has_open_review(session: Session, kb_id: str) -> bool:
    """Return whether a document MR is already awaiting review for this KB."""
    return (
        session.scalar(
            select(ExtractionItem.id)
            .where(ExtractionItem.kb_id == kb_id)
            .where(
                ExtractionItem.status.in_(
                    (STATUS_PROCESSING, STATUS_QUEUED_FOR_REVIEW, STATUS_REVIEWING)
                )
            )
            .limit(1)
        )
        is not None
    )


def claim_next(session: Session, kb_id: str) -> ExtractionItem | None:
    """Claim the oldest queued item for a KB (single-flight is enforced by caller)."""
    item = session.scalar(
        select(ExtractionItem)
        .where(ExtractionItem.kb_id == kb_id)
        .where(ExtractionItem.status == STATUS_QUEUED)
        .order_by(ExtractionItem.created_at)
        .limit(1)
    )
    if item is None:
        return None
    item.status = STATUS_PROCESSING
    item.updated_at = _now()
    session.commit()
    return item


def mark_item(
    session: Session,
    item: ExtractionItem,
    status: str,
    *,
    branch: str | None = None,
    error: str | None = None,
) -> None:
    item.status = status
    if branch is not None:
        item.branch = branch
    item.error = error
    item.updated_at = _now()
    session.commit()


def recover_processing(session_factory: sessionmaker[Session]) -> int:
    """Reset items interrupted mid-processing so they can be retried."""
    with session_factory() as session:
        items = session.scalars(
            select(ExtractionItem).where(ExtractionItem.status == STATUS_PROCESSING)
        ).all()
        for item in items:
            item.status = STATUS_QUEUED
            item.updated_at = _now()
        session.commit()
        return len(items)


def items_for_task(session: Session, task_id: str) -> list[ExtractionItem]:
    return list(
        session.scalars(
            select(ExtractionItem)
            .where(ExtractionItem.import_task_id == task_id)
            .order_by(ExtractionItem.created_at)
        ).all()
    )


def refresh_import_task_status(session: Session, task_id: str | None) -> None:
    """Aggregate item statuses back onto the import task."""
    if not task_id:
        return
    task = session.get(ImportTask, task_id)
    if task is None or task.status in ("failed", "cancelled"):
        return
    items = items_for_task(session, task_id)
    if not items:
        return
    statuses = {item.status for item in items}
    if statuses & {STATUS_REVIEWING, STATUS_QUEUED_FOR_REVIEW, STATUS_PROCESSING}:
        task.status = TASK_REVIEWING if STATUS_REVIEWING in statuses else TASK_QUEUED_FOR_REVIEW
    elif STATUS_QUEUED in statuses:
        task.status = TASK_QUEUED_FOR_REVIEW
    elif statuses <= {STATUS_MERGED}:
        task.status = TASK_MERGED
    elif statuses <= {STATUS_REJECTED}:
        task.status = TASK_REJECTED
    elif statuses <= TERMINAL_ITEM_STATUSES and STATUS_MERGED in statuses:
        task.status = TASK_MERGED
    session.commit()
