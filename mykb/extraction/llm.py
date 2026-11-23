"""LLM client abstraction for drafting business knowledge.

The default client is a deterministic offline implementation so the pipeline is
testable without credentials. Configure a real OpenAI-compatible endpoint via the
``MYKB_LLM_BASE_URL`` / ``MYKB_LLM_API_KEY`` / ``MYKB_LLM_MODEL`` environment
variables.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

import httpx


class LLMError(RuntimeError):
    """Raised when an LLM call fails or returns a malformed response."""


class LLMClient(Protocol):
    model: str

    def draft(self, *, instructions: str, sources: list[tuple[str, str]]) -> str:
        """Return markdown business-knowledge text synthesized from sources."""

    def extract(
        self, *, instructions: str, sources: list[tuple[str, str]]
    ) -> dict[str, Any]:
        """Return a structured extraction result synthesized from sources."""


class FakeLLM:
    """Deterministic, offline LLM used for tests and local development."""

    model = "fake-llm"

    def draft(self, *, instructions: str, sources: list[tuple[str, str]]) -> str:
        lines = ["# 业务知识（草稿）", ""]
        for source_id, body in sources:
            snippet = body.strip().splitlines()[0] if body.strip() else ""
            lines.append(f"- 来源 `{source_id}`：{snippet}")
        return "\n".join(lines) + "\n"

    def extract(
        self, *, instructions: str, sources: list[tuple[str, str]]
    ) -> dict[str, Any]:
        claims: list[dict[str, Any]] = []
        title = "业务知识（草稿）"
        summary = ""
        for source_id, body in sources:
            lines = [line.strip() for line in body.splitlines() if line.strip()]
            if not lines:
                continue
            heading = next((line.lstrip("# ").strip() for line in lines if line.startswith("#")), "")
            if heading and title == "业务知识（草稿）":
                title = heading
            snippet = next((line for line in lines if not line.startswith("#")), lines[0])
            if not summary:
                summary = snippet
            claims.append({"text": snippet, "sources": [source_id]})
        if not claims:
            claims = [{"text": "源数据暂无可用内容", "sources": [sid for sid, _ in sources]}]
        return {
            "title": title,
            "summary": summary,
            "tags": ["source"],
            "claims": claims,
            "conflicts": [],
            "open_questions": [],
        }


class OpenAICompatibleLLM:
    """Minimal client for OpenAI-compatible chat-completions endpoints."""

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: float = 60.0) -> None:
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def draft(self, *, instructions: str, sources: list[tuple[str, str]]) -> str:
        source_text = "\n\n".join(f"[{sid}]\n{body}" for sid, body in sources)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": f"源数据：\n{source_text}"},
            ],
        }
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        try:
            return str(response.json()["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("malformed LLM completion response") from exc

    def extract(
        self, *, instructions: str, sources: list[tuple[str, str]]
    ) -> dict[str, Any]:
        source_text = "\n\n".join(f"[{sid}]\n{body}" for sid, body in sources)
        schema_hint = (
            "只输出 JSON 对象，字段：title(string)、summary(string)、tags(string[])、"
            "claims(array of {text: string, sources: string[]})、conflicts(array)、"
            "open_questions(string[])。每条 claim 的 sources 必须引用给定的来源 id，不要臆造。"
        )
        payload = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": f"{instructions}\n{schema_hint}"},
                {"role": "user", "content": f"源数据：\n{source_text}"},
            ],
        }
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        try:
            content = str(response.json()["choices"][0]["message"]["content"])
            return json.loads(_strip_code_fence(content))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMError("malformed LLM extraction response") from exc


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        stripped = stripped.removesuffix("```")
    return stripped.strip()


def get_default_llm() -> LLMClient:
    """Return a real client when configured, else the deterministic FakeLLM."""
    base_url = os.environ.get("MYKB_LLM_BASE_URL")
    api_key = os.environ.get("MYKB_LLM_API_KEY")
    model = os.environ.get("MYKB_LLM_MODEL", "gpt-4o-mini")
    if base_url and api_key:
        return OpenAICompatibleLLM(base_url=base_url, api_key=api_key, model=model)
    return FakeLLM()
