"""Draft business knowledge from source concepts using an LLM."""

from __future__ import annotations

from typing import Any

from ..okf.bundle import Bundle
from ..okf.model import Concept
from ..util import now_iso
from .harness import (
    ExtractionValidationError,
    apply_concept,
    build_concept,
    normalize_output,
    sha256_text,
    stable_relative_path,
    validate_concept,
)
from .lineage import build_source_entries
from .llm import LLMClient, get_default_llm

DRAFT_INSTRUCTIONS = (
    "你是企业知识管理平台的知识工程师。请阅读给定的源数据，加工融合成一条"
    "结构化、可复用的业务知识。使用 markdown，包含标题、要点与必要的引用。"
    "只依据源数据陈述事实，不要臆造。"
)

EXTRACT_INSTRUCTIONS = (
    "你是企业知识管理平台的知识工程师。阅读给定的源数据，提炼出可复用的业务知识。"
    "每条断言（claim）必须标注它来自哪个来源 id，只依据源数据陈述事实，不要臆造。"
)


class Drafter:
    """Reads ``raw`` source concepts and produces ``knowledge`` drafts."""

    def __init__(self, bundle: Bundle, llm: LLMClient | None = None) -> None:
        self.bundle = bundle
        self.llm = llm or get_default_llm()

    def draft(self, source_ids: list[str], *, title: str | None = None) -> Concept:
        sources = [self.bundle.read_concept(sid) for sid in source_ids]
        pairs = [(sid, concept.body) for sid, concept in zip(source_ids, sources)]
        body = self.llm.draft(instructions=DRAFT_INSTRUCTIONS, sources=pairs)

        frontmatter: dict[str, object] = {
            "type": "业务知识",
            "title": title or (sources[0].title if sources else "业务知识"),
            "generated": {"by": f"ai:{self.llm.model}", "at": now_iso()},
            "status": "draft",
            "sources": build_source_entries(source_ids, sources),
        }
        code_sources = [c for c in sources if c.type == "代码" and c.resource]
        if code_sources:
            frontmatter["resource"] = code_sources[0].resource
        return Concept(frontmatter=frontmatter, body=body)

    def draft_to_bundle(
        self, source_ids: list[str], *, relative_path: str, title: str | None = None
    ) -> str:
        concept = self.draft(source_ids, title=title)
        return self.bundle.write_concept(concept, "knowledge", relative_path)

    # -- structured extraction (harness-constrained) ----------------------
    def propose_concept(
        self,
        source_ids: list[str],
        *,
        title: str | None = None,
        task_id: str | None = None,
    ) -> Concept:
        """Extract a validated-shape business knowledge concept from sources."""
        sources = [self.bundle.read_concept(sid) for sid in source_ids]
        pairs = [(sid, concept.body) for sid, concept in zip(source_ids, sources)]
        raw = self.llm.extract(instructions=EXTRACT_INSTRUCTIONS, sources=pairs)
        output = normalize_output(raw)
        source_meta: dict[str, dict[str, Any]] = {
            sid: {"resource": concept.resource, "title": concept.title}
            for sid, concept in zip(source_ids, sources)
        }
        source_hash = sha256_text("\n\n".join(body for _, body in pairs))
        return build_concept(
            output,
            source_ids=source_ids,
            source_meta=source_meta,
            model=self.llm.model,
            source_hash=source_hash,
            task_id=task_id,
            title=title,
        )

    def propose_to_bundle(
        self,
        source_ids: list[str],
        *,
        relative_path: str | None = None,
        title: str | None = None,
        task_id: str | None = None,
    ) -> tuple[str, bool]:
        """Extract, validate and write a concept; return ``(concept_id, changed)``."""
        concept = self.propose_concept(source_ids, title=title, task_id=task_id)
        target = relative_path or stable_relative_path(title or concept.title or "knowledge")
        issues = validate_concept(concept, self.bundle)
        if issues:
            raise ExtractionValidationError("; ".join(issues))
        return apply_concept(self.bundle, concept, "knowledge", target)
