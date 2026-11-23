"""FastAPI dependencies: session, identity and knowledge-base authorization."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..auth.service import permissions_for_user
from ..auth.tokens import TokenService
from ..db.models import KbMember, KnowledgeBase, User

KB_ROLE_RANK: dict[str, int] = {"viewer": 1, "editor": 2, "admin": 3, "owner": 4}

PLATFORM_ADMIN_ROLE = "admin"


@dataclass
class AuthUser:
    id: str
    username: str
    display_name: str
    email: str | None
    roles: list[str]
    permissions: list[str]

    @property
    def is_platform_admin(self) -> bool:
        return PLATFORM_ADMIN_ROLE in self.roles


@dataclass
class KbAccess:
    kb: KnowledgeBase
    role: str
    is_platform_admin: bool = False


def get_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_token_service(request: Request) -> TokenService:
    return request.app.state.token_service


def get_settings(request: Request):
    return request.app.state.settings


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
    tokens: TokenService = Depends(get_token_service),
) -> AuthUser:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    token = header[len("Bearer ") :].strip()
    record = tokens.validate(session, token)
    if record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = session.get(User, record.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    roles, permissions = permissions_for_user(session, user.id)
    return AuthUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        roles=roles,
        permissions=permissions,
    )


def require_platform_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if not user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin required"
        )
    return user


def ensure_kb_role(
    *,
    session: Session,
    user: AuthUser,
    kb_id: str,
    min_role: str,
) -> KbAccess:
    """Load the knowledge base and enforce a minimum role, or raise ``HTTPException``.

    Shared by the ``require_kb_role`` dependency and multi-target code paths
    (such as running an eval set against several knowledge bases at once) that
    cannot rely on a single ``kb_id`` path parameter.
    """
    if min_role not in KB_ROLE_RANK:
        raise ValueError(f"unknown kb role '{min_role}'")
    kb = session.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    if user.is_platform_admin:
        return KbAccess(kb=kb, role="owner", is_platform_admin=True)
    member = session.get(KbMember, (kb_id, user.id))
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not a knowledge base member"
        )
    if KB_ROLE_RANK.get(member.role, 0) < KB_ROLE_RANK[min_role]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires at least '{min_role}' role",
        )
    return KbAccess(kb=kb, role=member.role, is_platform_admin=False)


def require_kb_role(min_role: str):
    """Build a dependency that loads the knowledge base and enforces a minimum role.

    ``min_role`` is validated eagerly so a typo fails at import time.
    """
    if min_role not in KB_ROLE_RANK:
        raise ValueError(f"unknown kb role '{min_role}'")

    def dependency(
        kb_id: str,
        user: AuthUser = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> KbAccess:
        return ensure_kb_role(session=session, user=user, kb_id=kb_id, min_role=min_role)

    return dependency
