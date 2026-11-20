"""Knowledge-base document (raw concept) listing."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from ...kb.context import bundle_for
from ..deps import KbAccess, require_kb_role

router = APIRouter(prefix="/kbs/{kb_id}/documents", tags=["documents"])


@router.get("")
def list_documents(access: KbAccess = Depends(require_kb_role("viewer"))) -> dict:
    bundle = bundle_for(access.kb)
    documents = []
    for concept_id, concept in bundle.iter_concepts("raw"):
        documents.append(
            {
                "concept_id": concept_id,
                "title": concept.title or Path(concept_id).stem,
                "resource": concept.resource,
                "status": concept.status,
                "type": concept.type,
                "import_task_id": concept.frontmatter.get("x-import-task"),
            }
        )
    documents.sort(key=lambda item: str(item["concept_id"]))
    return {"documents": documents}
