"""Document conversion types shared by upload connectors and parser providers.

A conversion happens after ``sync`` has produced raw bytes and before the
normalize step wraps the markdown in OKF frontmatter. Providers are selected by
suffix/MIME so new formats can be added without touching the import pipeline.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

SUPPORTED_SUFFIXES = frozenset({".md", ".markdown", ".docx"})
MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})
ALLOWED_ASSET_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})


class ConversionError(ValueError):
    """A per-item conversion failure (the rest of the task may continue)."""


class UnsupportedFormatError(ConversionError):
    """No provider accepts the document format."""


class ConversionNotConfiguredError(ConversionError):
    """The format needs a conversion service that has not been configured."""


class ConversionLimitError(ConversionError):
    """A converted document exceeds a configured output limit."""


class ConversionUnavailableError(RuntimeError):
    """The conversion service is unreachable or broken; retry the whole task."""


class ConversionAuthError(ConversionUnavailableError):
    """The conversion service rejected our credentials."""


@dataclass(frozen=True)
class RawDocument:
    """A single raw file produced by a connector's sync stage."""

    key: str
    name: str
    data: bytes
    mime: str = "application/octet-stream"
    suffix: str = ""

    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


@dataclass(frozen=True)
class Asset:
    """A binary asset produced by conversion, renamed by the ingest pipeline."""

    name: str
    data: bytes
    source_name: str | None = None


@dataclass
class ConversionResult:
    """Markdown plus assets and provenance produced from one raw document."""

    markdown: str
    title: str | None = None
    assets: list[Asset] = field(default_factory=list)
    frontmatter: dict[str, Any] = field(default_factory=dict)
    producer: str = "passthrough"
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class DocumentConverter(Protocol):
    """A provider that turns one raw document into markdown."""

    name: str

    def supports(self, suffix: str, mime: str) -> bool:
        """Return whether this provider accepts the document."""

    def convert(self, document: RawDocument) -> ConversionResult:
        """Convert one document or raise a :class:`ConversionError`."""
