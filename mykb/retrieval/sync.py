"""Versioned index sync.

Each sync binds the engine indexes to a knowledge version (the current git commit)
and records a history entry, enabling audit and rollback.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..okf.bundle import Bundle
from ..util import now_iso
from .index import select_code_sources, select_indexable_knowledge
from .interface import RetrievalEngine


def get_head_commit(root: str | Path) -> str | None:
    """Return the git HEAD commit for ``root`` or ``None`` if not a git repo."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


@dataclass
class IndexVersion:
    version: str
    created_at: str
    knowledge_ids: list[str] = field(default_factory=list)
    code_ids: list[str] = field(default_factory=list)
    engines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "knowledge_ids": self.knowledge_ids,
            "code_ids": self.code_ids,
            "engines": self.engines,
        }


class IndexSync:
    """Indexes verified knowledge into engines and records a version history."""

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
        base = Path(state_dir) if state_dir is not None else bundle.root / ".mykb"
        self.state_path = base / "index-state.json"
        self.history_path = base / "index-versions.json"

    def current_version(self) -> str:
        return get_head_commit(self.bundle.root) or "unversioned"

    def sync(
        self,
        *,
        version: str | None = None,
        knowledge_engines: list[RetrievalEngine] | None = None,
        code_engine: RetrievalEngine | None = None,
    ) -> IndexVersion:
        resolved_version = version or self.current_version()
        knowledge = select_indexable_knowledge(self.bundle)
        code = select_code_sources(self.bundle)

        engines = knowledge_engines if knowledge_engines is not None else self.knowledge_engines
        resolved_code_engine = code_engine if code_engine is not None else self.code_engine

        for engine in engines:
            engine.index(knowledge, version=resolved_version)
        if resolved_code_engine is not None:
            resolved_code_engine.index(code, version=resolved_version)

        names = [engine.name for engine in engines]
        if resolved_code_engine is not None:
            names.append(resolved_code_engine.name)
        record = IndexVersion(
            version=resolved_version,
            created_at=now_iso(),
            knowledge_ids=[c.id or "" for c in knowledge],
            code_ids=[c.id or "" for c in code],
            engines=names,
        )
        self._append_history(record)
        self._write_state(record)
        return record

    # -- state ------------------------------------------------------------
    def mark_version(self, record: IndexVersion) -> None:
        """Record an externally produced index version (e.g. after a rollback)."""
        self._append_history(record)
        self._write_state(record)

    def history(self) -> list[dict]:
        if not self.history_path.exists():
            return []
        try:
            return list(json.loads(self.history_path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return []

    def latest(self) -> dict | None:
        if not self.state_path.exists():
            return None
        try:
            return dict(json.loads(self.state_path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return None

    def _append_history(self, record: IndexVersion) -> None:
        entries = self.history()
        entries.append(record.to_dict())
        self._write(self.history_path, entries)

    def _write_state(self, record: IndexVersion) -> None:
        self._write(self.state_path, record.to_dict())

    @staticmethod
    def _write(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
