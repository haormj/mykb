"""OKF bundle layout and IO.

A bundle is a directory tree of markdown files. This module owns the platform's
three-level layout (``raw`` / ``knowledge`` / ``evals``), the bundle-root
``index.md`` metadata, and the read/write helpers used across the platform.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .model import Concept, FrontmatterError, parse, serialize

RESERVED_FILENAMES = {"index.md", "log.md"}
LEVELS: tuple[str, ...] = ("raw", "knowledge", "evals")
DEFAULT_OKF_VERSION = "0.3"


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
            raise ValueError("concept has no id; use write_concept to place a new concept")
        concept.to_file(self.path_for_id(concept.id))
        return concept.id

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
