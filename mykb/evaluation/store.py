"""Database-backed evaluation store.

Eval sets and runs are platform metadata (Postgres), not knowledge content:
they never live in a knowledge-base git bundle. See
``openspec/changes/platform-level-evaluation/design.md``.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import EvalCase, EvalCaseResult, EvalRun, EvalSet
from .types import CaseData, EvalResult


def _case_row(case: CaseData, position: int) -> EvalCase:
    return EvalCase(
        position=position,
        question=case.question,
        reference_answer=case.reference_answer,
        expected_concept=case.expected_concept or None,
        domain=case.domain or None,
        difficulty=case.difficulty or None,
    )


def create_set(
    session: Session,
    *,
    owner_id: str,
    name: str,
    cases: Iterable[CaseData],
    title: str | None = None,
    description: str | None = None,
) -> EvalSet:
    eval_set = EvalSet(
        owner_user_id=owner_id,
        name=name.strip(),
        title=title,
        description=description,
    )
    for position, case in enumerate(cases):
        eval_set.cases.append(_case_row(case, position))
    session.add(eval_set)
    session.commit()
    session.refresh(eval_set)
    return eval_set


def list_sets(session: Session) -> list[EvalSet]:
    stmt = select(EvalSet).order_by(EvalSet.created_at.desc(), EvalSet.name)
    return list(session.scalars(stmt))


def get_set(session: Session, set_id: str) -> EvalSet | None:
    return session.get(EvalSet, set_id)


def update_set(
    session: Session,
    eval_set: EvalSet,
    *,
    name: str | None = None,
    title: str | None = None,
    description: str | None = None,
    cases: Iterable[CaseData] | None = None,
) -> EvalSet:
    if name is not None:
        eval_set.name = name.strip()
    if title is not None:
        eval_set.title = title
    if description is not None:
        eval_set.description = description
    if cases is not None:
        eval_set.cases.clear()
        for position, case in enumerate(cases):
            eval_set.cases.append(_case_row(case, position))
    session.commit()
    session.refresh(eval_set)
    return eval_set


def delete_set(session: Session, eval_set: EvalSet) -> None:
    session.delete(eval_set)
    session.commit()


def case_data(eval_set: EvalSet) -> list[CaseData]:
    return [
        CaseData(
            question=case.question,
            reference_answer=case.reference_answer,
            expected_concept=case.expected_concept,
            domain=case.domain,
            difficulty=case.difficulty,
            case_id=case.id,
        )
        for case in eval_set.cases
    ]


def save_run(
    session: Session,
    *,
    eval_set: EvalSet,
    target_kb_id: str,
    triggered_by: str | None,
    result: EvalResult,
) -> EvalRun:
    run = EvalRun(
        set_id=eval_set.id,
        target_kb_id=target_kb_id,
        triggered_by=triggered_by,
        knowledge_version=result.knowledge_version,
        case_count=result.case_count,
        coverage=result.coverage,
        a_score=result.a_score,
        b_score=result.b_score,
    )
    session.add(run)
    session.flush()
    for case in result.cases:
        session.add(
            EvalCaseResult(
                run_id=run.id,
                case_id=case.case_id,
                question=case.question,
                expected_concept=case.expected_concept,
                status=case.status,
                a_score=case.a_score,
                b_answer=case.b_answer,
                b_score=case.b_score,
            )
        )
    session.commit()
    session.refresh(run)
    return run


def list_runs(
    session: Session,
    *,
    kb_ids: Iterable[str] | None = None,
    set_id: str | None = None,
) -> list[EvalRun]:
    stmt = select(EvalRun).order_by(EvalRun.created_at.desc())
    if kb_ids is not None:
        ids = list(kb_ids)
        if not ids:
            return []
        stmt = stmt.where(EvalRun.target_kb_id.in_(ids))
    if set_id is not None:
        stmt = stmt.where(EvalRun.set_id == set_id)
    return list(session.scalars(stmt))


def get_run(session: Session, run_id: str) -> EvalRun | None:
    return session.get(EvalRun, run_id)


def run_case_results(session: Session, run_id: str) -> list[EvalCaseResult]:
    stmt = select(EvalCaseResult).where(EvalCaseResult.run_id == run_id)
    return list(session.scalars(stmt))


def trend(session: Session, *, set_id: str, kb_id: str) -> list[EvalRun]:
    stmt = (
        select(EvalRun)
        .where(EvalRun.set_id == set_id, EvalRun.target_kb_id == kb_id)
        .order_by(EvalRun.created_at.asc())
    )
    return list(session.scalars(stmt))
