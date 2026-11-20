"""Lifecycle transitions: needs-review, deprecation, and re-extraction."""

from __future__ import annotations

from ..extraction.drafter import Drafter
from ..okf.bundle import Bundle
from ..okf.model import Concept


def _with_status(concept: Concept, status: str, **extra) -> Concept:
    frontmatter = dict(concept.frontmatter)
    frontmatter["status"] = status
    frontmatter.update(extra)
    return Concept(frontmatter=frontmatter, body=concept.body, id=concept.id)


def mark_needs_review(bundle: Bundle, concept_ids: list[str], *, reason: str | None = None) -> list[str]:
    """Set ``status: needs-review`` on the given business knowledge concepts."""
    updated: list[str] = []
    for concept_id in concept_ids:
        try:
            concept = bundle.read_concept(concept_id)
        except FileNotFoundError:
            continue
        extra = {"x-review-reason": reason} if reason else {}
        bundle.save_concept(_with_status(concept, "needs-review", **extra))
        updated.append(concept_id)
    return updated


def deprecate(bundle: Bundle, concept_id: str, *, superseded_by: str) -> str:
    """Mark a concept deprecated and point it at its replacement."""
    concept = bundle.read_concept(concept_id)
    bundle.save_concept(_with_status(concept, "deprecated", superseded_by=superseded_by))
    return concept_id


def re_draft(
    bundle: Bundle,
    concept_id: str,
    drafter: Drafter,
    *,
    relative_path: str | None = None,
    title: str | None = None,
) -> str:
    """Re-extract a needs-review concept from its original sources (fresh draft)."""
    concept = bundle.read_concept(concept_id)
    source_ids = concept.source_ids()
    if not source_ids:
        raise ValueError(f"concept '{concept_id}' has no sources to re-extract from")
    rel = relative_path or concept_id.split("/", 1)[1]
    return drafter.draft_to_bundle(source_ids, relative_path=rel, title=title or concept.title)
