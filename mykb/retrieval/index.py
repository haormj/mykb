"""Rules for what enters the retrieval index."""

from __future__ import annotations

from ..okf.bundle import Bundle
from ..okf.model import Concept


def select_indexable_knowledge(bundle: Bundle) -> list[Concept]:
    """Only verified and stable business knowledge may be indexed."""
    return [c for _, c in bundle.iter_concepts("knowledge") if c.is_verified_stable()]


def select_code_sources(bundle: Bundle) -> list[Concept]:
    """Read-only code reference concepts feed the code engine, never the RAG index."""
    return [c for _, c in bundle.iter_concepts("raw") if c.type == "代码"]
