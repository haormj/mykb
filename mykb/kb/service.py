"""Knowledge-base registration and git repository lifecycle."""

from __future__ import annotations

import re
import shutil
import unicodedata
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..crypto import encrypt_secret
from ..db.models import KbMember, KnowledgeBase, User
from . import gitops


class KnowledgeBaseError(ValueError):
    """A user-facing knowledge-base error."""


class KnowledgeBaseConflict(KnowledgeBaseError):
    """A uniqueness or path conflict."""


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKC", name.strip().lower())
    chars: list[str] = []
    for char in text:
        if char.isalnum():
            chars.append(char)
        elif char in " -_/":
            chars.append("-")
    slug = re.sub(r"-+", "-", "".join(chars)).strip("-")
    return slug or "kb"


def _unique_slug(session: Session, base: str) -> str:
    candidate = base
    suffix = 1
    while session.scalar(select(KnowledgeBase).where(KnowledgeBase.slug == candidate)) is not None:
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


def create_knowledge_base(
    session: Session,
    settings: Settings,
    *,
    owner: User,
    name: str,
    git_url: str | None = None,
    git_branch: str = "main",
    git_token: str | None = None,
) -> KnowledgeBase:
    name = name.strip()
    if not name:
        raise KnowledgeBaseError("name is required")
    if session.scalar(select(KnowledgeBase).where(KnowledgeBase.name == name)) is not None:
        raise KnowledgeBaseConflict("knowledge base name already exists")

    kb_id = str(uuid.uuid4())
    slug = _unique_slug(session, slugify(name))
    local_path = settings.kb_root / f"{slug}-{kb_id[:8]}"
    if local_path.exists():
        raise KnowledgeBaseConflict(f"local path already in use: {local_path}")

    encrypted = encrypt_secret(settings.secret_key, git_token) if git_token else None
    try:
        if git_url:
            gitops.clone_or_init_with_remote(
                local_path,
                title=name,
                git_url=git_url,
                branch=git_branch,
                token=git_token,
            )
        else:
            gitops.init_local_repo(local_path, title=name)

        kb = KnowledgeBase(
            id=kb_id,
            name=name,
            slug=slug,
            git_url=git_url,
            git_branch=git_branch,
            local_path=str(local_path),
            git_credential_enc=encrypted,
            owner_id=owner.id,
        )
        session.add(kb)
        session.flush()
        session.add(KbMember(kb_id=kb_id, user_id=owner.id, role="owner"))
        session.commit()
        return kb
    except Exception:
        session.rollback()
        if local_path.exists():
            shutil.rmtree(local_path, ignore_errors=True)
        raise


def remote_credential(kb: KnowledgeBase, settings: Settings) -> str | None:
    if not kb.git_credential_enc:
        return None
    from ..crypto import decrypt_secret

    return decrypt_secret(settings.secret_key, kb.git_credential_enc)


def bind_remote(
    session: Session,
    settings: Settings,
    kb: KnowledgeBase,
    *,
    git_url: str,
    git_branch: str | None = None,
    git_token: str | None = None,
) -> KnowledgeBase:
    branch = git_branch or kb.git_branch
    existing_token = git_token or remote_credential(kb, settings)
    gitops.bind_remote(
        Path(kb.local_path), git_url=git_url, branch=branch, token=existing_token
    )
    kb.git_url = git_url
    kb.git_branch = branch
    if git_token:
        kb.git_credential_enc = encrypt_secret(settings.secret_key, git_token)
    session.commit()
    return kb


def accessible_bases(
    session: Session, *, user_id: str, is_platform_admin: bool
) -> list[tuple[KnowledgeBase, str]]:
    if is_platform_admin:
        return [
            (kb, "owner")
            for kb in session.scalars(select(KnowledgeBase).order_by(KnowledgeBase.created_at)).all()
        ]

    rows = session.execute(
        select(KnowledgeBase, KbMember.role)
        .join(KbMember, KbMember.kb_id == KnowledgeBase.id)
        .where(KbMember.user_id == user_id)
        .order_by(KnowledgeBase.created_at)
    ).all()
    return [(kb, role) for kb, role in rows]
