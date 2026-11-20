"""Knowledge-base scoped evaluation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ...evaluation.evalset import EvalCase, EvalSetManager
from ...evaluation.runner import EvalRunner
from ...evaluation.scoreboard import Scoreboard
from ...kb.context import RetrievalCache, bundle_for
from ..deps import KbAccess, require_kb_role

router = APIRouter(prefix="/kbs/{kb_id}/eval", tags=["evaluation"])


class EvalCaseIn(BaseModel):
    question: str
    reference_answer: str
    expected_concept: str | None = None
    domain: str | None = None
    difficulty: str | None = None


class EvalSetIn(BaseModel):
    name: str
    title: str | None = None
    cases: list[EvalCaseIn]


@router.post("/sets")
def create_eval_set(
    payload: EvalSetIn,
    access: KbAccess = Depends(require_kb_role("editor")),
) -> dict:
    bundle = bundle_for(access.kb)
    cases = [EvalCase(**case.model_dump(exclude_none=True)) for case in payload.cases]
    concept_id = EvalSetManager(bundle).create(payload.name, cases, title=payload.title)
    return {"id": concept_id, "name": payload.name}


@router.get("/sets")
def list_eval_sets(access: KbAccess = Depends(require_kb_role("viewer"))) -> dict:
    return {"sets": EvalSetManager(bundle_for(access.kb)).list()}


@router.post("/run")
def run_eval(
    name: str,
    request: Request,
    access: KbAccess = Depends(require_kb_role("editor")),
) -> dict:
    bundle = bundle_for(access.kb)
    cache: RetrievalCache = request.app.state.retrieval_cache
    run = EvalRunner(bundle, cache.get(access.kb)).run(name)
    return run.to_dict()


@router.get("/sets/{name}/trend")
def eval_trend(name: str, access: KbAccess = Depends(require_kb_role("viewer"))) -> dict:
    return {"trend": Scoreboard(bundle_for(access.kb)).trend(name)}
