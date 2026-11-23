from __future__ import annotations

from sqlalchemy import select

from mykb.db.models import User
from mykb.evaluation import store
from mykb.evaluation.types import CaseData, CaseResult, EvalResult
from tests.helpers import create_kb, register


def _setup_owner_and_kbs(app, client):
    headers = register(client, "store-user")
    kb_a = create_kb(client, headers, "store-kb-a")
    kb_b = create_kb(client, headers, "store-kb-b")
    with app.state.session_factory() as session:
        owner = session.scalar(select(User).where(User.username == "store-user"))
        assert owner is not None
        return headers, owner.id, kb_a["id"], kb_b["id"]


def _result(a: float = 1.0, b: float = 0.8, status: str = "hit") -> EvalResult:
    return EvalResult(
        a_score=a,
        b_score=b,
        coverage=1.0,
        case_count=1,
        knowledge_version="v1",
        cases=[
            CaseResult(
                question="q",
                expected_concept="knowledge/x",
                status=status,
                a_score=a,
                b_answer="ans",
                b_score=b,
            )
        ],
    )


def test_store_set_crud_and_cross_kb_runs(app, client):
    _headers, owner_id, kb_a, kb_b = _setup_owner_and_kbs(app, client)

    with app.state.session_factory() as session:
        created = store.create_set(
            session,
            owner_id=owner_id,
            name="finance",
            title="财务",
            cases=[
                CaseData(question="ltv", reference_answer="90d", expected_concept="knowledge/x"),
                CaseData(question="no-concept", reference_answer="free"),
            ],
        )
        created_id = created.id
        assert [c.question for c in created.cases] == ["ltv", "no-concept"]
        assert [c.position for c in created.cases] == [0, 1]

        names = [s.id for s in store.list_sets(session)]
        assert created_id in names

        updated = store.update_set(
            session,
            store.get_set(session, created_id),
            name="finance-v2",
            cases=[CaseData(question="only", reference_answer="x")],
        )
        assert updated.name == "finance-v2"
        assert len(updated.cases) == 1

    with app.state.session_factory() as session:
        eval_set = store.get_set(session, created_id)
        assert eval_set is not None
        run_a = store.save_run(
            session, eval_set=eval_set, target_kb_id=kb_a, triggered_by=owner_id, result=_result()
        )
        run_b = store.save_run(
            session,
            eval_set=eval_set,
            target_kb_id=kb_b,
            triggered_by=owner_id,
            result=_result(a=0.5),
        )
        assert run_a.id and run_b.id

        kb_a_runs = store.list_runs(session, kb_ids=[kb_a])
        assert [r.id for r in kb_a_runs] == [run_a.id]

        results = store.run_case_results(session, run_a.id)
        assert len(results) == 1
        assert results[0].question == "q"

        points = store.trend(session, set_id=created_id, kb_id=kb_a)
        assert len(points) == 1 and points[0].a_score == 1.0

        store.delete_set(session, eval_set)
        assert store.get_set(session, created_id) is None
