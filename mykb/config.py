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
    upload_max_bytes: int = 50 * 1024 * 1024
    upload_max_zip_entries: int = 2000
    parser_url: str | None = None
    parser_timeout: float = 60.0
    parser_tier: str = "flash"
    parser_concurrency: int = 2
    parser_token: str | None = None
    conversion_max_assets: int = 100
    conversion_max_asset_bytes: int = 20 * 1024 * 1024
    conversion_max_markdown_bytes: int = 10 * 1024 * 1024
    kb_asset_quota_bytes: int = 512 * 1024 * 1024
    extraction_enabled: bool = True

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def tmp_root(self) -> Path:
        return self.kb_root / ".tmp"

    @property
    def pending_root(self) -> Path:
        """Staging area for documents awaiting extraction review (outside repos)."""
        return self.kb_root / ".pending"

    @property
    def parse_cache_root(self) -> Path:
        return self.kb_root / ".cache" / "parse"


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

    def _int(key: str, default: int) -> int:
        raw = source.get(key, str(default))
        try:
            return int(raw)
        except ValueError as exc:
            raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc

    def _positive_int(key: str, default: int) -> int:
        value = _int(key, default)
        if value <= 0:
            raise ConfigError(f"{key} must be a positive integer, got {value!r}")
        return value

    def _float(key: str, default: float) -> float:
        raw = source.get(key, str(default))
        try:
            return float(raw)
        except ValueError as exc:
            raise ConfigError(f"{key} must be a number, got {raw!r}") from exc

    kb_root = Path(source.get("MYKB_KB_ROOT", "~/.mykb/kbs")).expanduser()
    parser_url = source.get("MYKB_PARSER_URL") or None
    parser_token = source.get("MYKB_PARSER_TOKEN") or None
    extraction_enabled = source.get("MYKB_EXTRACTION_ENABLED", "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    return Settings(
        database_url=source["DATABASE_URL"],
        jwt_secret=source["JWT_SECRET"],
        secret_key=source["MYKB_SECRET_KEY"],
        kb_root=kb_root,
        token_expires_days=_int("TOKEN_EXPIRES_DAYS", 7),
        upload_max_bytes=_int("MYKB_UPLOAD_MAX_BYTES", 50 * 1024 * 1024),
        upload_max_zip_entries=_int("MYKB_UPLOAD_MAX_ZIP_ENTRIES", 2000),
        parser_url=parser_url,
        parser_timeout=_float("MYKB_PARSER_TIMEOUT", 60.0),
        parser_tier=source.get("MYKB_PARSER_TIER", "flash"),
        parser_concurrency=_positive_int("MYKB_PARSER_CONCURRENCY", 2),
        parser_token=parser_token,
        conversion_max_assets=_positive_int("MYKB_CONVERSION_MAX_ASSETS", 100),
        conversion_max_asset_bytes=_positive_int(
            "MYKB_CONVERSION_MAX_ASSET_BYTES", 20 * 1024 * 1024
        ),
        conversion_max_markdown_bytes=_positive_int(
            "MYKB_CONVERSION_MAX_MARKDOWN_BYTES", 10 * 1024 * 1024
        ),
        kb_asset_quota_bytes=_positive_int(
            "MYKB_KB_ASSET_QUOTA_BYTES", 512 * 1024 * 1024
        ),
        extraction_enabled=extraction_enabled,
    )
