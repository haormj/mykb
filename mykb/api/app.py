"""FastAPI application factory.

Platform routes are knowledge-base scoped: identity and the knowledge-base
registry live under ``/auth`` and ``/kbs``; content operations live under
``/kbs/{kb_id}``. Content itself is stored in per-KB git-backed OKF bundles.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from ..auth.tokens import TokenService
from ..config import Settings, load_settings
from ..db import Base
from ..db.session import create_db_engine, create_session_factory
from ..kb.context import RetrievalCache
from .routes import admin, auth, evaluation, kbs, members, retrieval, review


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

    app = FastAPI(title="mykb", version="0.2.0")
    app.state.settings = resolved
    resolved.kb_root.mkdir(parents=True, exist_ok=True)

    engine = create_db_engine(resolved.database_url)
    app.state.db_engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.token_service = TokenService(
        resolved.jwt_secret, expires_days=resolved.token_expires_days
    )
    app.state.retrieval_cache = RetrievalCache()

    if create_tables:
        Base.metadata.create_all(engine)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(kbs.router)
    app.include_router(members.router)
    app.include_router(retrieval.router)
    app.include_router(evaluation.router)
    app.include_router(review.router)
    return app


app = create_app()
