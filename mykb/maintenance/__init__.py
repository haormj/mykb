"""Knowledge maintenance: staleness, lineage traceback, lifecycle and rollback."""

from .lifecycle import deprecate, mark_needs_review, re_draft
from .lineage_trace import trace_affected
from .rollback import IndexRollback, concepts_at_commit
from .staleness import StaleSource, detect_stale_sources, is_expired

__all__ = [
    "IndexRollback",
    "StaleSource",
    "concepts_at_commit",
    "deprecate",
    "detect_stale_sources",
    "is_expired",
    "mark_needs_review",
    "re_draft",
    "trace_affected",
]
