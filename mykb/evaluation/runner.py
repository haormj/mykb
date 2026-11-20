"""Evaluation runner producing knowledge-quality (A) and end-to-end (B) scores."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..okf.bundle import Bundle
from ..retrieval.engines.markdown_rag import tokens
from ..retrieval.interface import RetrievalService
from ..util import now_iso_us
from .evalset import EvalCase, EvalSetManager
from .scoreboard import Scoreboard


def similarity(a: str, b: str) -> float:
    """Token-set F1 similarity in ``[0, 1]`` (deterministic, offline)."""
    ta = set(tokens(a))
    tb = set(tokens(b))
    if not ta or not tb:
        return 0.0
    intersection = len(ta & tb)
    if intersection == 0:
        return 0.0
    precision = intersection / len(ta)
    recall = intersection / len(tb)
    return 2 * precision * recall / (precision + recall)


@dataclass
class CaseResult:
    question: str
    expected_concept: str | None
    a_hit: bool
    a_score: float
    b_answer: str
    b_score: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvalRunResult:
    set_name: str
    knowledge_version: str | None
    created_at: str
    a_score: float
    b_score: float
    cases: list[CaseResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["cases"] = [case.to_dict() for case in self.cases]
        return payload


class EvalRunner:
    """Runs an eval set against the unified retrieval interface."""

    def __init__(
        self,
        bundle: Bundle,
        service: RetrievalService,
        *,
        answerer=None,
        scoreboard: Scoreboard | None = None,
    ) -> None:
        self.bundle = bundle
        self.service = service
        self.answerer = answerer
        self.scoreboard = scoreboard or Scoreboard(bundle)

    def run(self, set_name: str, *, top_k: int = 5) -> EvalRunResult:
        eval_set = EvalSetManager(self.bundle).load(set_name)
        results: list[CaseResult] = []
        for case in eval_set.cases:
            a_score = self._score_knowledge(case, top_k=top_k)
            b_score, b_answer = self._score_e2e(case, top_k=top_k)
            results.append(
                CaseResult(
                    question=case.question,
                    expected_concept=case.expected_concept,
                    a_hit=a_score >= 1.0,
                    a_score=a_score,
                    b_answer=b_answer,
                    b_score=b_score,
                )
            )

        count = len(results)
        run = EvalRunResult(
            set_name=set_name,
            knowledge_version=getattr(self.service.engines["knowledge"], "version", None),
            created_at=now_iso_us(),
            a_score=sum(r.a_score for r in results) / count if count else 0.0,
            b_score=sum(r.b_score for r in results) / count if count else 0.0,
            cases=results,
        )
        self.scoreboard.save(run)
        return run

    def _score_knowledge(self, case: EvalCase, *, top_k: int) -> float:
        """A score: expected concept exists, is verified/stable, and is retrieved."""
        if not case.expected_concept:
            return 0.0
        try:
            concept = self.bundle.read_concept(case.expected_concept)
        except FileNotFoundError:
            return 0.0
        if not concept.is_verified_stable():
            return 0.0
        hits = self.service.search(case.question, kind="knowledge", top_k=top_k).hits
        return 1.0 if any(hit.concept_id == case.expected_concept for hit in hits) else 0.0

    def _score_e2e(self, case: EvalCase, *, top_k: int) -> tuple[float, str]:
        """B score: full question->retrieve->generate->answer compared to reference."""
        answer = self.service.answer(case.question, answerer=self.answerer, top_k=top_k)
        return similarity(answer, case.reference_answer), answer
