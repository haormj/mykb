"""Per-knowledge-base runtime context and retrieval service cache."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from ..db.models import KnowledgeBase
from ..okf.bundle import Bundle
from ..retrieval.interface import RetrievalService
from ..retrieval.service import build_knowledge_backend, build_retrieval_service


def bundle_for(kb: KnowledgeBase) -> Bundle:
    return Bundle(Path(kb.local_path))


class RetrievalCache:
    """Caches one read service per knowledge base.

    The active snapshot is resolved from the database on every query, so a
    publish that flips the pointer is picked up without cross-process cache
    invalidation. The cache only avoids reconstructing the service object.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        backend=None,
    ) -> None:
        self._factory = session_factory
        self._backend = backend or build_knowledge_backend()
        self._services: dict[str, RetrievalService] = {}

    def get(self, kb: KnowledgeBase, *, sync: bool = False) -> RetrievalService:
        if kb.id not in self._services:
            self._services[kb.id] = build_retrieval_service(
                Path(kb.local_path),
                backend=self._backend,
                session_factory=self._factory,
                kb_id=kb.id,
            )
        return self._services[kb.id]

    def rebuild(self, kb: KnowledgeBase) -> RetrievalService:
        service = build_retrieval_service(
            Path(kb.local_path),
            backend=self._backend,
            session_factory=self._factory,
            kb_id=kb.id,
        )
        self._services[kb.id] = service
        return service

    def invalidate(self, kb_id: str) -> None:
        self._services.pop(kb_id, None)
