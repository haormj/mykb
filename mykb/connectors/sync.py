"""Import pipeline: run a connector's two stages into the bundle.

The importer owns incremental behaviour. It records a per-connector sync state
(fingerprint + produced concept id per source key) so that re-running a sync does
not re-normalize or re-write unchanged source content.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..okf.bundle import Bundle
from .base import Connector


@dataclass
class SyncResult:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def imported(self) -> int:
        return len(self.added) + len(self.updated)


def _safe_rel(key: str) -> str:
    parts = [p for p in key.replace("\\", "/").split("/") if p not in ("", ".", "..")]
    rel = "/".join(parts) or "item"
    return rel if rel.endswith(".md") else f"{rel}.md"


class Importer:
    """Runs a single connector against a bundle, producing ``raw`` concepts."""

    def __init__(
        self,
        bundle: Bundle,
        connector: Connector,
        *,
        subdir: str | None = None,
        state_dir: str | Path | None = None,
    ) -> None:
        self.bundle = bundle
        self.connector = connector
        self.subdir = subdir if subdir is not None else connector.name
        base = Path(state_dir) if state_dir is not None else bundle.root / ".mykb"
        self.state_path = base / f"sync-{connector.name}.json"

    def _load_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_state(self, state: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def run(self, *, incremental: bool = True) -> SyncResult:
        result = SyncResult()
        items = self.connector.sync()
        state = self._load_state()
        for item in items:
            fingerprint = item.fingerprint()
            previous = state.get(item.key)
            if incremental and previous and previous.get("fingerprint") == fingerprint:
                result.skipped.append(item.key)
                continue
            rel = _safe_rel(item.key)
            concepts = self.connector.normalize([item])
            for concept in concepts:
                cid = self.bundle.write_concept(concept, "raw", f"{self.subdir}/{rel}")
                (result.updated if previous else result.added).append(cid)
            state[item.key] = {
                "fingerprint": fingerprint,
                "concept_id": concepts[0].id if concepts else None,
                "resource": item.resource,
            }
        self._save_state(state)
        return result
