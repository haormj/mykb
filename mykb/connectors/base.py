"""Connector protocol and raw item definitions.

A connector has two orthogonal stages:

* ``sync`` pulls raw data from a source platform (auth, pagination, rate limits,
  incremental pull) and yields :class:`RawItem` objects.
* ``normalize`` turns raw items into OKF :class:`Concept` objects.

Keeping the stages separate lets source-specific fetching and content-to-markdown
mapping evolve independently.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..okf.model import Concept


@dataclass
class RawItem:
    """A single raw item pulled from a source during the sync stage."""

    key: str
    resource: str
    content: str
    title: str | None = None
    content_type: str = "text/markdown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def fingerprint(self) -> str:
        """Stable content fingerprint used for incremental sync."""
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@runtime_checkable
class Connector(Protocol):
    """Two-stage data-source connector."""

    name: str

    def sync(self) -> list[RawItem]:
        """Pull raw data from the source platform."""

    def normalize(self, items: list[RawItem]) -> list[Concept]:
        """Convert raw items into OKF source concepts."""


class BaseConnector:
    """Convenience base class implementing ``normalize`` for source concepts."""

    name = "base"
    source_type = "源数据"

    def __init__(self, *, base_uri: str | None = None, source_type: str | None = None) -> None:
        self.base_uri = base_uri.rstrip("/") if base_uri else None
        if source_type:
            self.source_type = source_type

    def resource_for(self, key: str) -> str:
        if self.base_uri:
            return f"{self.base_uri}/{key}"
        return key

    def normalize(self, items: list[RawItem]) -> list[Concept]:
        from ..util import now_iso

        concepts: list[Concept] = []
        for item in items:
            frontmatter: dict[str, Any] = {
                "type": self.source_type,
                "title": item.title or item.key,
                "resource": item.resource,
                "generated": {"by": f"process:{self.name}", "at": now_iso()},
                "status": "draft",
                "tags": ["source", self.name],
                "x-connector": self.name,
            }
            for key, value in (item.metadata.get("frontmatter") or {}).items():
                frontmatter.setdefault(key, value)
            concepts.append(Concept(frontmatter=frontmatter, body=item.content))
        return concepts

    def sync(self) -> list[RawItem]:  # pragma: no cover - overridden by connectors
        raise NotImplementedError
