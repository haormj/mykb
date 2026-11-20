"""LLM client abstraction for drafting business knowledge.

The default client is a deterministic offline implementation so the pipeline is
testable without credentials. Configure a real OpenAI-compatible endpoint via the
``MYKB_LLM_BASE_URL`` / ``MYKB_LLM_API_KEY`` / ``MYKB_LLM_MODEL`` environment
variables.
"""

from __future__ import annotations

import os
from typing import Protocol

import httpx


class LLMError(RuntimeError):
    """Raised when an LLM call fails or returns a malformed response."""


class LLMClient(Protocol):
    model: str

    def draft(self, *, instructions: str, sources: list[tuple[str, str]]) -> str:
        """Return markdown business-knowledge text synthesized from sources."""


class FakeLLM:
    """Deterministic, offline LLM used for tests and local development."""

    model = "fake-llm"

    def draft(self, *, instructions: str, sources: list[tuple[str, str]]) -> str:
        lines = ["# 业务知识（草稿）", ""]
        for source_id, body in sources:
            snippet = body.strip().splitlines()[0] if body.strip() else ""
            lines.append(f"- 来源 `{source_id}`：{snippet}")
        return "\n".join(lines) + "\n"


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


def get_default_llm() -> LLMClient:
    """Return a real client when configured, else the deterministic FakeLLM."""
    base_url = os.environ.get("MYKB_LLM_BASE_URL")
    api_key = os.environ.get("MYKB_LLM_API_KEY")
    model = os.environ.get("MYKB_LLM_MODEL", "gpt-4o-mini")
    if base_url and api_key:
        return OpenAICompatibleLLM(base_url=base_url, api_key=api_key, model=model)
    return FakeLLM()
