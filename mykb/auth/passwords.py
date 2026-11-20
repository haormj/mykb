"""Password hashing helpers (bcrypt)."""

from __future__ import annotations

import bcrypt

_MAX_BCRYPT_BYTES = 72


def hash_password(password: str) -> str:
    payload = password.encode("utf-8")[:_MAX_BCRYPT_BYTES]
    return bcrypt.hashpw(payload, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    payload = password.encode("utf-8")[:_MAX_BCRYPT_BYTES]
    try:
        return bcrypt.checkpw(payload, password_hash.encode("utf-8"))
    except ValueError:
        return False
