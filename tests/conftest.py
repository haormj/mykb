from __future__ import annotations

import os
import tempfile

import pytest

# Import-time defaults so `mykb.api.app` can build its module-level app during
# test collection. Individual tests override DATABASE_URL / MYKB_KB_ROOT.
_BOOT = tempfile.mkdtemp(prefix="mykb-test-boot-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_BOOT}/bootstrap.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-with-enough-length-0123456789")
os.environ.setdefault("MYKB_SECRET_KEY", "test-secret-key-with-enough-length")
os.environ.setdefault("MYKB_KB_ROOT", f"{_BOOT}/bootstrap-kbs")


@pytest.fixture
def app(tmp_path):
    from mykb.api.app import create_app
    from mykb.db.bootstrap import bootstrap

    application = create_app(
        database_url=f"sqlite:///{tmp_path / 'db.sqlite'}",
        kb_root=tmp_path / "kbs",
        create_tables=True,
    )
    with application.state.session_factory() as session:
        bootstrap(session, {"ADMIN_USERNAME": "root", "ADMIN_PASSWORD": "root-pass"})
    return application


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client
