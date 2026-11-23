"""Snapshot-backed read path.

Resolves the active snapshot for a knowledge base at query time, searches that
snapshot, and maps backend document ids back to platform concept ids. The read
path never materializes or publishes anything.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from .backend import RetrievalBackend, SnapshotRef
from .interface import Answerer, RetrievalHit, RetrievalResponse
from .publish import ActiveResolver, ConceptMapStore


class SnapshotRetrievalService:
    """Stable facade over one backend, scoped to a single knowledge base."""

    def __init__(
        self,
        *,
        backend: RetrievalBackend,
        session_factory: sessionmaker[Session],
        kb_id: str,
        code_engine=None,
    ) -> None:
        self.backend = backend
        self._session_factory = session_factory
        self.kb_id = kb_id
        self.engines: dict[str, object] = {"knowledge": backend}
        if code_engine is not None:
            self.engines["code"] = code_engine
        self._resolver = ActiveResolver()
        self._store = ConceptMapStore()

    def _resolve(self):
        with self._session_factory() as session:
            version = self._resolver.active_version(session, self.kb_id)
            if version is None:
                return None, {}
            return version, self._store.doc_to_concept(session, version.id)

    def search(
        self, query: str, *, kind: str = "knowledge", top_k: int = 5
    ) -> RetrievalResponse:
        if kind == "code":
            engine = self.engines.get("code")
            if engine is None:
                raise KeyError("no engine for kind 'code'")
            code_hits = list(engine.search(query, top_k=top_k))  # type: ignore[attr-defined]
            return RetrievalResponse(
                query=query,
                kind=kind,
                engine=engine.name,  # type: ignore[attr-defined]
                hits=code_hits,
                knowledge_version=getattr(engine, "version", None),
            )
        if kind != "knowledge":
            raise KeyError(
                f"no engine for kind '{kind}', available: {list(self.engines)}"
            )

        version, doc_map = self._resolve()
        if version is None:
            return RetrievalResponse(
                query=query, kind=kind, engine=self.backend.name, hits=[]
            )
        ref = SnapshotRef(self.backend.name, version.weknora_kb_id, version.git_commit)
        hits: list[RetrievalHit] = []
        for raw in self.backend.search(query, ref=ref, top_k=top_k):
            concept_id = doc_map.get(raw.doc_ref)
            if concept_id is None:
                continue
            hits.append(
                RetrievalHit(
                    concept_id=concept_id,
                    title=raw.title,
                    snippet=raw.snippet,
                    score=raw.score,
                    engine=self.backend.name,
                )
            )
        return RetrievalResponse(
            query=query,
            kind=kind,
            engine=self.backend.name,
            hits=hits,
            knowledge_version=version.git_commit,
        )

    def answer(
        self, query: str, *, answerer: Answerer | None = None, top_k: int = 5
    ) -> str:
        hits = self.search(query, kind="knowledge", top_k=top_k).hits
        if answerer is not None:
            return answerer(query, hits)
        return hits[0].snippet if hits else ""

    @property
    def knowledge_version(self) -> str | None:
        version, _ = self._resolve()
        return version.git_commit if version is not None else None
