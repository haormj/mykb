from __future__ import annotations

import uuid

import pytest

from mykb.db.models import KnowledgeBase, User, WeKnoraConceptMap, WeKnoraIndexVersion
from mykb.okf.model import Concept
from mykb.retrieval.backend import (
    READY,
    BuildProgress,
    Capabilities,
    RetrievalBackend,
    SnapshotRef,
)
from mykb.retrieval.publish import (
    RETIRED,
    ActiveResolver,
    ConceptMapStore,
    PublishError,
    SnapshotPublisher,
)


class FakeBackend:
    name = "fake"
    capabilities = Capabilities(async_ingest=False)

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.created: list[SnapshotRef] = []
        self.deleted: list[SnapshotRef] = []
        self._docs: dict[str, dict[str, str]] = {}

    def create_snapshot(self, concepts, *, label=None) -> SnapshotRef:
        ref = SnapshotRef(self.name, f"snap-{uuid.uuid4().hex}", label)
        self.created.append(ref)
        self._docs[ref.snapshot_id] = {
            c.id: f"doc-{c.id}" for c in concepts if c.id
        }
        return ref

    def poll(self, ref: SnapshotRef) -> BuildProgress:
        docs = self._docs[ref.snapshot_id]
        if self.fail:
            return BuildProgress("failed", 0, len(docs), error="boom")
        return BuildProgress(READY, len(docs), len(docs), concept_docs=dict(docs))

    def search(self, query, *, ref, top_k=5):
        return []

    def delete_snapshot(self, ref: SnapshotRef) -> None:
        self.deleted.append(ref)

    def healthcheck(self) -> bool:
        return True


def _concept(cid: str) -> Concept:
    return Concept(
        frontmatter={
            "type": "业务知识",
            "title": cid.split("/")[-1],
            "status": "stable",
            "verified": [{"by": "human:alice"}],
        },
        body="body",
        id=cid,
    )


def _make_kb(session, name: str = "kb1") -> KnowledgeBase:
    user = User(username=f"u-{name}", display_name="Owner")
    session.add(user)
    session.flush()
    kb = KnowledgeBase(name=name, slug=name, local_path=f"/tmp/{name}", owner_id=user.id)
    session.add(kb)
    session.flush()
    return kb


def test_fake_backend_satisfies_protocol():
    assert isinstance(FakeBackend(), RetrievalBackend)
    assert isinstance(FakeBackend().capabilities, Capabilities)


def test_active_resolver_returns_none_without_pointer(app):
    factory = app.state.session_factory
    with factory() as session:
        kb = _make_kb(session)
        assert ActiveResolver().active_version(session, kb.id) is None


def test_active_resolver_after_activate(app):
    factory = app.state.session_factory
    with factory() as session:
        kb = _make_kb(session)
        version = WeKnoraIndexVersion(
            kb_id=kb.id, git_commit="c1", weknora_kb_id="w1", status=READY
        )
        session.add(version)
        session.flush()
        ActiveResolver().activate(session, kb.id, version)
        session.commit()
        resolved = ActiveResolver().active_version(session, kb.id)
        assert resolved is not None and resolved.id == version.id


def test_concept_map_store_doc_to_concept(app):
    factory = app.state.session_factory
    with factory() as session:
        kb = _make_kb(session)
        version = WeKnoraIndexVersion(
            kb_id=kb.id, git_commit="c1", weknora_kb_id="w1", status=READY
        )
        session.add(version)
        session.flush()
        ConceptMapStore().replace_maps(
            session, version, {"knowledge/x": "d1", "knowledge/y": "d2"}
        )
        mapping = ConceptMapStore().doc_to_concept(session, version.id)
        assert mapping == {"d1": "knowledge/x", "d2": "knowledge/y"}


def test_publisher_all_ready_activates_and_maps(app):
    factory = app.state.session_factory
    backend = FakeBackend()
    publisher = SnapshotPublisher(backend, sleep=lambda _s: None)
    with factory() as session:
        kb = _make_kb(session)
        version = publisher.publish(
            session,
            kb_id=kb.id,
            concepts=[_concept("knowledge/x"), _concept("knowledge/y")],
            git_commit="c1",
        )
        assert version.status == READY
        assert len(backend.created) == 1
        resolved = ActiveResolver().active_version(session, kb.id)
        assert resolved.id == version.id
        assert session.query(WeKnoraConceptMap).count() == 2


def test_publisher_failure_keeps_previous_active(app):
    factory = app.state.session_factory
    with factory() as session:
        kb = _make_kb(session)
        good = SnapshotPublisher(FakeBackend(), sleep=lambda _s: None).publish(
            session, kb_id=kb.id, concepts=[_concept("knowledge/old")], git_commit="c1"
        )
        assert ActiveResolver().active_version(session, kb.id).id == good.id

        failing = FakeBackend(fail=True)
        with pytest.raises(PublishError):
            SnapshotPublisher(failing, sleep=lambda _s: None).publish(
                session, kb_id=kb.id, concepts=[_concept("knowledge/new")], git_commit="c2"
            )
        assert ActiveResolver().active_version(session, kb.id).id == good.id
        assert len(failing.deleted) == 1


def test_publisher_idempotent_for_same_commit(app):
    factory = app.state.session_factory
    backend = FakeBackend()
    publisher = SnapshotPublisher(backend, sleep=lambda _s: None)
    with factory() as session:
        kb = _make_kb(session)
        first = publisher.publish(
            session, kb_id=kb.id, concepts=[_concept("knowledge/x")], git_commit="c1"
        )
        second = publisher.publish(
            session, kb_id=kb.id, concepts=[_concept("knowledge/x")], git_commit="c1"
        )
        assert first.id == second.id
        assert len(backend.created) == 1


def test_publisher_retires_versions_beyond_retention(app):
    factory = app.state.session_factory
    backend = FakeBackend()
    publisher = SnapshotPublisher(backend, retention=2, sleep=lambda _s: None)
    with factory() as session:
        kb = _make_kb(session)
        for i in range(1, 4):
            publisher.publish(
                session,
                kb_id=kb.id,
                concepts=[_concept(f"knowledge/c{i}")],
                git_commit=f"c{i}",
            )
        retired = (
            session.query(WeKnoraIndexVersion)
            .filter(WeKnoraIndexVersion.status == RETIRED)
            .all()
        )
        assert len(retired) == 1
        assert len(backend.deleted) == 1


def test_local_backend_snapshot_search_and_delete():
    from mykb.retrieval.engines.local import LocalBackend

    backend = LocalBackend()
    concept = Concept(
        frontmatter={"type": "业务知识", "title": "LTV", "status": "stable"},
        body="90 day LTV aggregate across orders",
        id="knowledge/finance/ltv",
    )
    ref = backend.create_snapshot([concept], label="c1")
    progress = backend.poll(ref)
    assert progress.status == READY
    assert progress.concept_docs == {concept.id: concept.id}

    hits = backend.search("ltv", ref=ref, top_k=5)
    assert hits and hits[0].doc_ref == concept.id

    backend.delete_snapshot(ref)
    assert backend.search("ltv", ref=ref, top_k=5) == []
    assert backend.healthcheck() is True
    assert backend.capabilities.async_ingest is False


def test_rollback_rebuilds_when_version_not_ready(app, monkeypatch, tmp_path):
    from pathlib import Path

    from mykb.maintenance import rollback as rollback_module
    from mykb.maintenance.rollback import IndexRollback
    from mykb.okf.bundle import Bundle

    fake = FakeBackend()
    publisher = SnapshotPublisher(fake, retention=1, sleep=lambda _s: None)
    factory = app.state.session_factory
    with factory() as session:
        kb = _make_kb(session)
        publisher.publish(
            session, kb_id=kb.id, concepts=[_concept("knowledge/a")], git_commit="c1"
        )
        latest = publisher.publish(
            session, kb_id=kb.id, concepts=[_concept("knowledge/b")], git_commit="c2"
        )
        assert ActiveResolver().active_version(session, kb.id).id == latest.id
        kb_id = kb.id

    monkeypatch.setattr(
        rollback_module,
        "concepts_at_commit",
        lambda _bundle, _commit: [_concept("knowledge/a")],
    )
    rollback = IndexRollback(Bundle(Path(tmp_path) / "kb"), fake, retention=1)
    with factory() as session:
        before = len(fake.created)
        version = rollback.rollback(session, kb_id=kb_id, version="c1")
        assert len(fake.created) == before + 1
        assert version.git_commit == "c1"
        assert version.status == READY
        assert ActiveResolver().active_version(session, kb_id).id == version.id


class _FailingDeleteBackend(FakeBackend):
    def delete_snapshot(self, ref):
        self.deleted.append(ref)
        raise RuntimeError("delete failed")


def test_retention_delete_failure_keeps_active(app):
    backend = _FailingDeleteBackend()
    publisher = SnapshotPublisher(backend, retention=1, sleep=lambda _s: None)
    factory = app.state.session_factory
    with factory() as session:
        kb = _make_kb(session)
        publisher.publish(
            session, kb_id=kb.id, concepts=[_concept("knowledge/a")], git_commit="c1"
        )
        latest = publisher.publish(
            session, kb_id=kb.id, concepts=[_concept("knowledge/b")], git_commit="c2"
        )
        assert ActiveResolver().active_version(session, kb.id).id == latest.id
        assert len(backend.deleted) == 1


def test_rollback_retained_switches_without_rematerializing(app):
    from pathlib import Path

    from mykb.maintenance.rollback import IndexRollback
    from mykb.okf.bundle import Bundle

    fake = FakeBackend()
    publisher = SnapshotPublisher(fake, retention=3, sleep=lambda _s: None)
    factory = app.state.session_factory
    with factory() as session:
        kb = _make_kb(session)
        first = publisher.publish(
            session, kb_id=kb.id, concepts=[_concept("knowledge/a")], git_commit="c1"
        )
        publisher.publish(
            session, kb_id=kb.id, concepts=[_concept("knowledge/b")], git_commit="c2"
        )
        before = len(fake.created)
        result = IndexRollback(
            Bundle(Path("/tmp/unused-kb")), fake, retention=3
        ).rollback(session, kb_id=kb.id, version="c1")
        assert result.id == first.id
        assert len(fake.created) == before
        assert ActiveResolver().active_version(session, kb.id).id == first.id
