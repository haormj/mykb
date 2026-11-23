"""Read-only concept preview: markdown body and derived image assets."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ...kb.context import bundle_for
from ...okf.bundle import RESERVED_FILENAMES
from ..deps import KbAccess, require_kb_role

router = APIRouter(prefix="/kbs/{kb_id}/concepts", tags=["concepts"])


@router.get("/content")
def concept_content(
    concept_id: str, access: KbAccess = Depends(require_kb_role("viewer"))
) -> dict:
    bundle = bundle_for(access.kb)
    normalized = bundle.concept_id(concept_id)
    try:
        level, _ = bundle.split_concept_id(normalized)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="concept not found"
        ) from exc
    path = bundle.path_for_id(normalized)
    if not path.is_file() or path.name in RESERVED_FILENAMES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="concept not found")
    concept = bundle.read_concept(normalized)
    return {
        "concept_id": normalized,
        "level": level,
        "title": concept.title,
        "body": concept.body,
    }


@router.get("/asset")
def concept_asset(
    concept_id: str,
    name: str,
    access: KbAccess = Depends(require_kb_role("viewer")),
) -> Response:
    bundle = bundle_for(access.kb)
    normalized = bundle.concept_id(concept_id)
    try:
        data, mime = bundle.read_asset(normalized, name)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="asset not found"
        ) from exc
    return Response(content=data, media_type=mime)
