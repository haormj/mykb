"""Account lifecycle and platform role lookups."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Role, User, UserRole
from .passwords import hash_password, verify_password


class AccountError(ValueError):
    """A user-facing account validation error."""


def _role_by_name(session: Session, name: str) -> Role | None:
    return session.scalar(select(Role).where(Role.name == name))


def ensure_default_role(session: Session, user: User, role_name: str = "user") -> None:
    role = _role_by_name(session, role_name)
    if role is None:
        from ..db.bootstrap import ensure_role

        role = ensure_role(session, role_name, ["basic"], "Regular platform user")
    exists = session.scalar(
        select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
    )
    if exists is None:
        session.add(UserRole(user_id=user.id, role_id=role.id))


def register_account(
    session: Session,
    *,
    username: str,
    password: str,
    email: str | None = None,
    display_name: str | None = None,
) -> User:
    username = username.strip()
    if not (3 <= len(username) <= 50):
        raise AccountError("username must be between 3 and 50 characters")
    if len(password) < 6:
        raise AccountError("password must be at least 6 characters")
    if session.scalar(select(User).where(User.username == username)) is not None:
        raise AccountError("username already exists")
    if email and session.scalar(select(User).where(User.email == email)) is not None:
        raise AccountError("email already exists")

    user = User(
        username=username,
        password_hash=hash_password(password),
        email=email,
        display_name=display_name or username,
    )
    session.add(user)
    session.flush()
    ensure_default_role(session, user)
    session.flush()
    return user


def authenticate(session: Session, username: str, password: str) -> User | None:
    user = session.scalar(select(User).where(User.username == username))
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def roles_for_user(session: Session, user_id: str) -> list[Role]:
    return list(
        session.scalars(
            select(Role).join(UserRole, UserRole.role_id == Role.id).where(
                UserRole.user_id == user_id
            )
        ).all()
    )


def permissions_for_user(session: Session, user_id: str) -> tuple[list[str], list[str]]:
    roles = roles_for_user(session, user_id)
    permissions: list[str] = []
    for role in roles:
        for item in role.permissions or []:
            if isinstance(item, str):
                permissions.append(item)
    return [role.name for role in roles], permissions


def find_or_create_sso_user(
    session: Session,
    *,
    provider: str,
    external_id: str,
    username: str,
    display_name: str | None = None,
    email: str | None = None,
) -> User:
    user = session.scalar(
        select(User).where(User.sso_provider == provider, User.sso_user_id == external_id)
    )
    if user is not None:
        return user
    base_username = username.strip() or f"{provider}-{external_id}"
    candidate = base_username
    suffix = 1
    while session.scalar(select(User).where(User.username == candidate)) is not None:
        suffix += 1
        candidate = f"{base_username}-{suffix}"
    user = User(
        username=candidate,
        display_name=display_name or candidate,
        email=email,
        sso_provider=provider,
        sso_user_id=external_id,
    )
    session.add(user)
    session.flush()
    ensure_default_role(session, user)
    session.flush()
    return user
