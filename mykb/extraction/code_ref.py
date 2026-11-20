"""Read-only code references.

Code lives in its own git repository. Rather than copying code bodies into the
bundle, a ``代码`` source concept records a reference (``resource`` points at the
code file) plus a short summary. Business knowledge extracted from it keeps the
code resource and never embeds the code body.
"""

from __future__ import annotations

from pathlib import Path

from ..okf.bundle import Bundle
from ..okf.model import Concept
from ..util import now_iso


def _slug(resource: str) -> str:
    cleaned = resource.replace("://", "/")
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in cleaned)
    return safe[-80:].strip("_") or "code"


def create_code_source(
    bundle: Bundle,
    *,
    resource: str,
    title: str | None = None,
    summary: str | None = None,
) -> str:
    """Create a read-only code-reference source concept; the code body is not copied."""
    concept = Concept(
        frontmatter={
            "type": "代码",
            "title": title or Path(resource).name,
            "resource": resource,
            "generated": {"by": "process:code-ref", "at": now_iso()},
            "status": "draft",
            "x-source-readonly": True,
        },
        body=summary
        or f"代码引用：{resource}\n（代码本体不复制进 bundle，仅按 resource 引用）\n",
    )
    return bundle.write_concept(concept, "raw", f"code/{_slug(resource)}")
