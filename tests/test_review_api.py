from __future__ import annotations

from fastapi.testclient import TestClient

from mykb.api.app import create_app
from mykb.okf.bundle import Bundle
from mykb.okf.model import Concept


def test_review_flow_list_diff_approve(tmp_path):
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout()

    source_id = bundle.write_concept(
        Concept(
            frontmatter={"type": "源数据", "title": "LTV", "resource": "https://wiki/ltv"},
            body="90 day LTV is computed per customer.",
        ),
        "raw",
        "wiki/ltv",
    )
    draft_id = bundle.write_concept(
        Concept(
            frontmatter={
                "type": "业务知识",
                "title": "LTV 业务知识",
                "status": "draft",
                "generated": {"by": "ai:fake-llm", "at": "2026-01-01T00:00:00Z"},
                "sources": [{"id": source_id}],
            },
            body="# LTV\n\n90 day LTV aggregate across orders.\n",
        ),
        "knowledge",
        "finance/ltv",
    )

    client = TestClient(create_app(bundle.root))

    drafts = client.get("/review/drafts").json()["drafts"]
    assert any(d["concept_id"] == draft_id for d in drafts)

    diff = client.get("/review/diff", params={"concept_id": draft_id}).json()["diff"]
    assert "aggregate across orders" in diff

    approved = client.post(
        "/review/approve", params={"concept_id": draft_id, "reviewer": "bob"}
    ).json()
    assert approved["approved"] is True

    loaded = bundle.read_concept(draft_id)
    assert loaded.status == "stable"
    assert loaded.verified[-1]["by"] == "human:bob"

    remaining = client.get("/review/drafts").json()["drafts"]
    assert all(d["concept_id"] != draft_id for d in remaining)

    # Approved knowledge is now retrievable through the unified interface.
    hits = client.get("/retrieve", params={"q": "ltv"}).json()["hits"]
    assert any(hit["concept_id"] == draft_id for hit in hits)
