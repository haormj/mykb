"""Lineage helpers: link business knowledge back to its source concepts."""

from __future__ import annotations

from ..okf.bundle import Bundle
from ..okf.model import Concept


def build_source_entries(
    source_ids: list[str], concepts: list[Concept]
) -> list[dict[str, object]]:
    """Build OKF ``sources`` entries (id + resource + title) for a draft."""
    entries: list[dict[str, object]] = []
    for source_id, concept in zip(source_ids, concepts):
        entry: dict[str, object] = {"id": source_id}
        if concept.resource:
            entry["resource"] = concept.resource
        if concept.title:
            entry["title"] = concept.title
        entries.append(entry)
    return entries


def trace_dependents(bundle: Bundle, source_id: str) -> list[str]:
    """Return ids of business-knowledge concepts whose sources include ``source_id``."""
    dependents: list[str] = []
    for concept_id, concept in bundle.iter_concepts("knowledge"):
        if source_id in concept.source_ids():
            dependents.append(concept_id)
    return dependents
