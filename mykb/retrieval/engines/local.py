"""In-process snapshot backend used for offline development and tests."""

from __future__ import annotations

import uuid

from ...okf.model import Concept
from ..backend import (
    FAILED,
    READY,
    BackendHit,
    BuildProgress,
    Capabilities,
    SnapshotRef,
)
from .markdown_rag import LocalMarkdownRAG


class LocalBackend:
    """Materializes each snapshot into an isolated in-memory markdown RAG."""

    name = "local-markdown-rag"
    capabilities = Capabilities(async_ingest=False)

    def __init__(self) -> None:
        self._engines: dict[str, LocalMarkdownRAG] = {}
        self._docs: dict[str, dict[str, str]] = {}

    def create_snapshot(
        self, concepts: list[Concept], *, label: str | None = None
    ) -> SnapshotRef:
        snapshot_id = uuid.uuid4().hex
        engine = LocalMarkdownRAG()
        engine.index(concepts, version=label)
        self._engines[snapshot_id] = engine
        self._docs[snapshot_id] = {
            concept.id: concept.id for concept in concepts if concept.id
        }
        return SnapshotRef(self.name, snapshot_id, label)

    def poll(self, ref: SnapshotRef) -> BuildProgress:
        if ref.snapshot_id not in self._engines:
            return BuildProgress(FAILED, error="unknown snapshot")
        docs = self._docs[ref.snapshot_id]
        return BuildProgress(READY, len(docs), len(docs), concept_docs=dict(docs))

    def search(
        self, query: str, *, ref: SnapshotRef, top_k: int = 5
    ) -> list[BackendHit]:
        engine = self._engines.get(ref.snapshot_id)
        if engine is None:
            return []
        return [
            BackendHit(hit.concept_id, hit.title, hit.snippet, hit.score)
            for hit in engine.search(query, top_k=top_k)
        ]

    def delete_snapshot(self, ref: SnapshotRef) -> None:
        self._engines.pop(ref.snapshot_id, None)
        self._docs.pop(ref.snapshot_id, None)

    def healthcheck(self) -> bool:
        return True
