"""Build OKF source concepts from conversion results."""

from __future__ import annotations

from pathlib import Path

from ..conversion.base import ConversionResult, RawDocument
from ..okf.model import Concept
from ..util import now_iso


def build_source_concept(
    *,
    result: ConversionResult,
    document: RawDocument,
    connector_name: str,
    source_type: str,
    resource: str,
    task_id: str,
) -> Concept:
    """Wrap converted markdown with source provenance and OKF metadata."""
    title = result.title or Path(document.name).stem
    frontmatter: dict[str, object] = {
        "type": source_type,
        "title": title,
        "resource": resource,
        "generated": {"by": f"process:{connector_name}", "at": now_iso()},
        "status": "draft",
        "tags": ["source", connector_name],
        "x-connector": connector_name,
        "x-import-task": task_id,
        "x-source-format": document.suffix.lstrip("."),
        "x-original-name": document.name,
        "x-original-sha256": document.sha256(),
        "x-original-size": len(document.data),
        "x-parsed-by": result.producer,
    }
    for key, value in result.frontmatter.items():
        frontmatter.setdefault(key, value)
    if result.warnings:
        frontmatter["x-warnings"] = list(result.warnings)
    return Concept(frontmatter=frontmatter, body=result.markdown)
