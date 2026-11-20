"""Eval-set management, stored as OKF concepts under the ``evals`` level.

An eval set is a single ``type: 评测集`` concept whose ``cases`` frontmatter list
holds the questions, reference answers, expected concept ids and metadata.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..okf.bundle import Bundle
from ..okf.model import Concept
from ..util import now_iso


@dataclass
class EvalCase:
    question: str
    reference_answer: str
    expected_concept: str | None = None
    domain: str | None = None
    difficulty: str | None = None

    def to_dict(self) -> dict:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass
class EvalSet:
    name: str
    cases: list[EvalCase]
    concept: Concept


def _case_from_dict(data: dict) -> EvalCase:
    return EvalCase(
        question=str(data.get("question", "")),
        reference_answer=str(data.get("reference_answer", "")),
        expected_concept=data.get("expected_concept"),
        domain=data.get("domain"),
        difficulty=data.get("difficulty"),
    )


class EvalSetManager:
    """Create, load and list eval sets in the bundle's ``evals`` level."""

    def __init__(self, bundle: Bundle) -> None:
        self.bundle = bundle

    def create(
        self,
        name: str,
        cases: list[EvalCase],
        *,
        title: str | None = None,
        author: str = "human:owner",
    ) -> str:
        frontmatter: dict = {
            "type": "评测集",
            "title": title or name,
            "cases": [case.to_dict() for case in cases],
            "generated": {"by": author, "at": now_iso()},
            "status": "stable",
        }
        concept = Concept(frontmatter=frontmatter, body=f"# {title or name}\n")
        return self.bundle.write_concept(concept, "evals", name)

    def _concept_id(self, name: str) -> str:
        return name if name.startswith("evals/") else f"evals/{name}"

    def load(self, name: str) -> EvalSet:
        concept = self.bundle.read_concept(self._concept_id(name))
        raw_cases = concept.frontmatter.get("cases") or []
        cases = [_case_from_dict(item) for item in raw_cases if isinstance(item, dict)]
        return EvalSet(name=name, cases=cases, concept=concept)

    def list(self) -> list[str]:
        names: list[str] = []
        for concept_id, concept in self.bundle.iter_concepts("evals"):
            if concept.type == "评测集":
                names.append(concept_id.split("/", 1)[1])
        return sorted(names)
