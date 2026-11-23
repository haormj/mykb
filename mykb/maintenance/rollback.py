"""Rollback to a historical knowledge version (git commit) via snapshots."""

from __future__ import annotations

import subprocess
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import WeKnoraIndexVersion
from ..okf.bundle import Bundle
from ..okf.model import Concept
from ..retrieval.backend import READY
from ..retrieval.publish import ActiveResolver, SnapshotPublisher


class RollbackError(RuntimeError):
    """Raised when a git operation or rollback target is invalid."""


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise RollbackError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def concepts_at_commit(bundle: Bundle, commit: str) -> list[Concept]:
    """Read verified/stable knowledge concepts as they existed at ``commit``."""
    listing = _git(bundle.root, "ls-tree", "-r", "--name-only", commit, "--", "knowledge")
    concepts: list[Concept] = []
    for path in listing.splitlines():
        if not path.endswith(".md"):
            continue
        if path.rsplit("/", 1)[-1] in ("index.md", "log.md"):
            continue
        text = _git(bundle.root, "show", f"{commit}:{path}")
        concept = Concept.from_text(text)
        concept.id = bundle.concept_id(path)
        if concept.is_verified_stable():
            concepts.append(concept)
    return concepts


class IndexRollback:
    """Restore a knowledge base to a historical snapshot.

    A ready snapshot inside the retention window is activated by pointer only.
    Otherwise the concepts are rebuilt from the git commit into a new snapshot.
    """

    def __init__(self, bundle: Bundle, backend, *, retention: int = 3) -> None:
        self.bundle = bundle
        self.backend = backend
        self.retention = retention

    def rollback(
        self, session: Session, *, kb_id: str, version: str
    ) -> WeKnoraIndexVersion:
        existing = session.scalar(
            select(WeKnoraIndexVersion).where(
                WeKnoraIndexVersion.kb_id == kb_id,
                WeKnoraIndexVersion.git_commit == version,
                WeKnoraIndexVersion.status == READY,
            )
        )
        if existing is not None:
            ActiveResolver().activate(session, kb_id, existing)
            session.commit()
            return existing

        concepts = concepts_at_commit(self.bundle, version)
        if not concepts:
            raise RollbackError(f"no verified knowledge at commit {version}")
        publisher = SnapshotPublisher(self.backend, retention=self.retention)
        return publisher.publish(
            session, kb_id=kb_id, concepts=concepts, git_commit=version
        )
