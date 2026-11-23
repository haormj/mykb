"""Conversion service: routing, per-document limits, caching and concurrency."""

from __future__ import annotations

import base64
import binascii
import json
import threading
from pathlib import Path

from ..config import Settings
from ..okf.bundle import Bundle
from .assets import prepare_assets
from .base import (
    Asset,
    ConversionLimitError,
    ConversionResult,
    DocumentConverter,
    RawDocument,
)
from .registry import build_default_converters, select_converter

PASSTHROUGH = "passthrough"


class ConverterService:
    """Selects a provider, enforces limits and caches expensive conversions."""

    def __init__(
        self,
        settings: Settings,
        *,
        converters: list[DocumentConverter] | None = None,
    ) -> None:
        self.settings = settings
        self.converters = (
            converters if converters is not None else build_default_converters(settings)
        )
        self._semaphore = threading.Semaphore(max(1, settings.parser_concurrency))

    def convert(self, document: RawDocument) -> ConversionResult:
        converter = select_converter(self.converters, document.suffix, document.mime)
        if converter.name == PASSTHROUGH:
            return converter.convert(document)

        digest = document.sha256()
        cached = self._read_cache(digest)
        if cached is not None:
            return cached

        with self._semaphore:
            result = converter.convert(document)
        result = self._validate(result)
        self._write_cache(digest, result)
        return result

    def _validate(self, result: ConversionResult) -> ConversionResult:
        if len(result.markdown.encode("utf-8")) > self.settings.conversion_max_markdown_bytes:
            raise ConversionLimitError("converted markdown exceeds the configured size limit")
        assets, warnings = prepare_assets(
            result.assets,
            max_assets=self.settings.conversion_max_assets,
            max_asset_bytes=self.settings.conversion_max_asset_bytes,
        )
        result.assets = assets
        result.warnings = [*result.warnings, *warnings]
        return result

    def _cache_path(self, digest: str) -> Path:
        return self.settings.parse_cache_root / digest / "result.json"

    def _read_cache(self, digest: str) -> ConversionResult | None:
        path = self._cache_path(digest)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            assets = [
                Asset(
                    name=item["name"],
                    data=base64.b64decode(item["data_base64"], validate=True),
                    source_name=item.get("source_name"),
                )
                for item in payload.get("assets", [])
            ]
            return ConversionResult(
                markdown=payload["markdown"],
                title=payload.get("title"),
                assets=assets,
                frontmatter=payload.get("frontmatter") or {},
                producer=payload.get("producer") or "mineru",
                warnings=list(payload.get("warnings") or []),
            )
        except (OSError, ValueError, KeyError, TypeError, binascii.Error):
            return None

    def _write_cache(self, digest: str, result: ConversionResult) -> None:
        path = self._cache_path(digest)
        payload = {
            "markdown": result.markdown,
            "title": result.title,
            "frontmatter": result.frontmatter,
            "producer": result.producer,
            "warnings": result.warnings,
            "assets": [
                {
                    "name": asset.name,
                    "source_name": asset.source_name,
                    "data_base64": base64.b64encode(asset.data).decode("ascii"),
                }
                for asset in result.assets
            ],
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except OSError:
            return


def concept_relative_path(key: str) -> str:
    """Map a raw file key to the markdown concept path under ``raw/upload``."""
    return key if key.endswith(".md") else f"{key}.md"


def concept_alias(relative: str) -> str:
    """Return the base name used for the concept's sibling ``.assets`` directory."""
    return Path(relative).stem


def asset_quota_exceeded(bundle: Bundle, assets: list[Asset], quota: int) -> bool:
    """Return whether writing ``assets`` would exceed the knowledge-base quota."""
    current = bundle.asset_bytes()
    return current + sum(len(asset.data) for asset in assets) > quota
