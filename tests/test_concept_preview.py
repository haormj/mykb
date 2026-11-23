from __future__ import annotations

from pathlib import Path

from mykb.okf.bundle import Bundle
from mykb.okf.model import Concept
from tests.helpers import create_kb, register

PNG = b"\x89PNG\r\n\x1a\nfake-image"


def _seed(client):
    headers = register(client)
    kb = create_kb(client, headers, name="kb")
    bundle = Bundle(Path(kb["local_path"]))
    bundle.write_concept(
        Concept(frontmatter={"type": "源数据", "title": "Doc"}, body="# Doc\n\nhello raw"),
        "raw",
        "upload/doc",
    )
    bundle.write_concept(
        Concept(frontmatter={"type": "业务知识", "title": "Biz"}, body="# Biz\n\nhello knowledge"),
        "knowledge",
        "topics/biz",
    )
    return headers, kb, bundle


def _content(client, headers, kb_id, concept_id):
    return client.get(
        f"/kbs/{kb_id}/concepts/content",
        params={"concept_id": concept_id},
        headers=headers,
    )


def _asset(client, headers, kb_id, concept_id, name):
    return client.get(
        f"/kbs/{kb_id}/concepts/asset",
        params={"concept_id": concept_id, "name": name},
        headers=headers,
    )


def test_content_reads_raw_and_knowledge(client):
    headers, kb, _ = _seed(client)

    raw = _content(client, headers, kb["id"], "raw/upload/doc")
    assert raw.status_code == 200, raw.text
    assert raw.json() == {
        "concept_id": "raw/upload/doc",
        "level": "raw",
        "title": "Doc",
        "body": "# Doc\n\nhello raw",
    }

    knowledge = _content(client, headers, kb["id"], "knowledge/topics/biz")
    assert knowledge.status_code == 200, knowledge.text
    assert knowledge.json()["level"] == "knowledge"
    assert knowledge.json()["body"] == "# Biz\n\nhello knowledge"


def test_content_rejects_non_member(client):
    _headers, kb, _ = _seed(client)
    bob = register(client, "bob")

    response = _content(client, bob, kb["id"], "raw/upload/doc")

    assert response.status_code == 403


def test_content_requires_authentication(client):
    _headers, kb, _ = _seed(client)

    response = client.get(
        f"/kbs/{kb['id']}/concepts/content", params={"concept_id": "raw/upload/doc"}
    )

    assert response.status_code == 401


def test_content_missing_and_cross_kb(client):
    headers, kb, _ = _seed(client)

    assert _content(client, headers, kb["id"], "raw/upload/missing").status_code == 404
    assert _content(client, headers, kb["id"], "raw/index").status_code == 404
    assert _content(client, headers, kb["id"], "../escape").status_code == 404

    other = create_kb(client, headers, name="other")
    other_bundle = Bundle(Path(other["local_path"]))
    other_bundle.write_concept(
        Concept(frontmatter={"type": "源数据"}, body="only in other"), "raw", "only2"
    )
    response = _content(client, headers, kb["id"], "raw/only2")
    assert response.status_code == 404


def test_asset_serves_image(client):
    headers, kb, bundle = _seed(client)
    directory = bundle.asset_dir_for("raw", "upload/doc")
    directory.mkdir(parents=True)
    (directory / "001-abc.png").write_bytes(PNG)

    response = _asset(client, headers, kb["id"], "raw/upload/doc", "001-abc.png")

    assert response.status_code == 200, response.text
    assert response.content == PNG
    assert response.headers["content-type"].startswith("image/png")


def test_asset_rejects_traversal_and_missing(client):
    headers, kb, bundle = _seed(client)
    directory = bundle.asset_dir_for("raw", "upload/doc")
    directory.mkdir(parents=True)
    (bundle.root / "raw" / "upload" / "secret.png").write_bytes(PNG)

    assert _asset(client, headers, kb["id"], "raw/upload/doc", "../secret.png").status_code == 404
    assert _asset(client, headers, kb["id"], "raw/upload/doc", "missing.png").status_code == 404


def test_asset_rejects_cross_concept_read(client):
    headers, kb, bundle = _seed(client)
    bundle.write_concept(
        Concept(frontmatter={"type": "源数据"}), "raw", "upload/other"
    )
    other_dir = bundle.asset_dir_for("raw", "upload/other")
    other_dir.mkdir(parents=True)
    (other_dir / "only-other.png").write_bytes(PNG)
    bundle.asset_dir_for("raw", "upload/doc").mkdir(parents=True)

    response = _asset(client, headers, kb["id"], "raw/upload/doc", "only-other.png")

    assert response.status_code == 404


def test_asset_rejects_non_member_and_anonymous(client):
    _headers, kb, bundle = _seed(client)
    directory = bundle.asset_dir_for("raw", "upload/doc")
    directory.mkdir(parents=True)
    (directory / "001-abc.png").write_bytes(PNG)
    bob = register(client, "bob")

    assert _asset(client, bob, kb["id"], "raw/upload/doc", "001-abc.png").status_code == 403
    assert (
        client.get(
            f"/kbs/{kb['id']}/concepts/asset",
            params={"concept_id": "raw/upload/doc", "name": "001-abc.png"},
        ).status_code
        == 401
    )
