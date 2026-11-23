"""Evaluation: platform-level eval sets, dual scoring, and score trends."""

from .runner import EvalRunner, similarity
from .types import CaseData, CaseResult, EvalResult

__all__ = [
    "CaseData",
    "CaseResult",
    "EvalResult",
    "EvalRunner",
    "similarity",
]
