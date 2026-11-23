"""Asset normalization and markdown link rewriting for converted documents."""

from __future__ import annotations

import hashlib
import re

from .base import ALLOWED_ASSET_SUFFIXES, Asset, ConversionLimitError

_LINK = re.compile(r"\]\(\s*([^)\s]+)")


def prepare_assets(
    assets: list[Asset], *, max_assets: int, max_asset_bytes: int
) -> tuple[list[Asset], list[str]]:
    """Rename assets deterministically and enforce per-document limits.

    Only bitmap suffixes are kept. Names never come from the parser, so path
    traversal and unstable parser naming cannot reach the bundle.
    """
    prepared: list[Asset] = []
    warnings: list[str] = []
    total = 0
    for asset in assets:
        source = asset.source_name or asset.name
        suffix = _suffix(asset.name) or _suffix(source)
        if suffix not in ALLOWED_ASSET_SUFFIXES:
            warnings.append(f"dropped non-bitmap asset: {source}")
            continue
        digest = hashlib.sha256(asset.data).hexdigest()[:8]
        name = f"{len(prepared) + 1:03d}-{digest}{suffix}"
        total += len(asset.data)
        if total > max_asset_bytes:
            raise ConversionLimitError("converted assets exceed the configured size limit")
        prepared.append(Asset(name=name, data=asset.data, source_name=source))
        if len(prepared) > max_assets:
            raise ConversionLimitError("converted document has too many image assets")
    return prepared, warnings


def rewrite_asset_links(markdown: str, assets: list[Asset], concept_alias: str) -> str:
    """Point markdown image links at the concept's ``.assets/`` directory."""
    mapping: dict[str, str] = {}
    for asset in assets:
        target = f"{concept_alias}.assets/{asset.name}"
        mapping[asset.name] = target
        if asset.source_name:
            mapping[asset.source_name] = target

    def _replace(match: re.Match[str]) -> str:
        target = match.group(1)
        replacement = mapping.get(target)
        if replacement is None:
            return match.group(0)
        return f"]({replacement}"

    return _LINK.sub(_replace, markdown)


def _suffix(name: str) -> str:
    _, dot, ext = name.rpartition(".")
    if not dot or not ext:
        return ""
    return f".{ext.lower()}"
