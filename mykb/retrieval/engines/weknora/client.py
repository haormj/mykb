"""Thin HTTP client for a self-hosted WeKnora instance (v0.9 API)."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

import httpx


class WeKnoraError(RuntimeError):
    """A WeKnora request failed."""


class WeKnoraUnavailable(WeKnoraError):
    """WeKnora could not be reached or returned a server error."""


class WeKnoraClient:
    """Minimal client covering knowledge-base lifecycle, ingest and retrieval."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        tenant_id: str | None = None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._tenant_id = tenant_id
        self._client = client or httpx.Client(timeout=timeout)
        self.max_retries = max(0, max_retries)
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep or time.sleep

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        if self._tenant_id:
            headers["X-Tenant-ID"] = self._tenant_id
        return headers

    def _checked(self, response: httpx.Response):
        if response.status_code >= 400:
            raise WeKnoraError(
                f"weknora HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise WeKnoraError("weknora returned non-JSON response") from exc
        if isinstance(payload, dict):
            if payload.get("success") is False:
                raise WeKnoraError(str(payload.get("error") or payload))
            if "data" in payload:
                return payload["data"]
        return payload

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self._base_url}{path}"
        last: Exception = WeKnoraUnavailable("weknora request failed")
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.request(
                    method, url, headers=self._headers(), **kwargs
                )
            except httpx.TransportError as exc:
                last = WeKnoraUnavailable(f"weknora unreachable: {exc}")
            else:
                if response.status_code < 500:
                    return self._checked(response)
                last = WeKnoraUnavailable(f"weknora HTTP {response.status_code}")
            if attempt < self.max_retries:
                self._sleep(self.backoff_seconds * (attempt + 1))
        raise last

    def health(self) -> bool:
        try:
            response = self._client.get(
                f"{self._base_url}/health", headers=self._headers()
            )
        except httpx.TransportError:
            return False
        if response.status_code != 200:
            return False
        try:
            return response.json().get("status") == "ok"
        except ValueError:
            return False

    def create_knowledge_base(
        self,
        name: str,
        *,
        description: str | None = None,
        embedding_model_id: str | None = None,
        kb_type: str = "document",
    ) -> dict:
        body: dict = {"name": name, "type": kb_type}
        if description:
            body["description"] = description
        if embedding_model_id:
            body["embedding_model_id"] = embedding_model_id
        return self._request("POST", "/api/v1/knowledge-bases", json=body)

    def delete_knowledge_base(self, kb_id: str) -> None:
        self._request("DELETE", f"/api/v1/knowledge-bases/{kb_id}")

    def add_manual_knowledge(
        self, kb_id: str, *, title: str, content: str, status: str = "publish"
    ) -> str:
        data = self._request(
            "POST",
            f"/api/v1/knowledge-bases/{kb_id}/knowledge/manual",
            json={"title": title, "content": content, "status": status},
        )
        return str(data["id"])

    def list_knowledge(
        self,
        kb_id: str,
        *,
        parse_status: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> list[dict]:
        params: dict = {"page": page, "page_size": page_size}
        if parse_status:
            params["parse_status"] = parse_status
        data = self._request(
            "GET", f"/api/v1/knowledge-bases/{kb_id}/knowledge", params=params
        )
        return list(data or [])

    def list_all_knowledge(self, kb_id: str, *, page_size: int = 100) -> list[dict]:
        rows: list[dict] = []
        page = 1
        while True:
            batch = self.list_knowledge(kb_id, page=page, page_size=page_size)
            rows.extend(batch)
            if len(batch) < page_size:
                break
            page += 1
        return rows

    def knowledge_search(
        self,
        *,
        query: str,
        knowledge_base_ids: Sequence[str],
        match_count: int = 10,
    ) -> list[dict]:
        data = self._request(
            "POST",
            "/api/v1/knowledge-search",
            json={
                "query": query,
                "knowledge_base_ids": list(knowledge_base_ids),
                "match_count": match_count,
            },
        )
        return list(data or [])

    def close(self) -> None:
        self._client.close()
