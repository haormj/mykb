"""OKF concept model.

A concept is a markdown file with a YAML frontmatter block where ``type`` is the
only required field. Unknown frontmatter keys are preserved on round-trip, as the
OKF spec requires consumers to keep extension fields they do not understand.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DELIMITER = "---"


class FrontmatterError(ValueError):
    """Raised when a markdown document has no parseable OKF frontmatter."""


class _Dumper(yaml.SafeDumper):
    """SafeDumper that renders datetimes as ISO-8601 strings."""


def _repr_datetime(dumper: yaml.SafeDumper, data: _dt.date) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:str", data.isoformat())


_Dumper.add_representer(_dt.datetime, _repr_datetime)
_Dumper.add_representer(_dt.date, _repr_datetime)


def _normalize(value: Any) -> Any:
    """Convert datetime values to ISO strings so round-trips stay plain strings."""
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def parse(text: str) -> tuple[dict[str, Any], str]:
    """Split a markdown document into ``(frontmatter dict, body)``."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != DELIMITER:
        raise FrontmatterError("document does not start with a '---' frontmatter block")
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == DELIMITER:
            end = idx
            break
    if end is None:
        raise FrontmatterError("unterminated frontmatter block (missing closing '---')")
    raw_yaml = "".join(lines[1:end])
    try:
        data = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"invalid YAML frontmatter: {exc}") from exc
    if not isinstance(data, dict):
        raise FrontmatterError("frontmatter must be a YAML mapping")
    body = "".join(lines[end + 1 :])
    return _normalize(data), body


def serialize(frontmatter: dict[str, Any], body: str = "") -> str:
    """Render a concept as markdown with a YAML frontmatter block."""
    fm = yaml.dump(
        frontmatter,
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    return f"{DELIMITER}\n{fm}{DELIMITER}\n{body}"


@dataclass
class Concept:
    """A single OKF concept (frontmatter + markdown body)."""

    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    id: str | None = None

    @property
    def type(self) -> str | None:
        value = self.frontmatter.get("type")
        return str(value) if value is not None else None

    @property
    def title(self) -> str | None:
        value = self.frontmatter.get("title")
        return str(value) if value is not None else None

    @property
    def status(self) -> str | None:
        value = self.frontmatter.get("status")
        return str(value) if value is not None else None

    @property
    def resource(self) -> str | None:
        value = self.frontmatter.get("resource")
        return str(value) if value is not None else None

    @property
    def stale_after(self) -> str | None:
        value = self.frontmatter.get("stale_after")
        return str(value) if value is not None else None

    @property
    def superseded_by(self) -> str | None:
        value = self.frontmatter.get("superseded_by")
        return str(value) if value is not None else None

    @property
    def sources(self) -> list[dict[str, Any]]:
        return list(self.frontmatter.get("sources") or [])

    @property
    def verified(self) -> list[dict[str, Any]]:
        return list(self.frontmatter.get("verified") or [])

    @property
    def generated(self) -> dict[str, Any]:
        value = self.frontmatter.get("generated")
        return dict(value) if isinstance(value, dict) else {}

    def source_ids(self) -> list[str]:
        """Concept ids referenced by the ``sources`` field."""
        ids: list[str] = []
        for entry in self.sources:
            if isinstance(entry, dict):
                ref = entry.get("id") or entry.get("resource")
            else:
                ref = entry
            if ref:
                ids.append(str(ref))
        return ids

    def is_verified_stable(self) -> bool:
        return self.status == "stable" and bool(self.verified)

    @classmethod
    def from_text(cls, text: str, *, id: str | None = None) -> Concept:
        frontmatter, body = parse(text)
        return cls(frontmatter=frontmatter, body=body, id=id)

    @classmethod
    def from_file(cls, path: str | Path, *, id: str | None = None) -> Concept:
        return cls.from_text(Path(path).read_text(encoding="utf-8"), id=id)

    def to_text(self) -> str:
        return serialize(self.frontmatter, self.body)

    def to_file(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_text(), encoding="utf-8")
