"""Document import task endpoints (local upload)."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import Settings
from ...db.models import ExtractionItem, ImportTask
from ...extraction.staging import cleanup_staged
from ...importing.service import (
    UploadError,
    prepare_upload,
    run_import_task,
    task_payload,
)
from ...kb import gitops
from ...okf.bundle import Bundle
from ..deps import (
    AuthUser,
    KbAccess,
    get_current_user,
    get_session,
    get_settings,
    require_kb_role,
)

router = APIRouter(prefix="/kbs/{kb_id}/import-tasks", tags=["import-tasks"])

TERMINAL_STATUSES = {"succeeded", "partial", "failed", "cancelled", "merged", "rejected"}
MANAGER_ROLES = {"admin", "owner"}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_import_task(
    request: Request,
    files: list[UploadFile] = File(...),
    access: KbAccess = Depends(require_kb_role("editor")),
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    task_id = str(uuid.uuid4())
    payloads: list[tuple[str, bytes]] = []
    for upload in files:
        payloads.append((upload.filename or "", await upload.read()))

    try:
        _, source_config = prepare_upload(task_id, settings, payloads)
    except UploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    task = ImportTask(
        id=task_id,
        kb_id=access.kb.id,
        source_type="upload",
        source_config=source_config,
        status="queued",
        created_by=user.id,
    )
    try:
        session.add(task)
        session.commit()
    except Exception:
        session.rollback()
        shutil.rmtree(settings.tmp_root / task_id, ignore_errors=True)
        raise

    request.app.state.import_executor.submit(
        run_import_task,
        task_id,
        session_factory=request.app.state.session_factory,
        settings=settings,
        cache=request.app.state.retrieval_cache,
        locks=request.app.state.kb_locks,
        lock_guard=request.app.state.kb_locks_guard,
        converter=request.app.state.converter_service,
        extraction_locks=request.app.state.extraction_locks,
        extraction_guard=request.app.state.extraction_locks_guard,
    )
    return task_payload(task)


@router.get("")
def list_import_tasks(
    access: KbAccess = Depends(require_kb_role("viewer")),
    session: Session = Depends(get_session),
) -> dict:
    tasks = session.scalars(
        select(ImportTask)
        .where(ImportTask.kb_id == access.kb.id)
        .order_by(ImportTask.created_at.desc())
    ).all()
    return {"tasks": [task_payload(task) for task in tasks]}


@router.get("/{task_id}")
def get_import_task(
    task_id: str,
    access: KbAccess = Depends(require_kb_role("viewer")),
    session: Session = Depends(get_session),
) -> dict:
    task = session.get(ImportTask, task_id)
    if task is None or task.kb_id != access.kb.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return task_payload(task)


@router.post("/{task_id}/cancel")
def cancel_import_task(
    task_id: str,
    access: KbAccess = Depends(require_kb_role("editor")),
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    task = session.get(ImportTask, task_id)
    if task is None or task.kb_id != access.kb.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    if task.created_by != user.id and not access.is_platform_admin and access.role not in MANAGER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="cannot cancel another user's task"
        )
    if task.status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"task already {task.status}"
        )
    task.status = "cancelled"
    items = session.scalars(
        select(ExtractionItem).where(ExtractionItem.import_task_id == task.id)
    ).all()
    bundle = None
    for item in items:
        if item.status in ("merged", "rejected", "failed"):
            continue
        if item.branch:
            if bundle is None:
                bundle = Bundle(Path(access.kb.local_path))
            gitops.delete_branch(bundle.root, item.branch)
        cleanup_staged(settings, item.id)
        item.status = "rejected"
    session.commit()
    return task_payload(task)
