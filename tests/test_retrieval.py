from __future__ import annotations

import json
import subprocess

import httpx
import pytest

from mykb.extraction.code_ref import create_code_source
from mykb.okf.bundle import Bundle
from mykb.okf.model import Concept
from mykb.retrieval.engines.codegraph import LocalCodeGraph
from mykb.retrieval.engines.markdown_rag import LocalMarkdownRAG, WeKnoraAdapter
from mykb.retrieval.index import select_indexable_knowledge
from mykb.retrieval.interface import RetrievalHit, RetrievalService
from mykb.retrieval.sync import IndexSync, get_head_commit


class RecordingEngine:
    name = "recording"

    def __init__(self) -> None:
        self.version: str | None = None
        self.indexed: list[str] = []

    def index(self, concepts: list[Concept], *, version: str | None = None) -> None:
        self.indexed = [c.id or "" for c in concepts]
        self.version = version

    def search(self, query: str, *, top_k: int = 5) -> list[RetrievalHit]:
        return []


def _bundle(tmp_path) -> Bundle:
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout()
    return bundle


def _knowledge(bundle, rel, *, status="stable", verified=True, body="90 day LTV aggregate"):
    fm = {"type": "业务知识", "title": rel.split("/")[-1], "status": status}
    if verified:
        fm["verified"] = [{"by": "human:alice", "at": "2026-01-01T00:00:00Z"}]
    return bundle.write_concept(Concept(frontmatter=fm, body=body), "knowledge", rel)


def test_only_verified_stable_knowledge_is_indexed(tmp_path):
    bundle = _bundle(tmp_path)
    verified_id = _knowledge(bundle, "finance/ltv")
    _knowledge(bundle, "finance/draft", status="draft", verified=False)
    bundle.write_concept(Concept(frontmatter={"type": "源数据"}, body="raw"), "raw", "wiki/x")

    assert [c.id for c in select_indexable_knowledge(bundle)] == [verified_id]

    engine = RecordingEngine()
    IndexSync(bundle, [engine]).sync()
    assert engine.indexed == [verified_id]


def test_unified_interface_returns_stable_shape_and_swaps_engines(tmp_path):
    bundle = _bundle(tmp_path)
    _knowledge(bundle, "finance/ltv", body="90 day LTV aggregate across orders")

    engine_a = LocalMarkdownRAG()
    IndexSync(bundle, [engine_a]).sync()
    service = RetrievalService(knowledge_engine=engine_a)
    response = service.search("ltv")
    assert response.engine == "local-markdown-rag"
    assert response.hits and response.hits[0].concept_id == "knowledge/finance/ltv"

    engine_b = LocalMarkdownRAG()
    IndexSync(bundle, [engine_b]).sync()
    service_b = RetrievalService(knowledge_engine=engine_b)
    response_b = service_b.search("ltv")
    assert response_b.hits[0].concept_id == response.hits[0].concept_id

    with pytest.raises(KeyError):
        service.search("ltv", kind="unknown")


def test_weknora_adapter_sends_and_parses():
    captured: dict[str, dict] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/index"):
            captured["index"] = json.loads(request.content)
            return httpx.Response(200, json={"ok": True})
        if request.url.path.endswith("/search"):
            captured["search"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={"hits": [{"id": "knowledge/x", "title": "X", "snippet": "s", "score": 0.9}]},
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = WeKnoraAdapter(base_url="http://weknora.local", client=client)
    adapter.index(
        [Concept(frontmatter={"type": "业务知识"}, body="b", id="knowledge/x")], version="v1"
    )
    hits = adapter.search("query")

    assert captured["index"]["version"] == "v1"
    assert captured["index"]["documents"][0]["id"] == "knowledge/x"
    assert hits[0].concept_id == "knowledge/x"
    assert hits[0].engine == "weknora"


def test_versioned_sync_binds_current_commit(tmp_path):
    bundle = _bundle(tmp_path)
    _knowledge(bundle, "finance/ltv")
    subprocess.run(["git", "-C", str(bundle.root), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(bundle.root), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(bundle.root), "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    head = get_head_commit(bundle.root)
    assert head

    sync = IndexSync(bundle, [RecordingEngine()])
    record = sync.sync()
    assert record.version == head
    assert sync.latest()["version"] == head
    assert len(sync.history()) == 1


def test_codegraph_returns_symbol_hits(tmp_path):
    bundle = _bundle(tmp_path)
    create_code_source(bundle, resource="https://git/repo/orders.py", title="order_ltv")
    code_engine = LocalCodeGraph()
    knowledge_engine = LocalMarkdownRAG()
    IndexSync(bundle, [knowledge_engine], code_engine=code_engine).sync()

    service = RetrievalService(knowledge_engine=knowledge_engine, code_engine=code_engine)
    response = service.search("order_ltv", kind="code")
    assert response.engine == "local-codegraph"
    assert response.hits and response.hits[0].concept_id.startswith("raw/code/")


def test_api_retrieve_uses_unified_interface(client):
    from tests.helpers import create_kb, register

    headers = register(client, "retrieval-user")
    kb = create_kb(client, headers, "api-retrieval")
    bundle = Bundle(kb["local_path"])
    _knowledge(bundle, "finance/ltv", body="90 day LTV aggregate across orders")

    body = client.get(
        f"/kbs/{kb['id']}/retrieve", params={"q": "ltv"}, headers=headers
    ).json()
    assert body["engine"] == "local-markdown-rag"
    assert body["hits"][0]["concept_id"] == "knowledge/finance/ltv"
