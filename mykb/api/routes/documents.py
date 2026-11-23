"""Knowledge-base document (raw concept) listing."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ...extraction.pipeline import process_pending
from ...extraction.queue import ACTION_DELETE, enqueue_item
from ...kb.context import bundle_for
from ..deps import AuthUser, KbAccess, get_current_user, get_session, require_kb_role

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


@router.delete("/{concept_id:path}")
def delete_document(
    concept_id: str,
    request: Request,
    access: KbAccess = Depends(require_kb_role("editor")),
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    bundle = bundle_for(access.kb)
    normalized = bundle.concept_id(concept_id)
    if not bundle.path_for_id(normalized).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    title = bundle.read_concept(normalized).title
    item = enqueue_item(
        session,
        kb_id=access.kb.id,
        import_task_id=None,
        concept_id=normalized,
        action=ACTION_DELETE,
        source_hash=None,
        title=title,
        created_by=user.id,
    )
    session.commit()
    process_pending(
        access.kb.id,
        session_factory=request.app.state.session_factory,
        settings=request.app.state.settings,
        locks=request.app.state.extraction_locks,
        guard=request.app.state.extraction_locks_guard,
        cache=request.app.state.retrieval_cache,
    )
    session.refresh(item)
    return {
        "item_id": item.id,
        "concept_id": concept_id,
        "action": item.action,
        "status": item.status,
    }
