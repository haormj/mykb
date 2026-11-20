"""Transitive lineage traceback: which business knowledge is affected by a source."""

from __future__ import annotations

from ..okf.bundle import Bundle


def trace_affected(bundle: Bundle, source_id: str) -> list[str]:
    """Return all business knowledge transitively depending on ``source_id``.

    Walks ``sources`` edges across the knowledge level, so knowledge that was
    fused from other knowledge is reached too.
    """
    business = {concept_id: concept for concept_id, concept in bundle.iter_concepts("knowledge")}
    affected: set[str] = set()
    frontier = {source_id}
    while frontier:
        next_frontier: set[str] = set()
        for concept_id, concept in business.items():
            if concept_id in affected:
                continue
            if frontier & set(concept.source_ids()):
                affected.add(concept_id)
                next_frontier.add(concept_id)
        frontier = next_frontier
    return sorted(affected)
