"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

REQUIRED_KEYS = ("DATABASE_URL", "JWT_SECRET", "MYKB_SECRET_KEY")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret: str
    secret_key: str
    kb_root: Path
    token_expires_days: int = 7

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


def load_database_url(env: Mapping[str, str] | None = None) -> str:
    """Require only ``DATABASE_URL`` (for migrations and bootstrap scripts)."""
    source = os.environ if env is None else env
    database_url = source.get("DATABASE_URL")
    if not database_url:
        raise ConfigError("missing required configuration: DATABASE_URL")
    return database_url


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    source = os.environ if env is None else env
    missing = [key for key in REQUIRED_KEYS if not source.get(key)]
    if missing:
        joined = ", ".join(missing)
        raise ConfigError(f"missing required configuration: {joined}")

    raw_days = source.get("TOKEN_EXPIRES_DAYS", "7")
    try:
        token_expires_days = int(raw_days)
    except ValueError as exc:
        raise ConfigError(f"TOKEN_EXPIRES_DAYS must be an integer, got {raw_days!r}") from exc

    kb_root = Path(source.get("MYKB_KB_ROOT", "~/.mykb/kbs")).expanduser()
    return Settings(
        database_url=source["DATABASE_URL"],
        jwt_secret=source["JWT_SECRET"],
        secret_key=source["MYKB_SECRET_KEY"],
        kb_root=kb_root,
        token_expires_days=token_expires_days,
    )
