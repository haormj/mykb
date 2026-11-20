"""Knowledge-base registration endpoints."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import Settings
from ...db.models import KnowledgeBase
from ...kb.gitops import GitError
from ...kb.service import (
    KnowledgeBaseConflict,
    KnowledgeBaseError,
    accessible_bases,
    bind_remote,
    create_knowledge_base,
)
from ..deps import (
    AuthUser,
    KbAccess,
    get_current_user,
    get_session,
    get_settings,
    require_kb_role,
)

router = APIRouter(prefix="/kbs", tags=["knowledge-bases"])


class KbCreate(BaseModel):
    name: str
    git_url: str | None = None
    git_branch: str = "main"
    git_token: str | None = None


class KbPatch(BaseModel):
    name: str | None = None
    git_branch: str | None = None


class RemoteBind(BaseModel):
    git_url: str
    git_branch: str | None = None
    git_token: str | None = None


def kb_payload(kb: KnowledgeBase, role: str) -> dict:
    return {
        "id": kb.id,
        "name": kb.name,
        "slug": kb.slug,
        "git_url": kb.git_url,
        "git_branch": kb.git_branch,
        "local_path": kb.local_path,
        "owner_id": kb.owner_id,
        "my_role": role,
        "has_remote": bool(kb.git_url),
    }


@router.get("")
def list_kbs(
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    rows = accessible_bases(
        session, user_id=user.id, is_platform_admin=user.is_platform_admin
    )
    return {"knowledge_bases": [kb_payload(kb, role) for kb, role in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_kb(
    payload: KbCreate,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    from ...db.models import User

    owner = session.get(User, user.id)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    try:
        kb = create_knowledge_base(
            session,
            settings,
            owner=owner,
            name=payload.name,
            git_url=payload.git_url or None,
            git_branch=payload.git_branch or "main",
            git_token=payload.git_token or None,
        )
    except KnowledgeBaseConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (KnowledgeBaseError, GitError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return kb_payload(kb, "owner")


@router.get("/{kb_id}")
def get_kb(access: KbAccess = Depends(require_kb_role("viewer"))) -> dict:
    return kb_payload(access.kb, access.role)


@router.patch("/{kb_id}")
def patch_kb(
    payload: KbPatch,
    access: KbAccess = Depends(require_kb_role("admin")),
    session: Session = Depends(get_session),
) -> dict:
    kb = access.kb
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
        existing = session.scalar(
            select(KnowledgeBase).where(KnowledgeBase.name == name, KnowledgeBase.id != kb.id)
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="knowledge base name already exists"
            )
        kb.name = name
    if payload.git_branch is not None:
        kb.git_branch = payload.git_branch
    session.commit()
    return kb_payload(kb, access.role)


@router.delete("/{kb_id}")
def delete_kb(
    access: KbAccess = Depends(require_kb_role("owner")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    kb = access.kb
    source = Path(kb.local_path)
    if source.exists():
        trash = settings.kb_root / ".trash"
        trash.mkdir(parents=True, exist_ok=True)
        target = trash / kb.id
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        source.rename(target)
    session.delete(kb)
    session.commit()
    return {"deleted": kb.id}


@router.post("/{kb_id}/remote")
def bind_kb_remote(
    payload: RemoteBind,
    access: KbAccess = Depends(require_kb_role("owner")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        kb = bind_remote(
            session,
            settings,
            access.kb,
            git_url=payload.git_url,
            git_branch=payload.git_branch,
            git_token=payload.git_token,
        )
    except GitError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return kb_payload(kb, access.role)
