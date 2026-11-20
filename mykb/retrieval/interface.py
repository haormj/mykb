"""Unified retrieval interface.

External consumers talk to :class:`RetrievalService`, which routes a request to
one of several interchangeable engines (markdown RAG, code graph, ...). The engine
is an internal implementation detail; the response shape and behaviour are stable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from ..okf.model import Concept


@dataclass
class RetrievalHit:
    concept_id: str
    title: str
    snippet: str
    score: float
    engine: str


@dataclass
class RetrievalResponse:
    query: str
    kind: str
    engine: str
    hits: list[RetrievalHit] = field(default_factory=list)
    knowledge_version: str | None = None


class RetrievalEngine(Protocol):
    """An interchangeable retrieval backend."""

    name: str
    version: str | None

    def index(self, concepts: list[Concept], *, version: str | None = None) -> None: ...

    def search(self, query: str, *, top_k: int = 5) -> list[RetrievalHit]: ...


Answerer = Callable[[str, list[RetrievalHit]], str]


class RetrievalService:
    """Stable facade over one knowledge engine and an optional code engine."""

    def __init__(
        self,
        *,
        knowledge_engine: RetrievalEngine,
        code_engine: RetrievalEngine | None = None,
    ) -> None:
        self.engines: dict[str, RetrievalEngine] = {"knowledge": knowledge_engine}
        if code_engine is not None:
            self.engines["code"] = code_engine

    def search(self, query: str, *, kind: str = "knowledge", top_k: int = 5) -> RetrievalResponse:
        try:
            engine = self.engines[kind]
        except KeyError as exc:
            raise KeyError(f"no engine for kind '{kind}', available: {list(self.engines)}") from exc
        hits = engine.search(query, top_k=top_k)
        return RetrievalResponse(
            query=query,
            kind=kind,
            engine=engine.name,
            hits=hits,
            knowledge_version=getattr(engine, "version", None),
        )

    def answer(self, query: str, *, answerer: Answerer | None = None, top_k: int = 5) -> str:
        """End-to-end answer: retrieve knowledge, then generate a response."""
        hits = self.search(query, kind="knowledge", top_k=top_k).hits
        if answerer is not None:
            return answerer(query, hits)
        return hits[0].snippet if hits else ""
