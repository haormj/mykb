"""OKF bundle conformance validation.

Per the OKF spec a bundle is conformant when every non-reserved ``.md`` file has
a parseable YAML frontmatter mapping with a non-empty ``type`` field.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .bundle import LEVELS, RESERVED_FILENAMES, Bundle
from .model import FrontmatterError, parse


@dataclass
class ValidationIssue:
    path: str
    reason: str

    def __str__(self) -> str:
        return f"{self.path}: {self.reason}"


def validate_bundle(root: str | Path) -> list[ValidationIssue]:
    """Return the list of conformance violations for the bundle at ``root``."""
    bundle = Bundle(Path(root))
    issues: list[ValidationIssue] = []
    for level in LEVELS:
        directory = bundle.level_dir(level)
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*.md")):
            if path.name in RESERVED_FILENAMES:
                continue
            rel = path.relative_to(bundle.root).as_posix()
            try:
                frontmatter, _ = parse(path.read_text(encoding="utf-8"))
            except FrontmatterError as exc:
                issues.append(ValidationIssue(rel, f"invalid frontmatter ({exc})"))
                continue
            concept_type = frontmatter.get("type")
            if concept_type is None or not str(concept_type).strip():
                issues.append(ValidationIssue(rel, "missing non-empty 'type' field"))
    return issues
