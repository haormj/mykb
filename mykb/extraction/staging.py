"""Filesystem staging for documents awaiting extraction review.

Staged content lives outside the git repos (under ``settings.pending_root``) so
it never shows up in ``git status`` or gets swept into a bundle commit.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..config import Settings
from ..conversion.base import Asset
from ..okf.bundle import Bundle
from ..okf.model import Concept


def pending_dir(settings: Settings, item_id: str) -> Path:
    return settings.pending_root / item_id


def staged_path(settings: Settings, item_id: str) -> Path:
    return pending_dir(settings, item_id) / "concept.md"


def stage_concept(
    settings: Settings,
    item_id: str,
    concept: Concept,
    assets: list[Asset],
) -> None:
    directory = pending_dir(settings, item_id)
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True, exist_ok=True)
    concept.to_file(directory / "concept.md")
    if assets:
        asset_dir = directory / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        for asset in assets:
            (asset_dir / asset.name).write_bytes(asset.data)


def load_staged(settings: Settings, item_id: str) -> tuple[Concept, list[Asset]]:
    directory = pending_dir(settings, item_id)
    path = directory / "concept.md"
    if not path.exists():
        raise FileNotFoundError(f"staged concept missing for item {item_id}")
    concept = Concept.from_file(path)
    asset_dir = directory / "assets"
    assets: list[Asset] = []
    if asset_dir.is_dir():
        for asset_path in sorted(asset_dir.iterdir()):
            if asset_path.is_file():
                assets.append(Asset(name=asset_path.name, data=asset_path.read_bytes()))
    return concept, assets


def staged_concept(settings: Settings, item_id: str) -> Concept | None:
    path = staged_path(settings, item_id)
    if not path.exists():
        return None
    return Concept.from_file(path)


def cleanup_staged(settings: Settings, item_id: str) -> None:
    shutil.rmtree(pending_dir(settings, item_id), ignore_errors=True)


def write_raw_concept(
    bundle: Bundle, *, concept_id: str, concept: Concept, assets: list[Asset]
) -> None:
    """Place a raw concept (and its derived assets) at ``concept_id``."""
    tail = concept_id.split("/", 1)[1] if "/" in concept_id else concept_id
    if assets:
        bundle.write_assets("raw", tail, assets)
    bundle.write_concept(concept, "raw", tail)
