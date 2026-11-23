from __future__ import annotations

import itertools
import json
import re

import httpx
import pytest

from mykb.okf.model import Concept
from mykb.retrieval.backend import READY
from mykb.retrieval.engines.weknora.backend import WeKnoraBackend
from mykb.retrieval.engines.weknora.client import WeKnoraClient
from mykb.retrieval.read import SnapshotRetrievalService


class FakeWeKnora:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.docs: dict[str, list[dict]] = {}
        self.search_results: list[dict] = []
        self._ids = itertools.count(1)

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        self.calls.append(
            {
                "method": request.method,
                "path": request.url.path,
                "headers": dict(request.headers),
                "body": body,
            }
        )
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.method == "POST" and path == "/api/v1/knowledge-bases":
            kb_id = f"kb-{next(self._ids)}"
            self.docs.setdefault(kb_id, [])
            return httpx.Response(201, json={"success": True, "data": {"id": kb_id}})
        match = re.match(r"/api/v1/knowledge-bases/([^/]+)/knowledge/manual", path)
        if match and request.method == "POST":
            kb_id = match.group(1)
            doc_id = f"doc-{next(self._ids)}"
            self.docs.setdefault(kb_id, []).append(
                {"id": doc_id, "parse_status": "completed", "title": body.get("title")}
            )
            return httpx.Response(200, json={"success": True, "data": {"id": doc_id}})
        match = re.match(r"/api/v1/knowledge-bases/([^/]+)/knowledge$", path)
        if match and request.method == "GET":
            rows = self.docs.get(match.group(1), [])
            return httpx.Response(
                200, json={"success": True, "data": rows, "total": len(rows)}
            )
        if request.method == "POST" and path == "/api/v1/knowledge-search":
            return httpx.Response(200, json={"success": True, "data": self.search_results})
        match = re.match(r"/api/v1/knowledge-bases/([^/]+)$", path)
        if match and request.method == "DELETE":
            self.docs.pop(match.group(1), None)
            return httpx.Response(200, json={"success": True})
        return httpx.Response(404, json={"success": False})


def _client(fake: FakeWeKnora) -> WeKnoraClient:
    transport = httpx.MockTransport(fake.handler)
    http = httpx.Client(transport=transport)
    return WeKnoraClient(
        base_url="http://weknora.local", api_key="secret", tenant_id="t1", client=http
    )


def test_client_upload_sends_auth_and_body():
    fake = FakeWeKnora()
    client = _client(fake)
    doc_id = client.add_manual_knowledge("kb-1", title="LTV", content="# LTV")

    assert doc_id.startswith("doc-")
    call = next(c for c in fake.calls if c["path"].endswith("/knowledge/manual"))
    assert call["headers"]["x-api-key"] == "secret"
    assert call["headers"]["x-tenant-id"] == "t1"
    assert call["body"] == {"title": "LTV", "content": "# LTV", "status": "publish"}


def test_client_search_returns_results():
    fake = FakeWeKnora()
    fake.search_results = [
        {
            "id": "chunk-1",
            "knowledge_id": "doc-1",
            "knowledge_title": "LTV",
            "content": "snippet",
            "score": 0.9,
        }
    ]
    client = _client(fake)
    results = client.knowledge_search(
        query="ltv", knowledge_base_ids=["kb-1"], match_count=5
    )
    assert results[0]["knowledge_id"] == "doc-1"
    call = next(c for c in fake.calls if c["path"] == "/api/v1/knowledge-search")
    assert call["body"]["query"] == "ltv"
    assert call["body"]["knowledge_base_ids"] == ["kb-1"]


def test_client_health():
    fake = FakeWeKnora()
    assert _client(fake).health() is True


def _concept(cid: str) -> Concept:
    return Concept(
        frontmatter={"type": "业务知识", "title": cid.split("/")[-1], "status": "stable"},
        body=f"body of {cid}",
        id=cid,
    )


def test_backend_create_snapshot_uploads_and_polls_ready():
    fake = FakeWeKnora()
    backend = WeKnoraBackend(_client(fake))
    ref = backend.create_snapshot([_concept("knowledge/a"), _concept("knowledge/b")], label="c1")

    uploads = [c for c in fake.calls if c["path"].endswith("/knowledge/manual")]
    assert len(uploads) == 2

    progress = backend.poll(ref)
    assert progress.status == READY
    assert progress.total == 2
    assert set(progress.concept_docs) == {"knowledge/a", "knowledge/b"}


def test_backend_create_snapshot_passes_embedding_model_id():
    fake = FakeWeKnora()
    backend = WeKnoraBackend(_client(fake), embedding_model_id="emb-1")
    backend.create_snapshot([_concept("knowledge/a")], label="c1")
    call = next(c for c in fake.calls if c["path"] == "/api/v1/knowledge-bases")
    assert call["body"]["embedding_model_id"] == "emb-1"


def test_backend_create_snapshot_omits_empty_embedding_model_id():
    fake = FakeWeKnora()
    backend = WeKnoraBackend(_client(fake))
    backend.create_snapshot([_concept("knowledge/a")], label="c1")
    call = next(c for c in fake.calls if c["path"] == "/api/v1/knowledge-bases")
    assert "embedding_model_id" not in call["body"]


def test_backend_search_maps_knowledge_id_to_doc_ref():
    fake = FakeWeKnora()
    backend = WeKnoraBackend(_client(fake))
    ref = backend.create_snapshot([_concept("knowledge/a")], label="c1")
    fake.search_results = [
        {
            "id": "chunk-1",
            "knowledge_id": mock_doc_id(fake),
            "knowledge_title": "A",
            "content": "snippet",
            "score": 0.7,
        }
    ]

    hits = backend.search("a", ref=ref, top_k=3)
    assert hits[0].doc_ref == mock_doc_id(fake)
    assert hits[0].title == "A"
    assert hits[0].score == 0.7


def mock_doc_id(fake: FakeWeKnora) -> str:
    for rows in fake.docs.values():
        if rows:
            return rows[0]["id"]
    raise AssertionError("no uploaded document")


def test_backend_delete_snapshot_and_capabilities():
    fake = FakeWeKnora()
    backend = WeKnoraBackend(_client(fake))
    ref = backend.create_snapshot([_concept("knowledge/a")], label="c1")
    backend.delete_snapshot(ref)
    assert any(c["method"] == "DELETE" for c in fake.calls)
    assert backend.capabilities.async_ingest is True
    assert backend.capabilities.supports_code is False
    assert backend.healthcheck() is True


def test_code_kind_unsupported_without_code_engine():
    fake = FakeWeKnora()
    backend = WeKnoraBackend(_client(fake))

    class _Factory:
        def __call__(self):
            raise AssertionError("no session expected")

    service = SnapshotRetrievalService(
        backend=backend, session_factory=_Factory(), kb_id="kb-1", code_engine=None
    )
    with pytest.raises(KeyError):
        service.search("x", kind="code")


def test_config_parses_weknora_settings():
    from mykb.config import load_settings

    settings = load_settings(
        {
            "DATABASE_URL": "sqlite://",
            "JWT_SECRET": "x",
            "MYKB_SECRET_KEY": "y",
            "MYKB_WEKNORA_URL": "http://w",
            "MYKB_WEKNORA_KEY": "k",
            "MYKB_WEKNORA_TENANT_ID": "t",
            "MYKB_WEKNORA_RETENTION": "5",
        }
    )
    assert settings.weknora_url == "http://w"
    assert settings.weknora_key == "k"
    assert settings.weknora_tenant_id == "t"
    assert settings.weknora_retention == 5


def test_backend_selection_local_vs_weknora():
    from mykb.config import load_settings
    from mykb.retrieval.engines.local import LocalBackend
    from mykb.retrieval.service import build_knowledge_backend

    base = {"DATABASE_URL": "sqlite://", "JWT_SECRET": "x", "MYKB_SECRET_KEY": "y"}
    assert isinstance(build_knowledge_backend(load_settings(base)), LocalBackend)
    remote = build_knowledge_backend(
        load_settings({**base, "MYKB_WEKNORA_URL": "http://w"})
    )
    assert isinstance(remote, WeKnoraBackend)
