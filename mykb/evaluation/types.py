"""Value types shared by the evaluation runner and store."""

from __future__ import annotations

from dataclasses import dataclass, field

# Per-case knowledge-quality classification (see design.md - Decision 2).
CASE_STATUSES: frozenset[str] = frozenset(
    {"hit", "not_retrieved", "unverified", "missing", "b_only"}
)
COVERAGE_STATUSES: frozenset[str] = frozenset({"hit", "not_retrieved", "unverified"})


@dataclass
class CaseData:
    """An evaluation question as fed to the runner / stored on a set."""

    question: str
    reference_answer: str
    expected_concept: str | None = None
    domain: str | None = None
    difficulty: str | None = None
    case_id: str | None = None


@dataclass
class CaseResult:
    """Outcome of one case within a run."""

    question: str
    expected_concept: str | None
    status: str
    a_score: float
    b_answer: str
    b_score: float
    case_id: str | None = None


@dataclass
class EvalResult:
    """Aggregate outcome of running a set against one target knowledge base."""

    a_score: float
    b_score: float
    coverage: float
    case_count: int
    knowledge_version: str | None
    cases: list[CaseResult] = field(default_factory=list)
