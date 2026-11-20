"""Markdown / file-directory connector.

Treats a local directory tree of markdown files as a read-only source. Each file
becomes one :class:`RawItem`; normalize wraps it in an OKF source concept.
"""

from __future__ import annotations

from pathlib import Path

from ..okf.model import Concept, FrontmatterError, parse
from .base import BaseConnector, RawItem
from .registry import register_connector


def _split_body(text: str) -> tuple[dict, str]:
    """Strip a leading OKF frontmatter block, if present, from source content."""
    try:
        frontmatter, body = parse(text)
        return frontmatter, body
    except FrontmatterError:
        return {}, text


@register_connector
class MarkdownDirConnector(BaseConnector):
    name = "markdown-dir"
    source_type = "源数据"

    def __init__(
        self,
        source_dir: str | Path,
        *,
        base_uri: str | None = None,
        source_type: str | None = None,
        pattern: str = "**/*.md",
    ) -> None:
        super().__init__(base_uri=base_uri, source_type=source_type)
        self.source_dir = Path(source_dir)
        self.pattern = pattern

    def sync(self) -> list[RawItem]:
        items: list[RawItem] = []
        for path in sorted(self.source_dir.glob(self.pattern)):
            if not path.is_file():
                continue
            rel = path.relative_to(self.source_dir).as_posix()
            text = path.read_text(encoding="utf-8")
            source_fm, body = _split_body(text)
            resource = self.resource_for(rel) if self.base_uri else path.resolve().as_uri()
            items.append(
                RawItem(
                    key=rel,
                    resource=resource,
                    content=body,
                    title=source_fm.get("title") or path.stem,
                    metadata={"frontmatter": source_fm},
                )
            )
        return items

    def normalize(self, items: list[RawItem]) -> list[Concept]:
        return super().normalize(items)
