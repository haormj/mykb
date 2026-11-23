"""Build retrieval backends and per-knowledge-base read services."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from ..okf.bundle import Bundle
from .backend import RetrievalBackend
from .engines.codegraph import LocalCodeGraph
from .engines.local import LocalBackend
from .read import SnapshotRetrievalService


def build_knowledge_backend(settings=None) -> RetrievalBackend:
    """Return the configured knowledge backend (WeKnora when a URL is set)."""
    url = getattr(settings, "weknora_url", None) if settings is not None else None
    if url:
        from .engines.weknora.backend import WeKnoraBackend
        from .engines.weknora.client import WeKnoraClient

        client = WeKnoraClient(
            base_url=url,
            api_key=getattr(settings, "weknora_key", None),
            tenant_id=getattr(settings, "weknora_tenant_id", None),
            timeout=getattr(settings, "weknora_timeout", 30.0),
        )
        return WeKnoraBackend(client)
    return LocalBackend()


def build_retrieval_service(
    bundle_root: str | Path,
    *,
    backend=None,
    session_factory: sessionmaker[Session] | None = None,
    kb_id: str | None = None,
    sync: bool = False,
):
    """Build a read service.

    With a platform session and knowledge-base id the service resolves the active
    snapshot from the database and never publishes. Without them (offline CLI),
    it falls back to a synced in-memory engine when ``sync`` is requested.
    """
    code = LocalCodeGraph()
    if session_factory is not None and kb_id is not None:
        return SnapshotRetrievalService(
            backend=backend or build_knowledge_backend(),
            session_factory=session_factory,
            kb_id=kb_id,
            code_engine=code,
        )

    from .engines.markdown_rag import LocalMarkdownRAG
    from .interface import RetrievalService
    from .sync import IndexSync

    knowledge = LocalMarkdownRAG()
    if sync:
        IndexSync(Bundle(Path(bundle_root)), [knowledge], code_engine=code).sync()
    return RetrievalService(knowledge_engine=knowledge, code_engine=code)
