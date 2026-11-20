"""Markdown RAG engines: a local reference engine and a WeKnora HTTP adapter."""

from __future__ import annotations

import re

import httpx

from ...okf.model import Concept
from ..interface import RetrievalHit

_ASCII = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    """Tokenize text for a lightweight lexical match (ASCII words + CJK chars)."""
    lowered = text.lower()
    result = _ASCII.findall(lowered)
    result.extend(ch for ch in lowered if "\u4e00" <= ch <= "\u9fff")
    return result


def _snippet(body: str, limit: int = 200) -> str:
    text = body.strip().replace("\n", " ")
    return text[:limit]


class LocalMarkdownRAG:
    """In-process markdown RAG engine used as the offline default."""

    name = "local-markdown-rag"

    def __init__(self) -> None:
        self.version: str | None = None
        self._docs: list[tuple[str, str, str]] = []

    def index(self, concepts: list[Concept], *, version: str | None = None) -> None:
        self._docs = [(c.id or "", c.title or "", c.body) for c in concepts]
        self.version = version

    def search(self, query: str, *, top_k: int = 5) -> list[RetrievalHit]:
        query_tokens = set(tokens(query))
        if not query_tokens:
            return []
        hits: list[RetrievalHit] = []
        for concept_id, title, body in self._docs:
            doc_tokens = set(tokens(f"{title}\n{body}"))
            overlap = len(query_tokens & doc_tokens)
            if overlap == 0:
                continue
            hits.append(
                RetrievalHit(
                    concept_id=concept_id,
                    title=title,
                    snippet=_snippet(body),
                    score=overlap / len(query_tokens),
                    engine=self.name,
                )
            )
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]


class WeKnoraAdapter:
    """HTTPS adapter to a WeKnora-style markdown RAG gateway.

    The gateway contract assumed here (adjust to your WeKnora deployment):

    * ``POST {base_url}/index``   -> ``{"documents": [...], "version": "..."}``
    * ``POST {base_url}/search``  -> ``{"hits": [{"id","title","snippet","score"}]}``
    """

    name = "weknora"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.version: str | None = None
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=timeout)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

    def index(self, concepts: list[Concept], *, version: str | None = None) -> None:
        documents = [
            {"id": c.id, "title": c.title, "content": c.body} for c in concepts if c.id
        ]
        response = self._client.post(
            f"{self._base_url}/index",
            json={"documents": documents, "version": version},
            headers=self._headers(),
        )
        response.raise_for_status()
        self.version = version

    def search(self, query: str, *, top_k: int = 5) -> list[RetrievalHit]:
        response = self._client.post(
            f"{self._base_url}/search",
            json={"query": query, "top_k": top_k},
            headers=self._headers(),
        )
        response.raise_for_status()
        data = response.json()
        return [
            RetrievalHit(
                concept_id=str(item.get("id", "")),
                title=str(item.get("title", "")),
                snippet=str(item.get("snippet", "")),
                score=float(item.get("score", 0.0)),
                engine=self.name,
            )
            for item in data.get("hits", [])
        ]
