"""Evaluation runner producing knowledge-quality (A) and end-to-end (B) scores.

The runner is pure scoring: it receives plain case data plus a knowledge-base
bundle and retrieval service, and never touches the database or any bundle's
eval storage. Persistence lives in :mod:`mykb.evaluation.store`.
"""

from __future__ import annotations

from ..okf.bundle import Bundle
from ..retrieval.engines.markdown_rag import tokens
from ..retrieval.interface import Answerer, RetrievalService
from .types import COVERAGE_STATUSES, CaseData, CaseResult, EvalResult


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


class EvalRunner:
    """Runs eval cases against a single knowledge base via the retrieval interface."""

    def __init__(
        self,
        bundle: Bundle,
        service: RetrievalService,
        *,
        answerer: Answerer | None = None,
    ) -> None:
        self.bundle = bundle
        self.service = service
        self.answerer = answerer

    def run(self, cases: list[CaseData], *, top_k: int = 5) -> EvalResult:
        results: list[CaseResult] = []
        for case in cases:
            status, a_score = self._score_knowledge(case, top_k=top_k)
            b_score, b_answer = self._score_e2e(case, top_k=top_k)
            results.append(
                CaseResult(
                    question=case.question,
                    expected_concept=case.expected_concept,
                    status=status,
                    a_score=a_score,
                    b_answer=b_answer,
                    b_score=b_score,
                    case_id=case.case_id,
                )
            )

        with_expected = [r for r in results if r.status != "b_only"]
        denominator = len(with_expected)
        a_score = (
            sum(r.a_score for r in with_expected) / denominator if denominator else 0.0
        )
        coverage = (
            sum(1 for r in with_expected if r.status in COVERAGE_STATUSES) / denominator
            if denominator
            else 0.0
        )
        b_score = sum(r.b_score for r in results) / len(results) if results else 0.0

        return EvalResult(
            a_score=a_score,
            b_score=b_score,
            coverage=coverage,
            case_count=len(results),
            knowledge_version=getattr(self.service.engines["knowledge"], "version", None),
            cases=results,
        )

    def _score_knowledge(self, case: CaseData, *, top_k: int) -> tuple[str, float]:
        """Classify missing -> unverified -> not_retrieved -> hit (or b_only)."""
        if not case.expected_concept:
            return "b_only", 0.0
        try:
            concept = self.bundle.read_concept(case.expected_concept)
        except FileNotFoundError:
            return "missing", 0.0
        if not concept.is_verified_stable():
            return "unverified", 0.0
        hits = self.service.search(case.question, kind="knowledge", top_k=top_k).hits
        if any(hit.concept_id == case.expected_concept for hit in hits):
            return "hit", 1.0
        return "not_retrieved", 0.0

    def _score_e2e(self, case: CaseData, *, top_k: int) -> tuple[float, str]:
        """B score: full question->retrieve->generate->answer compared to reference."""
        answer = self.service.answer(case.question, answerer=self.answerer, top_k=top_k)
        return similarity(answer, case.reference_answer), answer
