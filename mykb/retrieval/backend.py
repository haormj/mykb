"""Backend plugin contract for pluggable retrieval engines.

The platform owns versioning, snapshot pointers, concept mapping and retention.
A backend only materializes an immutable snapshot, reports its readiness, searches
inside it, and drops it. New RAG backends (WeKnora, OpenViking, ...) implement this
protocol; orchestration code never needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..okf.model import Concept

BUILDING = "building"
READY = "ready"
FAILED = "failed"


@dataclass(frozen=True)
class Capabilities:
    """Declared abilities of a backend, used for routing and clear errors."""

    supports_code: bool = False
    supports_generation: bool = False
    async_ingest: bool = False


@dataclass(frozen=True)
class SnapshotRef:
    """Opaque handle to one materialized snapshot inside a backend."""

    backend: str
    snapshot_id: str
    label: str | None = None


@dataclass
class BuildProgress:
    """Readiness of an in-flight snapshot build."""

    status: str
    done: int = 0
    total: int = 0
    error: str | None = None
    concept_docs: dict[str, str] = field(default_factory=dict)


@dataclass
class BackendHit:
    """A raw backend hit keyed by the backend's own document id."""

    doc_ref: str
    title: str
    snippet: str
    score: float


@runtime_checkable
class RetrievalBackend(Protocol):
    """Interchangeable snapshot-based retrieval backend."""

    name: str
    capabilities: Capabilities

    def create_snapshot(
        self, concepts: list[Concept], *, label: str | None = None
    ) -> SnapshotRef: ...

    def poll(self, ref: SnapshotRef) -> BuildProgress: ...

    def search(
        self, query: str, *, ref: SnapshotRef, top_k: int = 5
    ) -> list[BackendHit]: ...

    def delete_snapshot(self, ref: SnapshotRef) -> None: ...

    def healthcheck(self) -> bool: ...
