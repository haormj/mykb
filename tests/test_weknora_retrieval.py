from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from mykb.db.models import (
    KnowledgeBase,
    PublishTask,
    User,
    WeKnoraConceptMap,
    WeKnoraIndexVersion,
)


def _make_kb(session, name: str = "kb1") -> KnowledgeBase:
    user = User(username=f"owner-{name}", display_name="Owner")
    session.add(user)
    session.flush()
    kb = KnowledgeBase(
        name=name,
        slug=name,
        local_path=f"/tmp/{name}",
        owner_id=user.id,
    )
    session.add(kb)
    session.flush()
    return kb


def test_version_unique_per_kb_and_commit(app):
    factory = app.state.session_factory
    with factory() as session:
        kb = _make_kb(session)
        session.add(
            WeKnoraIndexVersion(kb_id=kb.id, git_commit="c1", weknora_kb_id="w1")
        )
        session.commit()

        session.add(
            WeKnoraIndexVersion(kb_id=kb.id, git_commit="c1", weknora_kb_id="w2")
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_version_weknora_kb_id_is_unique(app):
    factory = app.state.session_factory
    with factory() as session:
        kb = _make_kb(session)
        session.add(
            WeKnoraIndexVersion(kb_id=kb.id, git_commit="c1", weknora_kb_id="w1")
        )
        session.commit()

        session.add(
            WeKnoraIndexVersion(kb_id=kb.id, git_commit="c2", weknora_kb_id="w1")
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_concept_map_unique_per_version_and_concept(app):
    factory = app.state.session_factory
    with factory() as session:
        kb = _make_kb(session)
        version = WeKnoraIndexVersion(
            kb_id=kb.id, git_commit="c1", weknora_kb_id="w1"
        )
        session.add(version)
        session.flush()
        session.add(
            WeKnoraConceptMap(
                version_id=version.id, concept_id="knowledge/x", doc_ref="d1"
            )
        )
        session.commit()

        session.add(
            WeKnoraConceptMap(
                version_id=version.id, concept_id="knowledge/x", doc_ref="d2"
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_deleting_version_cascades_concept_maps(app):
    factory = app.state.session_factory
    with factory() as session:
        kb = _make_kb(session)
        version = WeKnoraIndexVersion(
            kb_id=kb.id, git_commit="c1", weknora_kb_id="w1"
        )
        session.add(version)
        session.flush()
        session.add(
            WeKnoraConceptMap(
                version_id=version.id, concept_id="knowledge/x", doc_ref="d1"
            )
        )
        session.commit()

        session.delete(version)
        session.commit()

        remaining = session.scalar(
            select(func.count()).select_from(WeKnoraConceptMap)
        )
        assert remaining == 0


def test_publish_task_status_machine(app):
    from mykb.db.models import PublishTask
    from mykb.retrieval.tasks import (
        ACTIVATING,
        BUILDING,
        INDEXING,
        QUEUED,
        READY,
        InvalidTransition,
        advance,
    )

    factory = app.state.session_factory
    with factory() as session:
        kb = _make_kb(session)
        task = PublishTask(kb_id=kb.id, git_commit="c1", status=QUEUED)
        session.add(task)
        session.flush()

        advance(task, BUILDING)
        advance(task, INDEXING)
        advance(task, ACTIVATING)
        advance(task, READY)
        assert task.status == READY

        with pytest.raises(InvalidTransition):
            advance(task, BUILDING)


def test_publish_task_failed_is_terminal(app):
    from mykb.db.models import PublishTask
    from mykb.retrieval.tasks import BUILDING, FAILED, QUEUED, InvalidTransition, advance

    factory = app.state.session_factory
    with factory() as session:
        kb = _make_kb(session)
        task = PublishTask(kb_id=kb.id, git_commit="c2", status=QUEUED)
        session.add(task)
        session.flush()
        advance(task, BUILDING)
        advance(task, FAILED)
        assert task.status == FAILED
        with pytest.raises(InvalidTransition):
            advance(task, BUILDING)


def _write_knowledge(bundle, rel: str, body: str) -> str:
    from mykb.okf.model import Concept

    return bundle.write_concept(
        Concept(
            frontmatter={
                "type": "业务知识",
                "title": rel.split("/")[-1],
                "status": "stable",
                "verified": [{"by": "human:alice"}],
            },
            body=body,
        ),
        "knowledge",
        rel,
    )


class _BlockingBackend:
    def __init__(self, inner, release, started):
        self.inner = inner
        self.release = release
        self.started = started
        self.name = inner.name
        self.capabilities = inner.capabilities

    def create_snapshot(self, concepts, *, label=None):
        return self.inner.create_snapshot(concepts, label=label)

    def poll(self, ref):
        self.started.set()
        self.release.wait(timeout=10)
        return self.inner.poll(ref)

    def search(self, query, *, ref, top_k=5):
        return self.inner.search(query, ref=ref, top_k=top_k)

    def delete_snapshot(self, ref):
        return self.inner.delete_snapshot(ref)

    def healthcheck(self):
        return self.inner.healthcheck()


def test_publish_task_serves_old_active_until_ready(client, app):
    import threading

    from mykb.okf.bundle import Bundle
    from mykb.retrieval.index import select_indexable_knowledge
    from mykb.retrieval.publish import SnapshotPublisher
    from mykb.retrieval.tasks import run_publish_task
    from tests.helpers import create_kb, register

    headers = register(client, "publish-owner")
    kb = create_kb(client, headers, "publish-kb")
    bundle = Bundle(kb["local_path"])
    _write_knowledge(bundle, "finance/old", "oldterm unique")

    factory = app.state.session_factory
    inner = app.state.retrieval_backend
    with factory() as session:
        SnapshotPublisher(inner, sleep=lambda _s: None).publish(
            session,
            kb_id=kb["id"],
            concepts=select_indexable_knowledge(bundle),
            git_commit="c1",
        )

    _write_knowledge(bundle, "finance/new", "newterm unique")

    with factory() as session:
        task = PublishTask(kb_id=kb["id"], git_commit="c2", status="queued")
        session.add(task)
        session.commit()
        task_id = task.id

    release = threading.Event()
    started = threading.Event()
    blocking = _BlockingBackend(inner, release, started)
    thread = threading.Thread(
        target=run_publish_task,
        kwargs={
            "task_id": task_id,
            "session_factory": factory,
            "backend": blocking,
            "retention": 3,
            "sleep": lambda _s: None,
        },
        daemon=True,
    )
    thread.start()
    assert started.wait(5)

    during = client.get(
        f"/kbs/{kb['id']}/retrieve", params={"q": "unique"}, headers=headers
    ).json()["hits"]
    assert {hit["concept_id"] for hit in during} == {"knowledge/finance/old"}

    release.set()
    thread.join(10)

    after = client.get(
        f"/kbs/{kb['id']}/retrieve", params={"q": "unique"}, headers=headers
    ).json()["hits"]
    assert {"knowledge/finance/old", "knowledge/finance/new"} <= {
        hit["concept_id"] for hit in after
    }
    with factory() as session:
        assert session.get(PublishTask, task_id).status == "ready"


def _wait_publish(client, headers, kb_id, task_id, timeout=5.0):
    import time

    deadline = time.time() + timeout
    body = {}
    while time.time() < deadline:
        body = client.get(
            f"/kbs/{kb_id}/publish/{task_id}", headers=headers
        ).json()
        if body["status"] in ("ready", "failed"):
            return body
        time.sleep(0.05)
    return body


def test_publish_endpoint_owner_status_and_outsider(client):
    from mykb.okf.bundle import Bundle
    from tests.helpers import create_kb, register

    headers = register(client, "pub-owner")
    kb = create_kb(client, headers, "pub-endpoint-kb")
    _write_knowledge(Bundle(kb["local_path"]), "finance/ltv", "ltv unique term")

    response = client.post(f"/kbs/{kb['id']}/publish", headers=headers)
    assert response.status_code == 202, response.text
    task_id = response.json()["task_id"]

    status = client.get(
        f"/kbs/{kb['id']}/publish/{task_id}", headers=headers
    ).json()
    assert status["task_id"] == task_id
    assert "doc_total" in status and "status" in status

    done = _wait_publish(client, headers, kb["id"], task_id)
    assert done["status"] == "ready", done

    hits = client.get(
        f"/kbs/{kb['id']}/retrieve", params={"q": "unique"}, headers=headers
    ).json()["hits"]
    assert any(hit["concept_id"] == "knowledge/finance/ltv" for hit in hits)

    outsider = register(client, "pub-outsider")
    assert (
        client.post(f"/kbs/{kb['id']}/publish", headers=outsider).status_code == 403
    )


def test_publish_endpoint_rejects_concurrent(client, app):
    from tests.helpers import create_kb, register

    headers = register(client, "pub-concurrent")
    kb = create_kb(client, headers, "pub-concurrent-kb")
    with app.state.session_factory() as session:
        session.add(
            PublishTask(kb_id=kb["id"], git_commit="c1", status="building")
        )
        session.commit()

    response = client.post(f"/kbs/{kb['id']}/publish", headers=headers)
    assert response.status_code == 409


def test_versions_endpoint_marks_active(client):
    from mykb.okf.bundle import Bundle
    from tests.helpers import create_kb, publish_current, register

    headers = register(client, "versions-owner")
    kb = create_kb(client, headers, "versions-kb")
    _write_knowledge(Bundle(kb["local_path"]), "finance/ltv", "ltv unique term")
    published = publish_current(client, kb)

    versions = client.get(f"/kbs/{kb['id']}/versions", headers=headers).json()[
        "versions"
    ]
    assert any(
        item["id"] == published["id"] and item["is_active"] for item in versions
    )


def test_index_sync_route_removed(client):
    from tests.helpers import create_kb, register

    headers = register(client, "old-route-owner")
    kb = create_kb(client, headers, "old-route-kb")
    assert client.post(f"/kbs/{kb['id']}/index-sync", headers=headers).status_code == 404


def test_cli_publish_command():
    from mykb.cli import build_parser

    args = build_parser().parse_args(["publish", "kb-1"])
    assert args.command == "publish"
    assert args.kb_id == "kb-1"
    with pytest.raises(SystemExit):
        build_parser().parse_args(["sync-index", "."])
