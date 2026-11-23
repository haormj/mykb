"""Platform-level evaluation endpoints.

Eval sets are global, reusable platform resources. Each run targets exactly one
knowledge base, and a set may be run against several knowledge bases at once.
Run results are visible only to members of the target knowledge base (and to
platform administrators) so the knowledge-base isolation invariant holds.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...db.models import EvalCaseResult, EvalRun, EvalSet
from ...evaluation import store
from ...evaluation.runner import EvalRunner
from ...evaluation.types import CaseData
from ...kb.context import RetrievalCache, bundle_for
from ...kb.service import accessible_bases
from ..deps import (
    AuthUser,
    KbAccess,
    ensure_kb_role,
    get_current_user,
    get_session,
)

router = APIRouter(prefix="/eval", tags=["evaluation"])


class EvalCaseIn(BaseModel):
    question: str
    reference_answer: str
    expected_concept: str | None = None
    domain: str | None = None
    difficulty: str | None = None


class EvalSetIn(BaseModel):
    name: str
    title: str | None = None
    description: str | None = None
    cases: list[EvalCaseIn] = []


class EvalSetPatch(BaseModel):
    name: str | None = None
    title: str | None = None
    description: str | None = None
    cases: list[EvalCaseIn] | None = None


class EvalRunIn(BaseModel):
    target_kb_ids: list[str]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _case_data(cases: list[EvalCaseIn]) -> list[CaseData]:
    return [
        CaseData(
            question=case.question,
            reference_answer=case.reference_answer,
            expected_concept=case.expected_concept,
            domain=case.domain,
            difficulty=case.difficulty,
        )
        for case in cases
    ]


def _set_payload(eval_set: EvalSet, *, with_cases: bool = False) -> dict:
    payload: dict[str, object] = {
        "id": eval_set.id,
        "name": eval_set.name,
        "title": eval_set.title,
        "description": eval_set.description,
        "owner_user_id": eval_set.owner_user_id,
        "case_count": len(eval_set.cases),
        "created_at": _iso(eval_set.created_at),
        "updated_at": _iso(eval_set.updated_at),
    }
    if with_cases:
        payload["cases"] = [
            {
                "id": case.id,
                "position": case.position,
                "question": case.question,
                "reference_answer": case.reference_answer,
                "expected_concept": case.expected_concept,
                "domain": case.domain,
                "difficulty": case.difficulty,
            }
            for case in eval_set.cases
        ]
    return payload


def _run_payload(run: EvalRun) -> dict:
    return {
        "id": run.id,
        "set_id": run.set_id,
        "target_kb_id": run.target_kb_id,
        "triggered_by": run.triggered_by,
        "knowledge_version": run.knowledge_version,
        "case_count": run.case_count,
        "coverage": run.coverage,
        "a_score": run.a_score,
        "b_score": run.b_score,
        "created_at": _iso(run.created_at),
    }


def _case_result_payload(result: EvalCaseResult) -> dict:
    return {
        "id": result.id,
        "case_id": result.case_id,
        "question": result.question,
        "expected_concept": result.expected_concept,
        "status": result.status,
        "a_score": result.a_score,
        "b_answer": result.b_answer,
        "b_score": result.b_score,
    }


def _require_set(session: Session, set_id: str) -> EvalSet:
    eval_set = store.get_set(session, set_id)
    if eval_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval set not found")
    return eval_set


def _require_owner(user: AuthUser, eval_set: EvalSet) -> None:
    if not user.is_platform_admin and eval_set.owner_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can modify this eval set"
        )


@router.post("/sets")
def create_eval_set(
    payload: EvalSetIn,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    if not payload.name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
    eval_set = store.create_set(
        session,
        owner_id=user.id,
        name=payload.name,
        title=payload.title,
        description=payload.description,
        cases=_case_data(payload.cases),
    )
    return _set_payload(eval_set, with_cases=True)


@router.get("/sets")
def list_eval_sets(
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    return {"sets": [_set_payload(eval_set) for eval_set in store.list_sets(session)]}


@router.get("/sets/{set_id}")
def get_eval_set(
    set_id: str,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    return _set_payload(_require_set(session, set_id), with_cases=True)


@router.patch("/sets/{set_id}")
def update_eval_set(
    set_id: str,
    payload: EvalSetPatch,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    eval_set = _require_set(session, set_id)
    _require_owner(user, eval_set)
    if payload.name is not None and not payload.name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
    updated = store.update_set(
        session,
        eval_set,
        name=payload.name,
        title=payload.title,
        description=payload.description,
        cases=_case_data(payload.cases) if payload.cases is not None else None,
    )
    return _set_payload(updated, with_cases=True)


@router.delete("/sets/{set_id}")
def delete_eval_set(
    set_id: str,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    eval_set = _require_set(session, set_id)
    _require_owner(user, eval_set)
    store.delete_set(session, eval_set)
    return {"deleted": True}


@router.post("/sets/{set_id}/run")
def run_eval_set(
    set_id: str,
    payload: EvalRunIn,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    eval_set = _require_set(session, set_id)
    target_ids = list(dict.fromkeys(payload.target_kb_ids))
    if not target_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="target_kb_ids is required"
        )

    # Validate every target first so a partial permission failure creates no runs.
    accesses: list[KbAccess] = [
        ensure_kb_role(session=session, user=user, kb_id=kb_id, min_role="editor")
        for kb_id in target_ids
    ]

    cache: RetrievalCache = request.app.state.retrieval_cache
    cases = store.case_data(eval_set)
    runs: list[dict] = []
    for access in accesses:
        service = cache.get(access.kb)
        result = EvalRunner(bundle_for(access.kb), service).run(cases)
        run = store.save_run(
            session,
            eval_set=eval_set,
            target_kb_id=access.kb.id,
            triggered_by=user.id,
            result=result,
        )
        runs.append(_run_payload(run))
    return {"runs": runs}


@router.get("/runs")
def list_eval_runs(
    kb_id: str | None = None,
    set_id: str | None = None,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    if kb_id is not None:
        access = ensure_kb_role(session=session, user=user, kb_id=kb_id, min_role="viewer")
        runs = store.list_runs(session, kb_ids=[access.kb.id], set_id=set_id)
    else:
        accessible = accessible_bases(
            session, user_id=user.id, is_platform_admin=user.is_platform_admin
        )
        runs = store.list_runs(
            session, kb_ids=[kb.id for kb, _role in accessible], set_id=set_id
        )
    return {"runs": [_run_payload(run) for run in runs]}


@router.get("/runs/{run_id}")
def get_eval_run(
    run_id: str,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    run = store.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval run not found")
    ensure_kb_role(session=session, user=user, kb_id=run.target_kb_id, min_role="viewer")
    payload = _run_payload(run)
    payload["cases"] = [
        _case_result_payload(result) for result in store.run_case_results(session, run.id)
    ]
    return payload


@router.get("/sets/{set_id}/trend")
def eval_trend(
    set_id: str,
    kb_id: str,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_set(session, set_id)
    access = ensure_kb_role(session=session, user=user, kb_id=kb_id, min_role="viewer")
    points = store.trend(session, set_id=set_id, kb_id=access.kb.id)
    return {
        "trend": [
            {
                "created_at": _iso(run.created_at),
                "a_score": run.a_score,
                "b_score": run.b_score,
                "coverage": run.coverage,
                "knowledge_version": run.knowledge_version,
            }
            for run in points
        ]
    }


@router.get("/overview")
def eval_overview(
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    accessible = accessible_bases(
        session, user_id=user.id, is_platform_admin=user.is_platform_admin
    )
    kb_ids = [kb.id for kb, _role in accessible]
    runs = store.list_runs(session, kb_ids=kb_ids)
    return {
        "sets": [
            {"id": eval_set.id, "name": eval_set.name, "title": eval_set.title}
            for eval_set in store.list_sets(session)
        ],
        "kbs": [
            {"id": kb.id, "name": kb.name, "my_role": role} for kb, role in accessible
        ],
        "runs": [_run_payload(run) for run in runs],
    }
