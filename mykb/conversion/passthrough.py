"""Markdown passthrough converter.

Markdown uploads keep their existing frontmatter and body; no parser is called.
"""

from __future__ import annotations

from pathlib import Path

from ..okf.model import FrontmatterError, parse
from .base import (
    MARKDOWN_SUFFIXES,
    ConversionError,
    ConversionResult,
    RawDocument,
)


class MarkdownPassthroughConverter:
    """Treat an uploaded markdown file as already converted."""

    name = "passthrough"

    def supports(self, suffix: str, mime: str) -> bool:
        return suffix.lower() in MARKDOWN_SUFFIXES or mime in {
            "text/markdown",
            "text/x-markdown",
        }

    def convert(self, document: RawDocument) -> ConversionResult:
        try:
            text = document.data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ConversionError("markdown file must be UTF-8 encoded") from exc
        try:
            frontmatter, body = parse(text)
        except FrontmatterError:
            frontmatter, body = {}, text
        title = frontmatter.get("title") or Path(document.name).stem
        return ConversionResult(
            markdown=body,
            title=str(title),
            frontmatter=dict(frontmatter),
            producer="passthrough",
        )
