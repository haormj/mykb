"""Platform-level administration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...auth.service import permissions_for_user
from ...db.models import User
from ..deps import AuthUser, get_session, require_platform_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
def list_users(
    _admin: AuthUser = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict:
    users = session.scalars(select(User).order_by(User.created_at)).all()
    payload = []
    for user in users:
        roles, _ = permissions_for_user(session, user.id)
        payload.append(
            {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "email": user.email,
                "roles": roles,
            }
        )
    return {"users": payload}
