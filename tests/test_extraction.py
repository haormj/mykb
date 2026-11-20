from __future__ import annotations

import subprocess

import pytest

from mykb.extraction.code_ref import create_code_source
from mykb.extraction.drafter import Drafter
from mykb.extraction.lineage import trace_dependents
from mykb.extraction.llm import FakeLLM
from mykb.extraction.review import GitReview, stamp_verified
from mykb.okf.bundle import Bundle
from mykb.okf.model import Concept


def _bundle_with_source(tmp_path):
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout()
    sid = bundle.write_concept(
        Concept(
            frontmatter={"type": "源数据", "title": "LTV 定义", "resource": "https://wiki/ltv"},
            body="90 天 LTV 按客户聚合 90 天内的订单金额。\n",
        ),
        "raw",
        "wiki/ltv",
    )
    return bundle, sid


def test_ai_draft_produces_draft_with_lineage(tmp_path):
    bundle, sid = _bundle_with_source(tmp_path)
    drafter = Drafter(bundle, FakeLLM())
    concept = drafter.draft([sid], title="LTV 业务知识")

    assert concept.type == "业务知识"
    assert concept.status == "draft"
    assert concept.generated["by"].startswith("ai:")
    assert concept.source_ids() == [sid]
    assert concept.body.strip()


def test_draft_to_bundle_lands_in_knowledge(tmp_path):
    bundle, sid = _bundle_with_source(tmp_path)
    Drafter(bundle, FakeLLM()).draft_to_bundle([sid], relative_path="finance/ltv", title="LTV")
    loaded = bundle.read_concept("knowledge/finance/ltv")
    assert loaded.type == "业务知识"
    assert loaded.source_ids() == [sid]
    assert trace_dependents(bundle, sid) == ["knowledge/finance/ltv"]


def test_stamp_verified_sets_stable_and_human_event():
    concept = Concept(frontmatter={"type": "业务知识", "status": "draft"}, body="x")
    stamped = stamp_verified(concept, reviewer="alice", when="2026-01-01T00:00:00Z")
    assert stamped.status == "stable"
    assert stamped.verified == [{"by": "human:alice", "at": "2026-01-01T00:00:00Z"}]


def test_git_approve_merges_and_stamps_verified(tmp_path):
    bundle, sid = _bundle_with_source(tmp_path)
    cid = Drafter(bundle, FakeLLM()).draft_to_bundle([sid], relative_path="finance/ltv")
    review = GitReview(bundle)

    branch = review.submit(cid)
    assert branch.startswith("review/")

    result = review.approve(cid, reviewer="alice")
    assert result.approved
    assert result.commit

    loaded = bundle.read_concept(cid)
    assert loaded.status == "stable"
    assert loaded.verified[0]["by"] == "human:alice"

    log = subprocess.run(
        ["git", "-C", str(bundle.root), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    assert "ci: verify" in log


def test_git_reject_does_not_land_draft_on_main(tmp_path):
    bundle, sid = _bundle_with_source(tmp_path)
    cid = Drafter(bundle, FakeLLM()).draft_to_bundle([sid], relative_path="finance/ltv")
    review = GitReview(bundle)
    review.submit(cid)
    result = review.reject(cid)
    assert not result.approved
    with pytest.raises(FileNotFoundError):
        bundle.read_concept(cid)


def test_code_source_is_reference_only(tmp_path):
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout()
    code = "def ltv(orders):\n    return sum(orders)\n"
    sid = create_code_source(
        bundle,
        resource="https://git.example.com/repo/orders.py",
        summary="订单 LTV 计算函数",
    )
    source = bundle.read_concept(sid)
    assert source.type == "代码"
    assert source.resource == "https://git.example.com/repo/orders.py"
    assert code not in source.body

    knowledge = Drafter(bundle, FakeLLM()).draft([sid], title="LTV 函数知识")
    assert knowledge.frontmatter["resource"] == "https://git.example.com/repo/orders.py"
    assert code not in knowledge.body
