"""Knowledge-base scoped draft review endpoints."""

from __future__ import annotations

import difflib

from fastapi import APIRouter, Depends, Request

from ...extraction.review import GitReview
from ...kb.context import RetrievalCache, bundle_for
from ..deps import KbAccess, require_kb_role

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
