from __future__ import annotations

from mykb.evaluation.evalset import EvalCase, EvalSetManager
from mykb.evaluation.runner import EvalRunner, similarity
from mykb.evaluation.scoreboard import Scoreboard
from mykb.okf.bundle import Bundle
from mykb.okf.model import Concept
from mykb.retrieval.engines.markdown_rag import LocalMarkdownRAG
from mykb.retrieval.interface import RetrievalService
from mykb.retrieval.sync import IndexSync


def _bundle(tmp_path) -> Bundle:
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout()
    return bundle


def _knowledge(bundle, rel, *, status="stable", verified=True, body="90 day LTV aggregate"):
    fm = {"type": "业务知识", "title": rel.split("/")[-1], "status": status}
    if verified:
        fm["verified"] = [{"by": "human:alice", "at": "2026-01-01T00:00:00Z"}]
    return bundle.write_concept(Concept(frontmatter=fm, body=body), "knowledge", rel)


def _service(bundle) -> RetrievalService:
    engine = LocalMarkdownRAG()
    IndexSync(bundle, [engine]).sync()
    return RetrievalService(knowledge_engine=engine)


def test_eval_set_create_load_and_list(tmp_path):
    bundle = _bundle(tmp_path)
    manager = EvalSetManager(bundle)
    cases = [
        EvalCase(
            question="LTV 怎么算",
            reference_answer="按客户聚合 90 天订单",
            expected_concept="knowledge/finance/ltv",
            domain="finance",
            difficulty="hard",
        )
    ]
    manager.create("finance-basics", cases, title="财务基础")

    loaded = manager.load("finance-basics")
    assert loaded.cases[0].question == "LTV 怎么算"
    assert loaded.cases[0].expected_concept == "knowledge/finance/ltv"
    assert loaded.cases[0].domain == "finance"
    assert manager.list() == ["finance-basics"]


def test_runner_scores_knowledge_quality_and_end_to_end(tmp_path):
    bundle = _bundle(tmp_path)
    _knowledge(bundle, "finance/ltv", body="90 day LTV aggregate across orders")
    service = _service(bundle)
    EvalSetManager(bundle).create(
        "finance-basics",
        [
            EvalCase(
                question="ltv",
                reference_answer="90 day LTV aggregate",
                expected_concept="knowledge/finance/ltv",
            )
        ],
    )

    run = EvalRunner(bundle, service).run("finance-basics")
    assert run.a_score == 1.0
    assert run.b_score > 0.5
    assert run.cases[0].a_hit
    assert run.knowledge_version is not None


def test_unverified_expected_concept_scores_zero_on_a(tmp_path):
    bundle = _bundle(tmp_path)
    _knowledge(bundle, "finance/ltv", status="draft", verified=False)
    service = _service(bundle)
    EvalSetManager(bundle).create(
        "drafts",
        [EvalCase(question="ltv", reference_answer="x", expected_concept="knowledge/finance/ltv")],
    )
    run = EvalRunner(bundle, service).run("drafts")
    assert run.a_score == 0.0


def test_scoreboard_records_trend(tmp_path):
    bundle = _bundle(tmp_path)
    _knowledge(bundle, "finance/ltv", body="90 day LTV aggregate across orders")
    service = _service(bundle)
    EvalSetManager(bundle).create(
        "finance-basics",
        [EvalCase(question="ltv", reference_answer="90 day LTV aggregate",
                  expected_concept="knowledge/finance/ltv")],
    )
    runner = EvalRunner(bundle, service)
    runner.run("finance-basics")
    runner.run("finance-basics")

    board = Scoreboard(bundle)
    trend = board.trend("finance-basics")
    assert len(trend) == 2
    assert all(entry["a_score"] == 1.0 for entry in trend)
    assert board.latest("finance-basics") is not None


def test_similarity_bounds():
    assert similarity("a b c", "a b c") == 1.0
    assert similarity("a b", "c d") == 0.0
    assert 0.0 < similarity("a b c", "a b") < 1.0


def test_api_eval_endpoints(client):
    from tests.helpers import create_kb, register

    headers = register(client, "eval-user")
    kb = create_kb(client, headers, "api-eval")
    bundle = Bundle(kb["local_path"])
    _knowledge(bundle, "finance/ltv", body="90 day LTV aggregate across orders")

    base = f"/kbs/{kb['id']}/eval"
    payload = {
        "name": "finance",
        "cases": [
            {
                "question": "ltv",
                "reference_answer": "90 day LTV aggregate",
                "expected_concept": "knowledge/finance/ltv",
            }
        ],
    }
    assert client.post(f"{base}/sets", json=payload, headers=headers).status_code == 200
    assert client.get(f"{base}/sets", headers=headers).json()["sets"] == ["finance"]

    run = client.post(f"{base}/run", params={"name": "finance"}, headers=headers).json()
    assert run["a_score"] == 1.0
    assert run["b_score"] > 0.5

    trend = client.get(f"{base}/sets/finance/trend", headers=headers).json()["trend"]
    assert len(trend) == 1
