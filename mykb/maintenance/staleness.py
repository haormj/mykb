"""Staleness and change detection for source data."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass

from ..okf.bundle import Bundle
from ..okf.model import Concept
from ..util import parse_iso


@dataclass
class StaleSource:
    concept_id: str
    reason: str  # "stale_after" | "resource_changed"


def is_expired(concept: Concept, *, now: dt.datetime | None = None) -> bool:
    """True when a concept's ``stale_after`` has passed."""
    raw = concept.stale_after
    if not raw:
        return False
    try:
        deadline = parse_iso(raw)
    except ValueError:
        return False
    current = now or dt.datetime.now(dt.UTC)
    return deadline <= current


def detect_stale_sources(
    bundle: Bundle,
    *,
    now: dt.datetime | None = None,
    resource_checker: Callable[[Concept], bool] | None = None,
) -> list[StaleSource]:
    """Detect expired sources and optionally sources whose external resource changed.

    ``resource_checker`` is a pluggable freshness probe for ``resource`` targets
    (HTTP head, git ref, file mtime, ...). Without it only ``stale_after`` is used.
    """
    stale: list[StaleSource] = []
    for concept_id, concept in bundle.iter_concepts("raw"):
        if is_expired(concept, now=now):
            stale.append(StaleSource(concept_id, "stale_after"))
        elif resource_checker is not None and resource_checker(concept):
            stale.append(StaleSource(concept_id, "resource_changed"))
    return stale
