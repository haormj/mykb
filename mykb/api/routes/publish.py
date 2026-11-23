"""Manual publish, publish status and snapshot version endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.models import PublishTask, WeKnoraIndexVersion
from ...retrieval.sync import get_head_commit
from ...retrieval.tasks import ACTIVE_STATUSES, run_publish_task, task_payload
from ..deps import (
    AuthUser,
    KbAccess,
    get_current_user,
    get_session,
    get_settings,
    require_kb_role,
)

router = APIRouter(prefix="/kbs/{kb_id}", tags=["publish"])


@router.post("/publish", status_code=status.HTTP_202_ACCEPTED)
def create_publish(
    request: Request,
    access: KbAccess = Depends(require_kb_role("admin")),
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
    settings=Depends(get_settings),
) -> dict:
    active = session.scalar(
        select(PublishTask)
        .where(
            PublishTask.kb_id == access.kb.id,
            PublishTask.status.in_(ACTIVE_STATUSES),
        )
        .limit(1)
    )
    if active is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a publish is already in progress",
        )

    git_commit = get_head_commit(access.kb.local_path) or "unversioned"
    task = PublishTask(
        kb_id=access.kb.id,
        git_commit=git_commit,
        status="queued",
        created_by=user.id,
    )
    session.add(task)
    session.commit()

    request.app.state.import_executor.submit(
        run_publish_task,
        task.id,
        session_factory=request.app.state.session_factory,
        backend=request.app.state.retrieval_backend,
        retention=getattr(settings, "weknora_retention", 3),
        locks=request.app.state.kb_locks,
        lock_guard=request.app.state.kb_locks_guard,
    )
    return task_payload(task)


@router.get("/publish/{task_id}")
def get_publish(
    task_id: str,
    access: KbAccess = Depends(require_kb_role("viewer")),
    session: Session = Depends(get_session),
) -> dict:
    task = session.get(PublishTask, task_id)
    if task is None or task.kb_id != access.kb.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="publish task not found"
        )
    return task_payload(task)


@router.get("/versions")
def list_versions(
    access: KbAccess = Depends(require_kb_role("viewer")),
    session: Session = Depends(get_session),
) -> dict:
    rows = session.scalars(
        select(WeKnoraIndexVersion)
        .where(WeKnoraIndexVersion.kb_id == access.kb.id)
        .order_by(WeKnoraIndexVersion.created_at.desc())
    ).all()
    active_id = access.kb.active_weknora_version_id
    return {
        "versions": [
            {
                "id": row.id,
                "git_commit": row.git_commit,
                "status": row.status,
                "doc_total": row.doc_total,
                "doc_completed": row.doc_completed,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "ready_at": row.ready_at.isoformat() if row.ready_at else None,
                "is_active": row.id == active_id,
            }
            for row in rows
        ]
    }
