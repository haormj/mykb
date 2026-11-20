"""Draft business knowledge from source concepts using an LLM."""

from __future__ import annotations

from ..okf.bundle import Bundle
from ..okf.model import Concept
from ..util import now_iso
from .lineage import build_source_entries
from .llm import LLMClient, get_default_llm

DRAFT_INSTRUCTIONS = (
    "你是企业知识管理平台的知识工程师。请阅读给定的源数据，加工融合成一条"
    "结构化、可复用的业务知识。使用 markdown，包含标题、要点与必要的引用。"
    "只依据源数据陈述事实，不要臆造。"
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
