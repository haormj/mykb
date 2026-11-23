"""WeKnora implementation of the snapshot backend contract."""

from __future__ import annotations

import uuid

from ....okf.model import Concept
from ...backend import (
    BUILDING,
    FAILED,
    READY,
    BackendHit,
    BuildProgress,
    Capabilities,
    SnapshotRef,
)
from .client import WeKnoraClient


class WeKnoraBackend:
    """Materializes one WeKnora knowledge base per snapshot."""

    name = "weknora"
    capabilities = Capabilities(async_ingest=True)

    def __init__(
        self,
        client: WeKnoraClient,
        *,
        kb_name_prefix: str = "mykb-index",
        embedding_model_id: str | None = None,
    ) -> None:
        self.client = client
        self.kb_name_prefix = kb_name_prefix
        self.embedding_model_id = embedding_model_id
        self._docs: dict[str, dict[str, str]] = {}

    def create_snapshot(
        self, concepts: list[Concept], *, label: str | None = None
    ) -> SnapshotRef:
        suffix = label or uuid.uuid4().hex
        kb = self.client.create_knowledge_base(
            name=f"{self.kb_name_prefix}-{suffix}",
            description="mykb published snapshot",
            embedding_model_id=self.embedding_model_id,
        )
        kb_id = str(kb["id"])
        docs: dict[str, str] = {}
        for concept in concepts:
            if not concept.id:
                continue
            doc_id = self.client.add_manual_knowledge(
                kb_id,
                title=concept.title or concept.id,
                content=concept.body or concept.title or concept.id,
            )
            docs[concept.id] = doc_id
        self._docs[kb_id] = docs
        return SnapshotRef(self.name, kb_id, label)

    def poll(self, ref: SnapshotRef) -> BuildProgress:
        docs = self._docs.get(ref.snapshot_id)
        if docs is None:
            return BuildProgress(FAILED, error="unknown snapshot")
        rows = self.client.list_all_knowledge(ref.snapshot_id)
        by_id = {row.get("id"): row for row in rows}
        completed = 0
        failed = 0
        error: str | None = None
        for doc_id in docs.values():
            status = (by_id.get(doc_id) or {}).get("parse_status")
            if status == "completed":
                completed += 1
            elif status == "failed":
                failed += 1
                error = error or f"document {doc_id} failed to parse"
        total = len(docs)
        concept_docs = dict(docs)
        if failed:
            return BuildProgress(FAILED, completed, total, error=error, concept_docs=concept_docs)
        if completed >= total:
            return BuildProgress(READY, completed, total, concept_docs=concept_docs)
        return BuildProgress(BUILDING, completed, total)

    def search(
        self, query: str, *, ref: SnapshotRef, top_k: int = 5
    ) -> list[BackendHit]:
        results = self.client.knowledge_search(
            query=query,
            knowledge_base_ids=[ref.snapshot_id],
            match_count=top_k,
        )
        hits: list[BackendHit] = []
        for item in results:
            doc_ref = item.get("knowledge_id")
            if not doc_ref:
                continue
            hits.append(
                BackendHit(
                    doc_ref=str(doc_ref),
                    title=str(item.get("knowledge_title") or ""),
                    snippet=str(item.get("content") or ""),
                    score=float(item.get("score") or 0.0),
                )
            )
        return hits

    def delete_snapshot(self, ref: SnapshotRef) -> None:
        self.client.delete_knowledge_base(ref.snapshot_id)
        self._docs.pop(ref.snapshot_id, None)

    def healthcheck(self) -> bool:
        return self.client.health()
