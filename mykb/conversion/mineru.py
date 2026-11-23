"""HTTP provider for the internal document conversion sidecar.

The sidecar exposes a small normalized contract (a thin adapter may sit in front
of MinerU):

``POST <MYKB_PARSER_URL>`` (multipart)
  - ``file``: the raw document
  - ``tier``: parsing tier

Response JSON::

  {
    "markdown": "...",
    "title": "optional",
    "parser_version": "4.2.0",
    "warnings": ["..."],
    "assets": [{"name": "img-1.png", "content_base64": "..."}]
  }

Markdown image links refer to assets by their ``name``; the ingest pipeline rewrites
them to the bundle's ``.assets/`` paths.
"""

from __future__ import annotations

import base64
import binascii

import httpx

from .base import (
    Asset,
    ConversionAuthError,
    ConversionError,
    ConversionNotConfiguredError,
    ConversionResult,
    ConversionUnavailableError,
    RawDocument,
)

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class MineruHttpConverter:
    """Convert docx via an internal MinerU-backed sidecar."""

    name = "mineru"

    def __init__(
        self,
        base_url: str | None,
        *,
        timeout: float = 60.0,
        tier: str = "flash",
        token: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout = timeout
        self.tier = tier
        self.token = token
        self._client = client

    def supports(self, suffix: str, mime: str) -> bool:
        return suffix.lower() == ".docx" or mime == DOCX_MIME

    def convert(self, document: RawDocument) -> ConversionResult:
        if not self.base_url:
            raise ConversionNotConfiguredError(
                "conversion service is not configured; set MYKB_PARSER_URL to import .docx"
            )
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(
                self.base_url,
                files={"file": (document.name, document.data, document.mime)},
                data={"tier": self.tier},
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise ConversionUnavailableError("conversion service timed out") from exc
        except httpx.HTTPError as exc:
            raise ConversionUnavailableError(f"conversion service unavailable: {exc}") from exc
        finally:
            if self._client is None:
                client.close()

        if response.status_code in (401, 403):
            raise ConversionAuthError("conversion service rejected credentials")
        if response.status_code >= 500:
            raise ConversionUnavailableError(
                f"conversion service error: {response.status_code}"
            )
        if response.status_code >= 400:
            raise ConversionError(
                f"conversion failed ({response.status_code}): {response.text[:200]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ConversionUnavailableError(
                "conversion service returned invalid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise ConversionUnavailableError("conversion service returned invalid payload")
        markdown = payload.get("markdown")
        if not isinstance(markdown, str):
            raise ConversionUnavailableError("conversion service response is missing markdown")

        assets: list[Asset] = []
        for item in payload.get("assets") or []:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            encoded = item.get("content_base64")
            if not isinstance(name, str) or not isinstance(encoded, str):
                raise ConversionError("conversion service returned an invalid asset")
            try:
                data = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ConversionError("conversion service returned invalid asset data") from exc
            source_name = item.get("source_name")
            assets.append(
                Asset(
                    name=name,
                    data=data,
                    source_name=str(source_name) if isinstance(source_name, str) else name,
                )
            )

        version = payload.get("parser_version") or payload.get("version")
        producer = f"mineru@{version}" if isinstance(version, str) and version else "mineru"
        warnings = payload.get("warnings")
        title = payload.get("title")
        return ConversionResult(
            markdown=markdown,
            title=str(title) if isinstance(title, str) else None,
            assets=assets,
            producer=producer,
            warnings=[str(w) for w in warnings] if isinstance(warnings, list) else [],
        )
