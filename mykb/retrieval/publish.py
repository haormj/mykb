"""Platform-owned snapshot orchestration: versioning, pointer, mapping, retention."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import KnowledgeBase, WeKnoraConceptMap, WeKnoraIndexVersion
from ..okf.model import Concept
from .backend import (
    BUILDING,
    FAILED,
    READY,
    BuildProgress,
    RetrievalBackend,
    SnapshotRef,
)

RETIRED = "retired"


class PublishError(RuntimeError):
    """Raised when a snapshot cannot be materialized or activated."""


def _now() -> datetime:
    return datetime.now(UTC)


class ActiveResolver:
    """Resolve and move the active snapshot pointer of a knowledge base."""

    def active_version(self, session: Session, kb_id: str) -> WeKnoraIndexVersion | None:
        version_id = session.scalar(
            select(KnowledgeBase.active_weknora_version_id).where(
                KnowledgeBase.id == kb_id
            )
        )
        if not version_id:
            return None
        version = session.get(WeKnoraIndexVersion, version_id)
        if version is None or version.status != READY:
            return None
        return version

    def activate(
        self, session: Session, kb_id: str, version: WeKnoraIndexVersion
    ) -> None:
        kb = session.get(KnowledgeBase, kb_id)
        if kb is None:
            raise PublishError(f"knowledge base '{kb_id}' not found")
        kb.active_weknora_version_id = version.id
        session.flush()


class ConceptMapStore:
    """Persist the concept id <-> backend document id map for a snapshot."""

    def concept_to_doc(self, session: Session, version_id: str) -> dict[str, str]:
        rows = session.scalars(
            select(WeKnoraConceptMap).where(WeKnoraConceptMap.version_id == version_id)
        ).all()
        return {row.concept_id: row.doc_ref for row in rows}

    def doc_to_concept(self, session: Session, version_id: str) -> dict[str, str]:
        rows = session.scalars(
            select(WeKnoraConceptMap).where(WeKnoraConceptMap.version_id == version_id)
        ).all()
        return {row.doc_ref: row.concept_id for row in rows}

    def replace_maps(
        self, session: Session, version: WeKnoraIndexVersion, concept_docs: dict[str, str]
    ) -> None:
        existing = session.scalars(
            select(WeKnoraConceptMap).where(
                WeKnoraConceptMap.version_id == version.id
            )
        ).all()
        for row in existing:
            session.delete(row)
        session.flush()
        for concept_id, doc_ref in concept_docs.items():
            session.add(
                WeKnoraConceptMap(
                    version_id=version.id, concept_id=concept_id, doc_ref=doc_ref
                )
            )
        session.flush()


class SnapshotPublisher:
    """Materialize a new backend snapshot and atomically activate it."""

    def __init__(
        self,
        backend: RetrievalBackend,
        *,
        retention: int = 3,
        max_polls: int = 120,
        poll_interval: float = 1.0,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.backend = backend
        self.retention = max(1, retention)
        self.max_polls = max(1, max_polls)
        self.poll_interval = poll_interval
        self._sleep = sleep or time.sleep
        self.resolver = ActiveResolver()
        self.store = ConceptMapStore()

    def publish(
        self,
        session: Session,
        *,
        kb_id: str,
        concepts: list[Concept],
        git_commit: str,
        on_phase: Callable[[str], None] | None = None,
    ) -> WeKnoraIndexVersion:
        concepts = [concept for concept in concepts if concept.id]
        if not concepts:
            raise PublishError("no verified knowledge to publish")

        existing = session.scalar(
            select(WeKnoraIndexVersion).where(
                WeKnoraIndexVersion.kb_id == kb_id,
                WeKnoraIndexVersion.git_commit == git_commit,
            )
        )
        if existing is not None and existing.status == READY:
            self.resolver.activate(session, kb_id, existing)
            session.commit()
            return existing
        if existing is not None and existing.status == BUILDING:
            raise PublishError("a publish is already in progress for this knowledge base")

        self._phase(on_phase, BUILDING)
        ref = self.backend.create_snapshot(concepts, label=git_commit)
        version = existing or WeKnoraIndexVersion(
            kb_id=kb_id, git_commit=git_commit, weknora_kb_id=ref.snapshot_id
        )
        if existing is not None:
            self._safe_delete(
                SnapshotRef(self.backend.name, existing.weknora_kb_id, existing.git_commit)
            )
        version.weknora_kb_id = ref.snapshot_id
        version.status = BUILDING
        version.doc_total = len(concepts)
        version.doc_completed = 0
        version.error = None
        session.add(version)
        session.flush()

        self._phase(on_phase, "indexing")
        progress = self._wait(ref)
        version.doc_completed = progress.done
        if progress.status != READY:
            version.status = FAILED
            version.error = progress.error or "publish failed"
            session.flush()
            self._safe_delete(ref)
            session.commit()
            raise PublishError(version.error)

        self._phase(on_phase, "activating")
        self.store.replace_maps(session, version, progress.concept_docs)
        version.status = READY
        version.ready_at = _now()
        version.doc_completed = progress.done
        self.resolver.activate(session, kb_id, version)
        session.flush()
        self._retire_old(session, kb_id, keep=version)
        session.commit()
        return version

    @staticmethod
    def _phase(on_phase: Callable[[str], None] | None, status: str) -> None:
        if on_phase is not None:
            with contextlib.suppress(Exception):
                on_phase(status)

    def _wait(self, ref: SnapshotRef) -> BuildProgress:
        last = BuildProgress(BUILDING)
        for _ in range(self.max_polls):
            last = self.backend.poll(ref)
            if last.status in (READY, FAILED):
                return last
            self._sleep(self.poll_interval)
        return BuildProgress(FAILED, last.done, last.total, error="publish timed out")

    def _safe_delete(self, ref: SnapshotRef) -> None:
        with contextlib.suppress(Exception):
            self.backend.delete_snapshot(ref)

    def _retire_old(
        self, session: Session, kb_id: str, *, keep: WeKnoraIndexVersion
    ) -> None:
        rows = session.scalars(
            select(WeKnoraIndexVersion)
            .where(
                WeKnoraIndexVersion.kb_id == kb_id,
                WeKnoraIndexVersion.status == READY,
            )
            .order_by(
                WeKnoraIndexVersion.created_at.desc(),
                WeKnoraIndexVersion.id.desc(),
            )
        ).all()
        for old in rows[self.retention :]:
            if old.id == keep.id:
                continue
            old.status = RETIRED
            session.flush()
            self._safe_delete(
                SnapshotRef(self.backend.name, old.weknora_kb_id, old.git_commit)
            )
