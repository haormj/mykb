from __future__ import annotations

from mykb.evaluation.runner import EvalRunner, similarity
from mykb.evaluation.types import CaseData
from mykb.okf.bundle import Bundle
from mykb.okf.model import Concept
from mykb.retrieval.engines.markdown_rag import LocalMarkdownRAG
from mykb.retrieval.interface import RetrievalService
from mykb.retrieval.sync import IndexSync
from tests.helpers import create_kb, login, register


def _bundle(tmp_path) -> Bundle:
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout()
    return bundle


def _knowledge(bundle, rel, *, status="stable", verified=True, body="body"):
    fm = {"type": "业务知识", "title": rel.split("/")[-1], "status": status}
    if verified:
        fm["verified"] = [{"by": "human:alice", "at": "2026-01-01T00:00:00Z"}]
    return bundle.write_concept(Concept(frontmatter=fm, body=body), "knowledge", rel)


def _service(bundle) -> RetrievalService:
    engine = LocalMarkdownRAG()
    IndexSync(bundle, [engine]).sync()
    return RetrievalService(knowledge_engine=engine)


def test_runner_classifies_four_states_and_scores(tmp_path):
    bundle = _bundle(tmp_path)
    _knowledge(bundle, "finance/ltv", body="90 day LTV aggregate across orders")
    _knowledge(bundle, "finance/refund", body="refund policy within 7 days")
    _knowledge(bundle, "finance/old", status="draft", verified=False, body="draft ltv")
    service = _service(bundle)

    cases = [
        CaseData(question="ltv", reference_answer="90 day LTV aggregate",
                 expected_concept="knowledge/finance/ltv"),
        CaseData(question="ltv", reference_answer="refund policy",
                 expected_concept="knowledge/finance/refund"),
        CaseData(question="ltv", reference_answer="draft ltv",
                 expected_concept="knowledge/finance/old"),
        CaseData(question="ltv", reference_answer="missing",
                 expected_concept="knowledge/finance/nope"),
        CaseData(question="ltv", reference_answer="90 day LTV aggregate"),
    ]

    result = EvalRunner(bundle, service).run(cases)
    statuses = [case.status for case in result.cases]
    assert statuses == ["hit", "not_retrieved", "unverified", "missing", "b_only"]
    # Fixed denominator: only the four cases with an expected concept count.
    assert result.a_score == 0.25
    # Coverage counts present concepts (hit + not_retrieved + unverified).
    assert result.coverage == 0.75
    assert result.case_count == 5
    assert 0.0 <= result.b_score <= 1.0
    assert result.knowledge_version is not None


def test_b_only_cases_do_not_lower_a_score(tmp_path):
    bundle = _bundle(tmp_path)
    _knowledge(bundle, "finance/ltv", body="90 day LTV aggregate across orders")
    service = _service(bundle)
    cases = [
        CaseData(question="ltv", reference_answer="90 day LTV aggregate",
                 expected_concept="knowledge/finance/ltv"),
        CaseData(question="ltv", reference_answer="anything"),
    ]
    result = EvalRunner(bundle, service).run(cases)
    assert result.a_score == 1.0
    assert result.coverage == 1.0
    assert result.case_count == 2


def test_similarity_bounds():
    assert similarity("a b c", "a b c") == 1.0
    assert similarity("a b", "c d") == 0.0
    assert 0.0 < similarity("a b c", "a b") < 1.0


# -- platform API --------------------------------------------------------


def _create_set(client, headers, name="finance"):
    payload = {
        "name": name,
        "cases": [
            {
                "question": "ltv",
                "reference_answer": "90 day LTV aggregate",
                "expected_concept": "knowledge/finance/ltv",
            }
        ],
    }
    response = client.post("/eval/sets", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_api_eval_set_crud_and_owner_only(client):
    owner = register(client, "eval-owner")
    created = _create_set(client, owner)
    assert created["case_count"] == 1
    set_id = created["id"]

    listing = client.get("/eval/sets", headers=owner).json()["sets"]
    assert [item["id"] for item in listing] == [set_id]

    other = register(client, "eval-other")
    assert client.patch(
        f"/eval/sets/{set_id}", json={"name": "hacked"}, headers=other
    ).status_code == 403
    assert client.delete(f"/eval/sets/{set_id}", headers=other).status_code == 403

    updated = client.patch(
        f"/eval/sets/{set_id}", json={"name": "finance-v2"}, headers=owner
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "finance-v2"
    assert updated.json()["cases"][0]["expected_concept"] == "knowledge/finance/ltv"

    assert client.delete(f"/eval/sets/{set_id}", headers=owner).status_code == 200
    assert client.get(f"/eval/sets/{set_id}", headers=owner).status_code == 404


def test_api_batch_run_and_result_visibility(client):
    owner = register(client, "batch-owner")
    kb_a = create_kb(client, owner, "batch-a")
    kb_b = create_kb(client, owner, "batch-b")
    _knowledge(Bundle(kb_a["local_path"]), "finance/ltv", body="90 day LTV aggregate")
    _knowledge(Bundle(kb_b["local_path"]), "finance/ltv", body="90 day LTV aggregate")
    set_id = _create_set(client, owner)["id"]

    run = client.post(
        f"/eval/sets/{set_id}/run",
        json={"target_kb_ids": [kb_a["id"], kb_b["id"]]},
        headers=owner,
    )
    assert run.status_code == 200, run.text
    runs = run.json()["runs"]
    assert {item["target_kb_id"] for item in runs} == {kb_a["id"], kb_b["id"]}
    assert all(item["a_score"] == 1.0 for item in runs)

    # A viewer member can see that KB's results...
    register(client, "batch-viewer")
    added = client.post(
        f"/kbs/{kb_a['id']}/members",
        json={"username": "batch-viewer", "role": "viewer"},
        headers=owner,
    )
    assert added.status_code in (200, 201), added.text
    viewer = login(client, "batch-viewer", "secret123")
    visible = client.get(f"/eval/runs?kb_id={kb_a['id']}", headers=viewer)
    assert visible.status_code == 200
    assert len(visible.json()["runs"]) == 1

    # ...but cannot run (needs editor), and a non-member sees nothing.
    assert client.post(
        f"/eval/sets/{set_id}/run", json={"target_kb_ids": [kb_a["id"]]}, headers=viewer
    ).status_code == 403
    outsider = register(client, "batch-outsider")
    assert client.get(f"/eval/runs?kb_id={kb_a['id']}", headers=outsider).status_code == 403
    assert client.get("/eval/runs", headers=outsider).json()["runs"] == []


def test_api_overview_cross_kb_and_visibility(client):
    owner = register(client, "overview-owner")
    kb_a = create_kb(client, owner, "overview-a")
    kb_b = create_kb(client, owner, "overview-b")
    _knowledge(Bundle(kb_a["local_path"]), "finance/ltv", body="90 day LTV aggregate")
    _knowledge(Bundle(kb_b["local_path"]), "finance/ltv", body="90 day LTV aggregate")
    set_id = _create_set(client, owner)["id"]
    client.post(
        f"/eval/sets/{set_id}/run",
        json={"target_kb_ids": [kb_a["id"], kb_b["id"]]},
        headers=owner,
    )

    overview = client.get("/eval/overview", headers=owner).json()
    assert set_id in {item["id"] for item in overview["sets"]}
    assert {item["id"] for item in overview["kbs"]} == {kb_a["id"], kb_b["id"]}
    assert {run["target_kb_id"] for run in overview["runs"]} == {kb_a["id"], kb_b["id"]}

    outsider = register(client, "overview-outsider")
    hidden = client.get("/eval/overview", headers=outsider).json()
    assert hidden["kbs"] == []
    assert hidden["runs"] == []
    # Global set definitions remain visible to any signed-in user.
    assert set_id in {item["id"] for item in hidden["sets"]}


def test_api_batch_run_is_all_or_nothing(client):
    owner = register(client, "atomic-owner")
    kb_a = create_kb(client, owner, "atomic-a")
    _knowledge(Bundle(kb_a["local_path"]), "finance/ltv", body="90 day LTV aggregate")
    set_id = _create_set(client, owner)["id"]

    stranger = register(client, "atomic-stranger")
    forb = create_kb(client, stranger, "atomic-forbidden")

    response = client.post(
        f"/eval/sets/{set_id}/run",
        json={"target_kb_ids": [kb_a["id"], forb["id"]]},
        headers=owner,
    )
    assert response.status_code == 403
    # No partial run was created for the permitted KB A.
    assert client.get(f"/eval/runs?kb_id={kb_a['id']}", headers=owner).json()["runs"] == []
