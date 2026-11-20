"""Evaluation: curated eval sets, dual scoring, and score trends."""

from .evalset import EvalCase, EvalSet, EvalSetManager
from .runner import EvalRunner, EvalRunResult, similarity
from .scoreboard import Scoreboard

__all__ = [
    "EvalCase",
    "EvalRunResult",
    "EvalRunner",
    "EvalSet",
    "EvalSetManager",
    "Scoreboard",
    "similarity",
]
