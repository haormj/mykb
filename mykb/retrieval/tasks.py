"""Manual publish task lifecycle and background worker."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from ..db.models import KnowledgeBase, PublishTask
from ..okf.bundle import Bundle
from .index import select_indexable_knowledge
from .publish import PublishError, SnapshotPublisher

QUEUED = "queued"
BUILDING = "building"
INDEXING = "indexing"
ACTIVATING = "activating"
READY = "ready"
FAILED = "failed"

ACTIVE_STATUSES = {QUEUED, BUILDING, INDEXING, ACTIVATING}

_ALLOWED: dict[str, set[str]] = {
    QUEUED: {BUILDING, FAILED},
    BUILDING: {INDEXING, ACTIVATING, READY, FAILED},
    INDEXING: {ACTIVATING, READY, FAILED},
    ACTIVATING: {READY, FAILED},
    READY: set(),
    FAILED: set(),
}


class InvalidTransition(RuntimeError):
    """Raised when a publish task moves between disallowed states."""


def advance(task: PublishTask, status: str) -> None:
    if status not in _ALLOWED.get(task.status, set()):
        raise InvalidTransition(
            f"cannot move publish task from {task.status} to {status}"
        )
    task.status = status


def _now() -> datetime:
    return datetime.now(UTC)


def task_payload(task: PublishTask) -> dict:
    return {
        "task_id": task.id,
        "kb_id": task.kb_id,
        "status": task.status,
        "git_commit": task.git_commit,
        "version_id": task.version_id,
        "doc_total": task.doc_total,
        "doc_completed": task.doc_completed,
        "error": task.error,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }


def _lock_for(kb_id: str, locks: dict[str, threading.Lock], guard: threading.Lock) -> threading.Lock:
    with guard:
        lock = locks.get(kb_id)
        if lock is None:
            lock = threading.Lock()
            locks[kb_id] = lock
        return lock


def run_publish_task(
    task_id: str,
    *,
    session_factory: sessionmaker[Session],
    backend,
    retention: int = 3,
    poll_interval: float = 1.0,
    max_polls: int = 120,
    sleep=None,
    locks: dict[str, threading.Lock] | None = None,
    lock_guard: threading.Lock | None = None,
) -> None:
    """Execute one publish task: materialize a snapshot and flip the pointer."""
    session = session_factory()
    try:
        task = session.get(PublishTask, task_id)
        if task is None:
            return
        kb = session.get(KnowledgeBase, task.kb_id)
        if kb is None:
            advance(task, FAILED)
            task.error = "knowledge base no longer exists"
            task.finished_at = _now()
            session.commit()
            return

        if locks is not None and lock_guard is not None:
            lock = _lock_for(kb.id, locks, lock_guard)
        else:
            lock = threading.Lock()
        with lock:
            session.refresh(task)
            if task.status != QUEUED:
                return
            advance(task, BUILDING)
            task.started_at = _now()
            session.commit()

            bundle = Bundle(Path(kb.local_path))
            concepts = select_indexable_knowledge(bundle)

            def on_phase(status: str) -> None:
                try:
                    advance(task, status)
                except InvalidTransition:
                    return
                session.commit()

            publisher = SnapshotPublisher(
                backend,
                retention=retention,
                max_polls=max_polls,
                poll_interval=poll_interval,
                sleep=sleep,
            )
            try:
                version = publisher.publish(
                    session,
                    kb_id=task.kb_id,
                    concepts=concepts,
                    git_commit=task.git_commit,
                    on_phase=on_phase,
                )
            except PublishError as exc:
                if task.status != FAILED:
                    advance(task, FAILED)
                task.error = str(exc)
                task.finished_at = _now()
                session.commit()
                return

            task.version_id = version.id
            task.doc_total = version.doc_total
            task.doc_completed = version.doc_completed
            if task.status != READY:
                advance(task, READY)
            task.finished_at = _now()
            session.commit()
    finally:
        session.close()
