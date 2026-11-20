"""Small shared helpers."""

from __future__ import annotations

import datetime as dt


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string with a ``Z`` suffix."""
    return (
        dt.datetime.now(dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def now_iso_us() -> str:
    """Current UTC time with microsecond precision (for unique run records)."""
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> dt.datetime:
    """Parse an ISO-8601 string, accepting a trailing ``Z``."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed
