"""Knowledge-base scoped draft review endpoints."""

from __future__ import annotations

import difflib

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.models import ExtractionItem
from ...extraction.pipeline import (
    PipelineError,
    approve_item,
    redraft_item,
    reject_item,
)
from ...extraction.review import GitReview
from ...kb import gitops
from ...kb.context import RetrievalCache, bundle_for
from ..deps import KbAccess, get_session, require_kb_role

router = APIRouter(prefix="/kbs/{kb_id}/review", tags=["review"])


@router.get("/drafts")
def review_drafts(access: KbAccess = Depends(require_kb_role("admin"))) -> dict:
    bundle = bundle_for(access.kb)
    drafts = [
        {"concept_id": concept_id, "title": concept.title, "status": concept.status}
        for concept_id, concept in bundle.iter_concepts("knowledge")
        if concept.status in ("draft", "needs-review")
    ]
    return {"drafts": drafts}


@router.get("/diff")
def review_diff(
    concept_id: str, access: KbAccess = Depends(require_kb_role("admin"))
) -> dict:
    bundle = bundle_for(access.kb)
    concept = bundle.read_concept(concept_id)
    source_texts: list[str] = []
    for source_id in concept.source_ids():
        try:
            source_texts.append(bundle.read_concept(source_id).body)
        except FileNotFoundError:
            continue
    source_text = "\n\n".join(source_texts)
    diff = "\n".join(
        difflib.unified_diff(
            source_text.splitlines(),
            concept.body.splitlines(),
            fromfile="sources",
            tofile="draft",
            lineterm="",
        )
    )
    return {"concept_id": concept_id, "diff": diff or concept.body}


@router.post("/approve")
def review_approve(
    concept_id: str,
    reviewer: str,
    request: Request,
    access: KbAccess = Depends(require_kb_role("admin")),
) -> dict:
    bundle = bundle_for(access.kb)
    result = GitReview(bundle).approve_draft(concept_id, reviewer=reviewer)
    cache: RetrievalCache = request.app.state.retrieval_cache
    cache.invalidate(access.kb.id)
    return {
        "concept_id": result.concept_id,
        "approved": result.approved,
        "commit": result.commit,
    }


# -- document-level review MRs -------------------------------------------
@router.get("/mrs")
def list_review_mrs(
    access: KbAccess = Depends(require_kb_role("admin")),
    session: Session = Depends(get_session),
) -> dict:
    items = session.scalars(
        select(ExtractionItem)
        .where(ExtractionItem.kb_id == access.kb.id)
        .order_by(ExtractionItem.created_at)
    ).all()
    mrs = [
        {
            "item_id": item.id,
            "concept_id": item.concept_id,
            "title": item.title,
            "action": item.action,
            "status": item.status,
            "branch": item.branch,
            "error": item.error,
        }
        for item in items
        if item.status in ("reviewing", "queued", "processing")
    ]
    return {"mrs": mrs}


@router.get("/mrs/{item_id}/diff")
def review_mr_diff(
    item_id: str,
    access: KbAccess = Depends(require_kb_role("admin")),
    session: Session = Depends(get_session),
) -> dict:
    item = session.get(ExtractionItem, item_id)
    if item is None or item.kb_id != access.kb.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review item not found")
    if not item.branch:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="review item has no branch")
    bundle = bundle_for(access.kb)
    files = gitops.changed_files_vs(bundle.root, "main", item.branch)
    return {
        "item_id": item.id,
        "concept_id": item.concept_id,
        "branch": item.branch,
        "files": files,
        "diff": gitops.diff_text(bundle.root, "main", item.branch),
    }


@router.post("/mrs/{item_id}/approve")
def review_mr_approve(
    item_id: str,
    reviewer: str,
    request: Request,
    access: KbAccess = Depends(require_kb_role("admin")),
) -> dict:
    try:
        return approve_item(
            item_id,
            session_factory=request.app.state.session_factory,
            settings=request.app.state.settings,
            reviewer=reviewer,
            locks=request.app.state.extraction_locks,
            guard=request.app.state.extraction_locks_guard,
            cache=request.app.state.retrieval_cache,
        )
    except PipelineError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/mrs/{item_id}/reject")
def review_mr_reject(
    item_id: str,
    request: Request,
    access: KbAccess = Depends(require_kb_role("admin")),
) -> dict:
    try:
        return reject_item(
            item_id,
            session_factory=request.app.state.session_factory,
            settings=request.app.state.settings,
            locks=request.app.state.extraction_locks,
            guard=request.app.state.extraction_locks_guard,
            cache=request.app.state.retrieval_cache,
        )
    except PipelineError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/mrs/{item_id}/redraft")
def review_mr_redraft(
    item_id: str,
    request: Request,
    access: KbAccess = Depends(require_kb_role("admin")),
) -> dict:
    try:
        return redraft_item(
            item_id,
            session_factory=request.app.state.session_factory,
            settings=request.app.state.settings,
            locks=request.app.state.extraction_locks,
            guard=request.app.state.extraction_locks_guard,
            cache=request.app.state.retrieval_cache,
        )
    except PipelineError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
