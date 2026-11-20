from __future__ import annotations

import subprocess

from mykb.extraction.drafter import Drafter
from mykb.extraction.llm import FakeLLM
from mykb.maintenance.lifecycle import deprecate, mark_needs_review, re_draft
from mykb.maintenance.lineage_trace import trace_affected
from mykb.maintenance.rollback import IndexRollback
from mykb.maintenance.staleness import detect_stale_sources, is_expired
from mykb.okf.bundle import Bundle
from mykb.okf.model import Concept
from mykb.retrieval.engines.markdown_rag import LocalMarkdownRAG
from mykb.retrieval.sync import IndexSync


def _bundle(tmp_path) -> Bundle:
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout()
    return bundle


def _source(bundle, rel="wiki/a", **fm):
    frontmatter = {"type": "源数据", "resource": f"https://src/{rel}", **fm}
    return bundle.write_concept(Concept(frontmatter=frontmatter, body="source"), "raw", rel)


def _knowledge(bundle, rel, *, sources=None, body="body", status="stable", verified=True):
    frontmatter = {"type": "业务知识", "title": rel.split("/")[-1], "status": status}
    if verified:
        frontmatter["verified"] = [{"by": "human:alice", "at": "2026-01-01T00:00:00Z"}]
    if sources:
        frontmatter["sources"] = [{"id": s} for s in sources]
    return bundle.write_concept(Concept(frontmatter=frontmatter, body=body), "knowledge", rel)


def test_staleness_detects_expired_and_changed(tmp_path):
    bundle = _bundle(tmp_path)
    expired = _source(bundle, "wiki/old", stale_after="2000-01-01T00:00:00Z")
    _source(bundle, "wiki/fresh", stale_after="2999-01-01T00:00:00Z")
    changed = _source(bundle, "wiki/changed", title="changed-doc")

    assert is_expired(bundle.read_concept(expired))
    stale = detect_stale_sources(
        bundle, resource_checker=lambda c: c.title == "changed-doc"
    )
    reasons = {s.concept_id: s.reason for s in stale}
    assert reasons[expired] == "stale_after"
    assert reasons[changed] == "resource_changed"


def test_trace_affected_walks_sources_transitively(tmp_path):
    bundle = _bundle(tmp_path)
    a = _source(bundle, "wiki/a")
    k1 = _knowledge(bundle, "k/one", sources=[a])
    k2 = _knowledge(bundle, "k/two", sources=[k1])
    _knowledge(bundle, "k/unrelated", sources=["raw/wiki/other"])

    assert trace_affected(bundle, a) == sorted([k1, k2])


def test_mark_needs_review_and_re_draft(tmp_path):
    bundle = _bundle(tmp_path)
    a = _source(bundle, "wiki/a")
    k1 = _knowledge(bundle, "k/one", sources=[a])

    updated = mark_needs_review(bundle, [k1], reason="source changed")
    assert updated == [k1]
    assert bundle.read_concept(k1).status == "needs-review"

    new_id = re_draft(bundle, k1, Drafter(bundle, FakeLLM()))
    redrafted = bundle.read_concept(new_id)
    assert redrafted.status == "draft"
    assert redrafted.generated["by"].startswith("ai:")
    assert redrafted.source_ids() == [a]


def test_deprecate_points_to_superseded(tmp_path):
    bundle = _bundle(tmp_path)
    old = _knowledge(bundle, "k/old")
    new = _knowledge(bundle, "k/new")
    deprecate(bundle, old, superseded_by=new)
    loaded = bundle.read_concept(old)
    assert loaded.status == "deprecated"
    assert loaded.superseded_by == new


def _commit(root, message):
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-m", message],
        check=True,
        capture_output=True,
    )


def test_index_rollback_restores_historical_version(tmp_path):
    bundle = _bundle(tmp_path)
    concept_id = _knowledge(bundle, "k/one", body="v1marker content")
    subprocess.run(["git", "-C", str(bundle.root), "init", "-b", "main"], check=True, capture_output=True)
    _commit(bundle.root, "v1")
    v1 = subprocess.run(
        ["git", "-C", str(bundle.root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()

    engine = LocalMarkdownRAG()
    IndexSync(bundle, [engine]).sync()
    assert engine.search("v1marker")

    bad = bundle.read_concept(concept_id)
    bad.body = "badmarker content"
    bundle.save_concept(bad)
    _commit(bundle.root, "v2-bad")
    IndexSync(bundle, [engine]).sync()
    assert engine.search("badmarker")

    IndexRollback(bundle, [engine]).rollback(v1)
    assert engine.search("v1marker")
    assert engine.search("badmarker") == []
