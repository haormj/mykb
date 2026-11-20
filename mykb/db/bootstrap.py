"""Idempotent platform bootstrap: roles and the first administrator."""

from __future__ import annotations

import os
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.passwords import hash_password
from .models import Role, User, UserRole

ROLE_DEFINITIONS: tuple[tuple[str, list[str], str], ...] = (
    ("admin", ["all"], "Platform administrator with full permissions"),
    ("user", ["basic"], "Regular platform user"),
)


def ensure_role(session: Session, name: str, permissions: list[str], description: str) -> Role:
    role = session.scalar(select(Role).where(Role.name == name))
    if role is None:
        role = Role(name=name, permissions=permissions, description=description)
        session.add(role)
        session.flush()
    return role


def ensure_roles(session: Session) -> dict[str, Role]:
    return {
        name: ensure_role(session, name, permissions, description)
        for name, permissions, description in ROLE_DEFINITIONS
    }


def ensure_admin(
    session: Session,
    *,
    username: str,
    password: str,
    email: str | None = None,
    display_name: str = "Administrator",
) -> User:
    """Create the administrator if missing; never overwrite an existing account."""
    imports = {row.username: row for row in session.scalars(select(User)).all()}
    existing = imports.get(username)
    if existing is not None:
        return existing

    admin_role = ensure_role(session, "admin", ["all"], "Platform administrator")
    user = User(
        username=username,
        password_hash=hash_password(password),
        email=email,
        display_name=display_name,
    )
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role_id=admin_role.id))
    session.flush()
    return user


def bootstrap(session: Session, env: Mapping[str, str] | None = None) -> None:
    source = os.environ if env is None else env
    ensure_roles(session)
    username = source.get("ADMIN_USERNAME")
    password = source.get("ADMIN_PASSWORD")
    if username and password:
        ensure_admin(
            session,
            username=username,
            password=password,
            email=source.get("ADMIN_EMAIL"),
            display_name=source.get("ADMIN_DISPLAY_NAME", "Administrator"),
        )
    session.commit()


def main() -> int:
    import argparse

    from ..config import load_database_url
    from .session import create_db_engine, create_session_factory

    parser = argparse.ArgumentParser(description="Bootstrap platform roles and admin")
    parser.parse_args()
    engine = create_db_engine(load_database_url())
    factory = create_session_factory(engine)
    with factory() as session:
        bootstrap(session)
    print("bootstrap complete")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
