"""JWT issuance backed by a server-side token whitelist.

The JWT proves possession; the ``user_tokens`` row makes it revocable. A new
login revokes the account's previous tokens (single active session), matching
the reference platform behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db.models import UserToken

ALGORITHM = "HS256"


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class TokenService:
    def __init__(self, secret: str, *, expires_days: int = 7) -> None:
        self.secret = secret
        self.expires_days = expires_days

    def create(
        self,
        session: Session,
        user_id: str,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> str:
        self.revoke_all(session, user_id)
        expires_at = datetime.now(UTC) + timedelta(days=self.expires_days)
        token = jwt.encode(
            {"sub": user_id, "exp": expires_at}, self.secret, algorithm=ALGORITHM
        )
        session.add(
            UserToken(
                user_id=user_id,
                token=token,
                user_agent=user_agent,
                ip_address=ip_address,
                expires_at=expires_at,
            )
        )
        session.flush()
        return token

    def validate(self, session: Session, token: str) -> UserToken | None:
        try:
            payload = jwt.decode(token, self.secret, algorithms=[ALGORITHM])
        except jwt.PyJWTError:
            return None
        record = session.scalar(select(UserToken).where(UserToken.token == token))
        if record is None or record.revoked_at is not None:
            return None
        if _as_aware(record.expires_at) <= datetime.now(UTC):
            return None
        if payload.get("sub") != record.user_id:
            return None
        return record

    def revoke(self, session: Session, token: str) -> None:
        record = session.scalar(select(UserToken).where(UserToken.token == token))
        if record is not None:
            session.delete(record)

    def revoke_all(self, session: Session, user_id: str) -> None:
        session.execute(delete(UserToken).where(UserToken.user_id == user_id))
