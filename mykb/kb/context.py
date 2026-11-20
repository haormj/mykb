"""Per-knowledge-base runtime context and retrieval service cache."""

from __future__ import annotations

from pathlib import Path

from ..okf.bundle import Bundle
from ..retrieval.interface import RetrievalService
from ..retrieval.service import build_retrieval_service
from ..db.models import KnowledgeBase


def bundle_for(kb: KnowledgeBase) -> Bundle:
    return Bundle(Path(kb.local_path))


class RetrievalCache:
    """Caches one retrieval service per knowledge base, invalidated on writes."""

    def __init__(self) -> None:
        self._services: dict[str, RetrievalService] = {}

    def get(self, kb: KnowledgeBase, *, sync: bool = True) -> RetrievalService:
        if kb.id not in self._services:
            self._services[kb.id] = build_retrieval_service(Path(kb.local_path), sync=sync)
        return self._services[kb.id]

    def rebuild(self, kb: KnowledgeBase) -> RetrievalService:
        service = build_retrieval_service(Path(kb.local_path))
        self._services[kb.id] = service
        return service

    def invalidate(self, kb_id: str) -> None:
        self._services.pop(kb_id, None)
