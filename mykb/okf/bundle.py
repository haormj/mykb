"""OKF bundle layout and IO.

A bundle is a directory tree of markdown files. This module owns the platform's
two-level knowledge layout (``raw`` / ``knowledge``), the bundle-root
``index.md`` metadata, and the read/write helpers used across the platform.
Evaluation data is platform metadata and is never stored in a bundle.
"""

from __future__ import annotations

import mimetypes
import shutil
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .model import Concept, FrontmatterError, parse, serialize

RESERVED_FILENAMES = {"index.md", "log.md"}
LEVELS: tuple[str, ...] = ("raw", "knowledge")
DEFAULT_OKF_VERSION = "0.3"


class AssetLike(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def data(self) -> bytes: ...


@dataclass
class Bundle:
    """A git-backed OKF bundle rooted at ``root``."""

    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)

    # -- layout -----------------------------------------------------------
    def level_dir(self, level: str) -> Path:
        if level not in LEVELS:
            raise ValueError(f"unknown level '{level}', expected one of {LEVELS}")
        return self.root / level

    def ensure_layout(
        self,
        *,
        okf_version: str = DEFAULT_OKF_VERSION,
        title: str | None = None,
        description: str | None = None,
        version: str = "0.1.0",
    ) -> None:
        """Create the three-level layout and the bundle-root index if missing."""
        self.root.mkdir(parents=True, exist_ok=True)
        for level in LEVELS:
            directory = self.level_dir(level)
            directory.mkdir(parents=True, exist_ok=True)
            index = directory / "index.md"
            if not index.exists():
                index.write_text(f"# {level}\n", encoding="utf-8")
        self._ensure_root_index(
            okf_version=okf_version, title=title, description=description, version=version
        )

    def _ensure_root_index(
        self,
        *,
        okf_version: str,
        title: str | None,
        description: str | None,
        version: str,
    ) -> None:
        index = self.root / "index.md"
        if index.exists():
            return
        frontmatter: dict[str, object] = {
            "okf_version": okf_version,
            "title": title or "Knowledge Bundle",
        }
        if description:
            frontmatter["description"] = description
        frontmatter["version"] = version
        index.write_text(serialize(frontmatter, "# Knowledge Bundle\n"), encoding="utf-8")

    def root_index(self) -> tuple[dict, str]:
        """Return ``(frontmatter, body)`` of the bundle-root index.md."""
        index = self.root / "index.md"
        if not index.exists():
            return {}, ""
        return parse(index.read_text(encoding="utf-8"))

    # -- concept ids ------------------------------------------------------
    @staticmethod
    def concept_id(relative_path: str) -> str:
        rel = relative_path.replace("\\", "/").lstrip("/")
        return rel.removesuffix(".md")

    def path_for_id(self, concept_id: str) -> Path:
        cid = concept_id.lstrip("/")
        cid = cid.removesuffix(".md")
        return self.root / f"{cid}.md"

    # -- io ---------------------------------------------------------------
    def read_concept(self, concept_id: str) -> Concept:
        path = self.path_for_id(concept_id)
        return Concept.from_file(path, id=self.concept_id(concept_id))

    def write_concept(self, concept: Concept, level: str, relative_path: str) -> str:
        """Write ``concept`` under ``level`` and return its concept id."""
        tail = relative_path.replace("\\", "/").lstrip("/")
        if not tail.endswith(".md"):
            tail += ".md"
        cid = self.concept_id(f"{level}/{tail}")
        concept.id = cid
        concept.to_file(self.root / f"{cid}.md")
        return cid

    def save_concept(self, concept: Concept) -> str:
        """Persist an existing concept back to the path named by its id."""
        if not concept.id:
            raise ValueError("concept has no id; use write_concept to place a new one")
        concept.to_file(self.path_for_id(concept.id))
        return concept.id

    # -- derived assets ---------------------------------------------------
    def asset_dir_for(self, level: str, relative_concept_path: str) -> Path:
        """Return the sibling ``<concept>.assets`` directory for a concept."""
        tail = relative_concept_path.replace("\\", "/").lstrip("/")
        tail = tail.removesuffix(".md")
        directory = self.level_dir(level) / f"{tail}.assets"
        resolved = directory.resolve()
        root = self.root.resolve()
        if root not in resolved.parents and resolved != root:
            raise ValueError("asset directory escapes the bundle root")
        return directory

    def write_assets(
        self, level: str, relative_concept_path: str, assets: Iterable[AssetLike]
    ) -> list[str]:
        """Write prepared assets and return links relative to the concept file."""
        directory = self.asset_dir_for(level, relative_concept_path)
        alias = Path(relative_concept_path).stem
        directory.mkdir(parents=True, exist_ok=True)
        links: list[str] = []
        for asset in assets:
            name = asset.name
            data = asset.data
            if name in ("", ".", "..") or Path(name).name != name or "\\" in name:
                raise ValueError(f"unsafe asset name: {name!r}")
            (directory / name).write_bytes(data)
            links.append(f"{alias}.assets/{name}")
        return links

    def remove_assets(self, level: str, relative_concept_path: str) -> None:
        """Delete a concept's asset directory if it exists."""
        shutil.rmtree(self.asset_dir_for(level, relative_concept_path), ignore_errors=True)

    def split_concept_id(self, concept_id: str) -> tuple[str, str]:
        """Split a concept id into ``(level, path-relative-to-level)``."""
        cid = concept_id.lstrip("/").removesuffix(".md")
        level, sep, tail = cid.partition("/")
        if not sep or level not in LEVELS or not tail:
            raise ValueError(f"concept id must live under one of {LEVELS}: {concept_id!r}")
        return level, tail

    def read_asset(self, concept_id: str, name: str) -> tuple[bytes, str]:
        """Read one asset from a concept's sibling ``.assets/`` directory.

        Returns ``(data, mime_type)``. Raises ``ValueError`` for an unsafe or
        escaping name, and ``FileNotFoundError`` when the asset is missing or is
        an un-smudged Git LFS pointer.
        """
        if (
            not name
            or name in (".", "..")
            or "/" in name
            or "\\" in name
            or Path(name).name != name
        ):
            raise ValueError(f"unsafe asset name: {name!r}")
        level, tail = self.split_concept_id(concept_id)
        directory = self.asset_dir_for(level, tail)
        try:
            resolved_dir = directory.resolve(strict=True)
        except OSError as exc:
            raise FileNotFoundError(name) from exc
        target = (directory / name).resolve()
        if target.parent != resolved_dir or not target.is_file():
            raise FileNotFoundError(name)
        data = target.read_bytes()
        if data.startswith(b"version https://git-lfs"):
            raise FileNotFoundError(name)
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        return data, mime

    def asset_bytes(self) -> int:
        """Total bytes of derived asset files in this bundle."""
        total = 0
        for path in self.root.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            if any(part.endswith(".assets") for part in path.parts):
                try:
                    total += path.stat().st_size
                except OSError:
                    continue
        return total


    def iter_concepts(self, level: str | None = None) -> Iterator[tuple[str, Concept]]:
        """Yield ``(concept_id, concept)`` for every non-reserved markdown file."""
        levels = (level,) if level else LEVELS
        for lvl in levels:
            directory = self.level_dir(lvl)
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("*.md")):
                if path.name in RESERVED_FILENAMES:
                    continue
                try:
                    concept = Concept.from_file(path)
                except (FrontmatterError, OSError):
                    continue
                cid = self.concept_id(path.relative_to(self.root).as_posix())
                concept.id = cid
                yield cid, concept

    def all_concept_ids(self) -> list[str]:
        return [cid for cid, _ in self.iter_concepts()]
