from __future__ import annotations

import time

from mykb.okf.bundle import Bundle
from mykb.okf.model import Concept
from tests.helpers import create_kb, register


def _verified(bundle: Bundle, rel: str, body: str) -> str:
    return bundle.write_concept(
        Concept(
            frontmatter={
                "type": "业务知识",
                "title": rel,
                "status": "stable",
                "verified": [{"by": "human:alice"}],
            },
            body=body,
        ),
        "knowledge",
        rel,
    )


def _wait(client, headers, kb_id: str, task_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    body: dict = {}
    while time.time() < deadline:
        body = client.get(
            f"/kbs/{kb_id}/publish/{task_id}", headers=headers
        ).json()
        if body["status"] in ("ready", "failed"):
            return body
        time.sleep(0.05)
    return body


def test_publish_then_retrieve_end_to_end(client):
    headers = register(client, "e2e-publish")
    kb = create_kb(client, headers, "e2e-publish-kb")
    concept_id = _verified(
        Bundle(kb["local_path"]), "finance/ltv", "ltv unique marker"
    )

    response = client.post(f"/kbs/{kb['id']}/publish", headers=headers)
    assert response.status_code == 202, response.text
    task_id = response.json()["task_id"]

    done = _wait(client, headers, kb["id"], task_id)
    assert done["status"] == "ready", done
    assert done["doc_total"] == 1 and done["doc_completed"] == 1

    hits = client.get(
        f"/kbs/{kb['id']}/retrieve", params={"q": "unique"}, headers=headers
    ).json()["hits"]
    assert any(
        hit["concept_id"] == concept_id and hit["engine"] == "local-markdown-rag"
        for hit in hits
    )

    versions = client.get(f"/kbs/{kb['id']}/versions", headers=headers).json()[
        "versions"
    ]
    active = [version for version in versions if version["is_active"]]
    assert len(active) == 1
    assert active[0]["id"] == done["version_id"]
