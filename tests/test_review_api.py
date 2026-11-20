from __future__ import annotations

from mykb.okf.bundle import Bundle
from mykb.okf.model import Concept
from tests.helpers import create_kb, register


def test_review_flow_list_diff_approve(client):
    headers = register(client, "reviewer")
    kb = create_kb(client, headers, "review-kb")
    bundle = Bundle(kb["local_path"])

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

    base = f"/kbs/{kb['id']}/review"
    drafts = client.get(f"{base}/drafts", headers=headers).json()["drafts"]
    assert any(d["concept_id"] == draft_id for d in drafts)

    diff = client.get(
        f"{base}/diff", params={"concept_id": draft_id}, headers=headers
    ).json()["diff"]
    assert "aggregate across orders" in diff

    approved = client.post(
        f"{base}/approve",
        params={"concept_id": draft_id, "reviewer": "bob"},
        headers=headers,
    ).json()
    assert approved["approved"] is True

    loaded = bundle.read_concept(draft_id)
    assert loaded.status == "stable"
    assert loaded.verified[-1]["by"] == "human:bob"

    remaining = client.get(f"{base}/drafts", headers=headers).json()["drafts"]
    assert all(d["concept_id"] != draft_id for d in remaining)

    hits = client.get(
        f"/kbs/{kb['id']}/retrieve", params={"q": "ltv"}, headers=headers
    ).json()["hits"]
    assert any(hit["concept_id"] == draft_id for hit in hits)
