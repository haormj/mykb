"""Knowledge-base scoped retrieval endpoints."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Request

from ...kb.context import RetrievalCache
from ..deps import KbAccess, require_kb_role

router = APIRouter(prefix="/kbs/{kb_id}", tags=["retrieval"])


def get_cache(request: Request) -> RetrievalCache:
    return request.app.state.retrieval_cache


@router.get("/retrieve")
def retrieve(
    q: str,
    kind: str = "knowledge",
    top_k: int = 5,
    access: KbAccess = Depends(require_kb_role("viewer")),
    cache: RetrievalCache = Depends(get_cache),
) -> dict:
    service = cache.get(access.kb)
    return asdict(service.search(q, kind=kind, top_k=top_k))


@router.get("/answer")
def answer(
    q: str,
    access: KbAccess = Depends(require_kb_role("viewer")),
    cache: RetrievalCache = Depends(get_cache),
) -> dict:
    service = cache.get(access.kb)
    return {"query": q, "answer": service.answer(q)}

