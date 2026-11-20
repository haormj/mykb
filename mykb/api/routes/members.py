"""Knowledge-base membership and role management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.models import KbMember, User
from ..deps import KB_ROLE_RANK, AuthUser, KbAccess, get_current_user, get_session, require_kb_role

router = APIRouter(prefix="/kbs/{kb_id}/members", tags=["members"])

ASSIGNABLE_BY = {
    "admin": {"editor", "viewer"},
    "owner": {"admin", "editor", "viewer"},
}


class MemberIn(BaseModel):
    username: str | None = None
    user_id: str | None = None
    role: str = "viewer"


class MemberRoleIn(BaseModel):
    role: str


def _rank(role: str) -> int:
    return KB_ROLE_RANK.get(role, 0)


def _actor_rank(access: KbAccess) -> int:
    return 99 if access.is_platform_admin else _rank(access.role)


def _assert_can_assign(access: KbAccess, new_role: str) -> None:
    if new_role not in KB_ROLE_RANK or new_role == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="role must be one of viewer, editor, admin",
        )
    if access.is_platform_admin:
        return
    allowed = ASSIGNABLE_BY.get(access.role, set())
    if new_role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"cannot assign role '{new_role}'",
        )


def _resolve_user(session: Session, payload: MemberIn) -> User:
    if payload.user_id:
        user = session.get(User, payload.user_id)
    elif payload.username:
        user = session.scalar(select(User).where(User.username == payload.username))
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="username or user_id is required"
        )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("")
def list_members(
    access: KbAccess = Depends(require_kb_role("viewer")),
    session: Session = Depends(get_session),
) -> dict:
    rows = session.execute(
        select(KbMember, User)
        .join(User, User.id == KbMember.user_id)
        .where(KbMember.kb_id == access.kb.id)
        .order_by(KbMember.created_at)
    ).all()
    return {
        "members": [
            {
                "user_id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "email": user.email,
                "role": member.role,
            }
            for member, user in rows
        ]
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def add_member(
    payload: MemberIn,
    access: KbAccess = Depends(require_kb_role("admin")),
    session: Session = Depends(get_session),
) -> dict:
    _assert_can_assign(access, payload.role)
    user = _resolve_user(session, payload)
    existing = session.get(KbMember, (access.kb.id, user.id))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="user is already a member")
    session.add(KbMember(kb_id=access.kb.id, user_id=user.id, role=payload.role))
    session.commit()
    return {"user_id": user.id, "username": user.username, "role": payload.role}


@router.patch("/{user_id}")
def update_member(
    user_id: str,
    payload: MemberRoleIn,
    access: KbAccess = Depends(require_kb_role("admin")),
    session: Session = Depends(get_session),
) -> dict:
    _assert_can_assign(access, payload.role)
    member = session.get(KbMember, (access.kb.id, user_id))
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="member not found")
    if member.role == "owner" and not access.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="use ownership transfer for the owner"
        )
    if member.role != "owner" and _rank(member.role) >= _actor_rank(access):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="cannot modify an equal or higher role"
        )
    member.role = payload.role
    session.commit()
    return {"user_id": user_id, "role": member.role}


@router.delete("/{user_id}")
def remove_member(
    user_id: str,
    access: KbAccess = Depends(require_kb_role("admin")),
    session: Session = Depends(get_session),
) -> dict:
    member = session.get(KbMember, (access.kb.id, user_id))
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="member not found")
    if member.role == "owner" and not access.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="the owner cannot be removed"
        )
    if not access.is_platform_admin and _rank(member.role) >= _actor_rank(access):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="cannot remove an equal or higher role"
        )
    session.delete(member)
    session.commit()
    return {"removed": user_id}


@router.post("/{user_id}/transfer")
def transfer_owner(
    user_id: str,
    access: KbAccess = Depends(require_kb_role("owner")),
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    target = session.get(KbMember, (access.kb.id, user_id))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="member not found")
    if target.user_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="already the owner"
        )
    current_owner = session.scalar(
        select(KbMember).where(
            KbMember.kb_id == access.kb.id, KbMember.role == "owner"
        )
    )
    if current_owner is not None:
        current_owner.role = "admin"
    target.role = "owner"
    session.commit()
    return {"owner_id": target.user_id}
