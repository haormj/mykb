from __future__ import annotations

import time
from pathlib import Path

from mykb.db.models import ExtractionItem
from mykb.extraction.drafter import Drafter
from mykb.extraction.harness import (
    apply_concept,
    build_concept,
    semantic_signature,
    validate_concept,
)
from mykb.extraction.llm import FakeLLM
from mykb.extraction.queue import claim_next, enqueue_item, recover_processing
from mykb.maintenance.audit import run_audit
from mykb.okf.bundle import Bundle
from mykb.okf.model import Concept
from tests.helpers import create_kb, publish_current, register


def _wait_for_review(client, headers, kb_id: str, timeout: float = 10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        mrs = client.get(f"/kbs/{kb_id}/review/mrs", headers=headers).json()["mrs"]
        ready = [mr for mr in mrs if mr["status"] == "reviewing"]
        if ready:
            tasks = client.get(f"/kbs/{kb_id}/import-tasks", headers=headers).json()["tasks"]
            return ready[0], tasks[0] if tasks else None
        tasks = client.get(f"/kbs/{kb_id}/import-tasks", headers=headers).json()["tasks"]
        if tasks and tasks[0]["status"] in ("failed", "cancelled", "succeeded"):
            raise AssertionError(f"no MR produced; task={tasks[0]}")
        time.sleep(0.05)
    raise AssertionError("timed out waiting for a review MR")


def _wait_status(client, headers, kb_id, statuses, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        tasks = client.get(f"/kbs/{kb_id}/import-tasks", headers=headers).json()["tasks"]
        if tasks and tasks[0]["status"] in statuses:
            return tasks[0]
        time.sleep(0.05)
    raise AssertionError(f"task did not reach {statuses}")


def test_import_review_approve_flow(client):
    headers = register(client, "pipeline-owner")
    kb = create_kb(client, headers, "pipeline-kb")
    path = Path(kb["local_path"])
    main_before = _git(path, "rev-parse", "main")

    response = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("note.md", b"# LTV\n\n90 day LTV per customer", "text/markdown"))],
        headers=headers,
    )
    assert response.status_code == 201, response.text

    mr, _task = _wait_for_review(client, headers, kb["id"])
    assert mr["status"] == "reviewing"
    assert mr["action"] == "add"
    assert mr["concept_id"] == "raw/upload/note"

    # Main is untouched until the MR is merged.
    assert _git(path, "rev-parse", "main") == main_before
    assert not (path / "raw" / "upload" / "note.md").exists()

    diff = client.get(
        f"/kbs/{kb['id']}/review/mrs/{mr['item_id']}/diff", headers=headers
    ).json()
    assert "raw/upload/note.md" in diff["files"]
    assert any(name.startswith("knowledge/") for name in diff["files"])

    approved = client.post(
        f"/kbs/{kb['id']}/review/mrs/{mr['item_id']}/approve",
        params={"reviewer": "alice"},
        headers=headers,
    )
    assert approved.status_code == 200, approved.text

    _wait_status(client, headers, kb["id"], {"merged", "succeeded"})
    bundle = Bundle(path)
    raw = bundle.read_concept("raw/upload/note")
    assert raw.type == "源数据"
    knowledge = [c for _, c in bundle.iter_concepts("knowledge")]
    assert knowledge and all(c.is_verified_stable() for c in knowledge)
    assert knowledge[0].frontmatter["claims"][0]["sources"] == ["raw/upload/note"]
    assert knowledge[0].frontmatter["x-extraction"]["model"] == "fake-llm"

    publish_current(client, kb)

    hits = client.get(
        f"/kbs/{kb['id']}/retrieve", params={"q": "LTV"}, headers=headers
    ).json()["hits"]
    assert hits


def test_reimport_same_content_is_skipped(client):
    headers = register(client, "skip-owner")
    kb = create_kb(client, headers, "skip-kb")
    payload = b"# Same\n\nunchanged"

    client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("same.md", payload, "text/markdown"))],
        headers=headers,
    )
    mr, _ = _wait_for_review(client, headers, kb["id"])
    client.post(
        f"/kbs/{kb['id']}/review/mrs/{mr['item_id']}/approve",
        params={"reviewer": "alice"},
        headers=headers,
    )
    _wait_status(client, headers, kb["id"], {"merged", "succeeded"})

    client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("same.md", payload, "text/markdown"))],
        headers=headers,
    )
    task = _wait_status(client, headers, kb["id"], {"succeeded", "partial", "failed"})
    assert task["skipped"] == 1
    assert task["added"] == 0


def test_delete_document_revises_knowledge(client):
    headers = register(client, "delete-owner")
    kb = create_kb(client, headers, "delete-kb")
    path = Path(kb["local_path"])

    client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("gone.md", b"# Gone\n\nonly source", "text/markdown"))],
        headers=headers,
    )
    mr, _ = _wait_for_review(client, headers, kb["id"])
    client.post(
        f"/kbs/{kb['id']}/review/mrs/{mr['item_id']}/approve",
        params={"reviewer": "alice"},
        headers=headers,
    )
    _wait_status(client, headers, kb["id"], {"merged", "succeeded"})
    bundle = Bundle(path)
    knowledge_ids = [cid for cid, _ in bundle.iter_concepts("knowledge")]
    assert knowledge_ids

    deleted = client.delete(
        f"/kbs/{kb['id']}/documents/raw/upload/gone.md", headers=headers
    )
    assert deleted.status_code == 200, deleted.text
    delete_mr, _ = _wait_for_review(client, headers, kb["id"])
    assert delete_mr["action"] == "delete"

    delete_approved = client.post(
        f"/kbs/{kb['id']}/review/mrs/{delete_mr['item_id']}/approve",
        params={"reviewer": "alice"},
        headers=headers,
    )
    assert delete_approved.status_code == 200, delete_approved.text
    finished = _wait_status(client, headers, kb["id"], {"merged", "succeeded"})
    assert finished
    assert not bundle.path_for_id("raw/upload/gone").exists()
    assert not [cid for cid, _ in bundle.iter_concepts("knowledge")]


def test_harness_validation_and_idempotent_apply(tmp_path):
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout()
    source_id = bundle.write_concept(
        Concept(frontmatter={"type": "源数据", "title": "LTV"}, body="LTV body"),
        "raw",
        "upload/ltv",
    )
    drafter = Drafter(bundle, FakeLLM())
    concept = drafter.propose_concept([source_id], task_id="t1")
    assert concept.frontmatter["claims"]
    assert concept.frontmatter["x-extraction"]["source_hash"]

    bad = build_concept(
        {"title": "bad", "claims": [{"text": "x", "sources": ["raw/missing"]}]},
        source_ids=[source_id],
        source_meta={},
        model="fake-llm",
        source_hash="h",
    )
    assert validate_concept(bad, bundle)
    with_unknown = [i for i in validate_concept(bad, bundle) if "unknown source" in i]
    assert with_unknown

    concept_id, changed = apply_concept(bundle, concept, "knowledge", "topics/ltv")
    assert changed
    _, changed_again = apply_concept(bundle, concept, "knowledge", "topics/ltv")
    assert not changed_again
    loaded = bundle.read_concept(concept_id)
    assert semantic_signature(loaded) == semantic_signature(concept)


def test_modify_reimport_produces_modify_mr(client):
    headers = register(client, "modify-owner")
    kb = create_kb(client, headers, "modify-kb")

    client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("v.md", b"# Doc\n\nfirst version", "text/markdown"))],
        headers=headers,
    )
    mr, _ = _wait_for_review(client, headers, kb["id"])
    client.post(
        f"/kbs/{kb['id']}/review/mrs/{mr['item_id']}/approve",
        params={"reviewer": "alice"},
        headers=headers,
    )
    _wait_status(client, headers, kb["id"], {"merged", "succeeded"})

    client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("v.md", b"# Doc\n\nsecond version", "text/markdown"))],
        headers=headers,
    )
    modify, _ = _wait_for_review(client, headers, kb["id"])
    assert modify["action"] == "modify"
    client.post(
        f"/kbs/{kb['id']}/review/mrs/{modify['item_id']}/approve",
        params={"reviewer": "alice"},
        headers=headers,
    )
    _wait_status(client, headers, kb["id"], {"merged", "succeeded"})
    bundle = Bundle(Path(kb["local_path"]))
    bodies = [c.body for _, c in bundle.iter_concepts("knowledge")]
    assert any("second version" in body for body in bodies)


def test_reject_and_redraft(client):
    headers = register(client, "redraft-owner")
    kb = create_kb(client, headers, "redraft-kb")
    path = Path(kb["local_path"])

    client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("r.md", b"# R\n\ncontent", "text/markdown"))],
        headers=headers,
    )
    first, _ = _wait_for_review(client, headers, kb["id"])
    redrafted = client.post(
        f"/kbs/{kb['id']}/review/mrs/{first['item_id']}/redraft", headers=headers
    )
    assert redrafted.status_code == 200, redrafted.text
    again, _ = _wait_for_review(client, headers, kb["id"])
    assert again["item_id"] == first["item_id"]
    assert again["status"] == "reviewing"

    rejected = client.post(
        f"/kbs/{kb['id']}/review/mrs/{again['item_id']}/reject", headers=headers
    )
    assert rejected.status_code == 200, rejected.text
    assert not (path / "raw" / "upload" / "r.md").exists()
    assert client.get(f"/kbs/{kb['id']}/review/mrs", headers=headers).json()["mrs"] == []


def test_queue_state_machine_and_recovery(client):
    headers = register(client, "queue-owner")
    kb = create_kb(client, headers, "queue-kb")
    app = client.app
    with app.state.session_factory() as session:
        item = enqueue_item(
            session,
            kb_id=kb["id"],
            import_task_id=None,
            concept_id="raw/upload/q",
            action="add",
            source_hash=None,
            title="q",
            created_by=None,
        )
        session.commit()
        item_id = item.id

    with app.state.session_factory() as session:
        claimed = claim_next(session, kb["id"])
        assert claimed is not None and claimed.id == item_id
        assert claimed.status == "processing"

    assert recover_processing(app.state.session_factory) == 1
    with app.state.session_factory() as session:
        recovered = session.get(ExtractionItem, item_id)
        assert recovered is not None and recovered.status == "queued"


def test_page_audit_flags_and_marks_needs_review(tmp_path):
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout()
    source_id = bundle.write_concept(
        Concept(frontmatter={"type": "源数据", "title": "Src"}, body="src body"),
        "raw",
        "upload/src",
    )
    bundle.write_concept(
        Concept(
            frontmatter={
                "type": "业务知识",
                "title": "Audited",
                "status": "stable",
                "sources": [{"id": source_id}],
                "claims": [
                    {"text": "same", "sources": [source_id]},
                    {"text": "same", "sources": [source_id]},
                ],
            },
            body="# Audited\n\n[broken](missing.md)\n",
        ),
        "knowledge",
        "topics/audited",
    )
    issues = run_audit(bundle)
    reasons = " ".join(issue.reason for issue in issues)
    assert "broken link" in reasons
    assert "duplicate claim" in reasons
    assert bundle.read_concept("knowledge/topics/audited").status == "needs-review"


def _git(path: Path, *args: str) -> str:
    import subprocess

    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    ).stdout.strip()
