"""Code-aware retrieval engine (codegraph).

Indexes read-only code source concepts (``type: 代码``) and answers symbol /
function oriented queries. A local in-process implementation is provided; a remote
codegraph service can be substituted behind the same engine interface.
"""

from __future__ import annotations

from ...okf.model import Concept
from ..interface import RetrievalHit
from .markdown_rag import tokens


class LocalCodeGraph:
    """In-process symbol index built from code-source concepts."""

    name = "local-codegraph"

    def __init__(self) -> None:
        self.version: str | None = None
        self._symbols: list[tuple[str, str, str]] = []

    def index(self, concepts: list[Concept], *, version: str | None = None) -> None:
        self._symbols = [
            (c.id or "", c.title or "", c.resource or "") for c in concepts if c.id
        ]
        self.version = version

    def search(self, query: str, *, top_k: int = 5) -> list[RetrievalHit]:
        query_tokens = set(tokens(query))
        if not query_tokens:
            return []
        hits: list[RetrievalHit] = []
        for concept_id, title, resource in self._symbols:
            haystack = set(tokens(f"{title} {resource}"))
            overlap = len(query_tokens & haystack)
            if overlap == 0:
                continue
            hits.append(
                RetrievalHit(
                    concept_id=concept_id,
                    title=title or resource,
                    snippet=f"代码符号: {title} ({resource})",
                    score=overlap / len(query_tokens),
                    engine=self.name,
                )
            )
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]
