"""Periodic page-level health check for business knowledge.

Per-document review only sees a delta; this audit looks at each accumulated page
as a whole and flags schema problems, duplicate entities, broken links and
declared conflicts, marking the affected pages ``needs-review``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..extraction.harness import claims_of, validate_concept
from ..okf.bundle import Bundle
from .lifecycle import mark_needs_review


@dataclass
class KnowledgeIssue:
    concept_id: str
    reason: str

    def __str__(self) -> str:
        return f"{self.concept_id}: {self.reason}"


def audit_knowledge(bundle: Bundle) -> list[KnowledgeIssue]:
    """Return health issues for every business-knowledge page."""
    issues: list[KnowledgeIssue] = []
    for concept_id, concept in bundle.iter_concepts("knowledge"):
        for problem in validate_concept(concept, bundle, target_id=concept_id):
            issues.append(KnowledgeIssue(concept_id, problem))
        claim_texts = [claim["text"] for claim in claims_of(concept)]
        duplicates = [
            text for text, count in Counter(claim_texts).items() if count > 1
        ]
        for text in duplicates:
            issues.append(KnowledgeIssue(concept_id, f"duplicate claim: {text[:40]!r}"))
        if concept.frontmatter.get("x-conflicts"):
            issues.append(KnowledgeIssue(concept_id, "declared conflicts need resolution"))
    return issues


def run_audit(bundle: Bundle) -> list[KnowledgeIssue]:
    """Audit the bundle and mark every affected page ``needs-review``."""
    issues = audit_knowledge(bundle)
    affected = sorted({issue.concept_id for issue in issues})
    if affected:
        mark_needs_review(bundle, affected, reason="page audit")
    return issues
