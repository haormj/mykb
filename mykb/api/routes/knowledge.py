"""Read-only projection of business knowledge concepts."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from ...kb.context import bundle_for
from ..deps import KbAccess, require_kb_role

router = APIRouter(prefix="/kbs/{kb_id}/knowledge", tags=["knowledge"])


@router.get("")
def list_knowledge(access: KbAccess = Depends(require_kb_role("viewer"))) -> dict:
    bundle = bundle_for(access.kb)
    items = []
    for concept_id, concept in bundle.iter_concepts("knowledge"):
        items.append(
            {
                "concept_id": concept_id,
                "title": concept.title or Path(concept_id).stem,
                "status": concept.status,
                "type": concept.type,
                "verified": bool(concept.verified),
                "sources": concept.source_ids(),
            }
        )
    items.sort(key=lambda item: str(item["concept_id"]))
    return {"knowledge": items}
