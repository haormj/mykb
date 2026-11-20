"""Score storage and trend queries."""

from __future__ import annotations

import json
from pathlib import Path

from ..okf.bundle import Bundle


class Scoreboard:
    """Persists eval runs and exposes per-set score trends."""

    def __init__(self, bundle: Bundle, *, state_dir: str | Path | None = None) -> None:
        base = Path(state_dir) if state_dir is not None else bundle.root / ".mykb" / "eval-runs"
        self.base = base

    def save(self, run) -> None:
        directory = self.base / run.set_name
        directory.mkdir(parents=True, exist_ok=True)
        stem = run.created_at.replace(":", "-")
        path = directory / f"{stem}.json"
        counter = 1
        while path.exists():
            path = directory / f"{stem}-{counter}.json"
            counter += 1
        path.write_text(
            json.dumps(run.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def history(self, set_name: str) -> list[dict]:
        directory = self.base / set_name
        if not directory.exists():
            return []
        runs = []
        for path in sorted(directory.glob("*.json")):
            try:
                runs.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        runs.sort(key=lambda run: run.get("created_at", ""))
        return runs

    def latest(self, set_name: str) -> dict | None:
        history = self.history(set_name)
        return history[-1] if history else None

    def trend(self, set_name: str) -> list[dict]:
        return [
            {
                "created_at": run.get("created_at"),
                "a_score": run.get("a_score", 0.0),
                "b_score": run.get("b_score", 0.0),
                "knowledge_version": run.get("knowledge_version"),
            }
            for run in self.history(set_name)
        ]
