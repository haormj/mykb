"""Index rollback to a historical knowledge version (git commit)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..okf.bundle import Bundle
from ..okf.model import Concept
from ..retrieval.index import select_code_sources
from ..retrieval.interface import RetrievalEngine
from ..retrieval.sync import IndexSync, IndexVersion
from ..util import now_iso


class RollbackError(RuntimeError):
    """Raised when a git operation for rollback fails."""


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
    """Re-indexes engines from a historical commit and records the rollback."""

    def __init__(
        self,
        bundle: Bundle,
        knowledge_engines: list[RetrievalEngine],
        *,
        code_engine: RetrievalEngine | None = None,
        state_dir: str | Path | None = None,
    ) -> None:
        self.bundle = bundle
        self.knowledge_engines = knowledge_engines
        self.code_engine = code_engine
        self.sync = IndexSync(
            bundle, knowledge_engines, code_engine=code_engine, state_dir=state_dir
        )

    def rollback(self, version: str) -> IndexVersion:
        concepts = concepts_at_commit(self.bundle, version)
        for engine in self.knowledge_engines:
            engine.index(concepts, version=version)
        if self.code_engine is not None:
            self.code_engine.index(select_code_sources(self.bundle), version=version)
        names = [engine.name for engine in self.knowledge_engines]
        if self.code_engine is not None:
            names.append(self.code_engine.name)
        record = IndexVersion(
            version=version,
            created_at=now_iso(),
            knowledge_ids=[concept.id or "" for concept in concepts],
            code_ids=[],
            engines=names,
        )
        self.sync.mark_version(record)
        return record
