"""FastAPI application factory.

Platform routes are knowledge-base scoped: identity and the knowledge-base
registry live under ``/auth`` and ``/kbs``; content operations live under
``/kbs/{kb_id}``. Content itself is stored in per-KB git-backed OKF bundles.
"""

from __future__ import annotations

import os
import threading
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from ..auth.tokens import TokenService
from ..config import Settings, load_settings
from ..conversion import ConverterService
from ..db import Base
from ..db.session import create_db_engine, create_session_factory
from ..extraction.queue import recover_processing
from ..importing.service import mark_stale_running_failed
from ..kb.context import RetrievalCache
from ..retrieval.service import build_knowledge_backend
from .routes import (
    admin,
    auth,
    documents,
    evaluation,
    import_tasks,
    kbs,
    knowledge,
    members,
    publish,
    retrieval,
    review,
)


def build_settings(
    *, database_url: str | None = None, kb_root: str | Path | None = None
) -> Settings:
    env = dict(os.environ)
    if database_url is not None:
        env["DATABASE_URL"] = database_url
    if kb_root is not None:
        env["MYKB_KB_ROOT"] = str(kb_root)
    return load_settings(env)


def create_app(
    settings: Settings | None = None,
    *,
    database_url: str | None = None,
    kb_root: str | Path | None = None,
    create_tables: bool = False,
) -> FastAPI:
    resolved = settings or build_settings(database_url=database_url, kb_root=kb_root)
    resolved.kb_root.mkdir(parents=True, exist_ok=True)

    engine = create_db_engine(resolved.database_url)
    session_factory = create_session_factory(engine)
    executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mykb-import")

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        mark_stale_running_failed(session_factory)
        recover_processing(session_factory)
        try:
            yield
        finally:
            executor.shutdown(wait=False)

    app = FastAPI(title="mykb", version="0.2.0", lifespan=lifespan)
    app.state.settings = resolved
    app.state.db_engine = engine
    app.state.session_factory = session_factory
    app.state.token_service = TokenService(
        resolved.jwt_secret, expires_days=resolved.token_expires_days
    )
    retrieval_backend = build_knowledge_backend(resolved)
    app.state.retrieval_backend = retrieval_backend
    app.state.retrieval_cache = RetrievalCache(session_factory, retrieval_backend)
    app.state.converter_service = ConverterService(resolved)
    app.state.import_executor = executor
    app.state.kb_locks = {}
    app.state.kb_locks_guard = threading.Lock()
    app.state.extraction_locks = {}
    app.state.extraction_locks_guard = threading.Lock()

    if create_tables:
        Base.metadata.create_all(engine)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(kbs.router)
    app.include_router(members.router)
    app.include_router(knowledge.router)
    app.include_router(retrieval.router)
    app.include_router(publish.router)
    app.include_router(evaluation.router)
    app.include_router(review.router)
    app.include_router(import_tasks.router)
    app.include_router(documents.router)
    return app


app = create_app()
