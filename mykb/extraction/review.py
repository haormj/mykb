"""Git-native review of business knowledge drafts.

Flow: an AI draft is committed on a review branch (the "PR"); approval merges the
branch and then a CI step stamps ``verified`` (human) and ``status: stable``.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from ..okf.bundle import Bundle
from ..okf.model import Concept
from ..util import now_iso


class GitError(RuntimeError):
    """Raised when a git command fails."""


@dataclass
class ReviewResult:
    concept_id: str
    approved: bool
    commit: str | None = None
    branch: str | None = None


def stamp_verified(concept: Concept, *, reviewer: str, when: str | None = None) -> Concept:
    """Return a copy of ``concept`` with a human verification event and stable status."""
    frontmatter = dict(concept.frontmatter)
    frontmatter["status"] = "stable"
    events = list(frontmatter.get("verified") or [])
    events.append({"by": f"human:{reviewer}", "at": when or now_iso()})
    frontmatter["verified"] = events
    return Concept(frontmatter=frontmatter, body=concept.body, id=concept.id)


class GitReview:
    """Approves/rejects drafts using a local git repository as the review medium."""

    def __init__(
        self, bundle: Bundle, *, author_name: str = "mykb-agent", author_email: str = "agent@mykb.local"
    ) -> None:
        self.bundle = bundle
        self.author_name = author_name
        self.author_email = author_email

    # -- git plumbing -----------------------------------------------------
    def _git(self, *args: str, check: bool = True) -> str:
        command = [
            "git",
            "-C",
            str(self.bundle.root),
            "-c",
            f"user.name={self.author_name}",
            "-c",
            f"user.email={self.author_email}",
            *args,
        ]
        proc = subprocess.run(command, capture_output=True, text=True, check=False)
        if check and proc.returncode != 0:
            raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed")
        return proc.stdout.strip()

    def init(self) -> None:
        self.bundle.ensure_layout()
        if not (self.bundle.root / ".git").exists():
            self._git("init", "-b", "main")
        if not self._git("rev-parse", "--verify", "HEAD", check=False):
            layout_files = [
                name
                for name in ("index.md", "raw/index.md", "knowledge/index.md", "evals/index.md")
                if (self.bundle.root / name).exists()
            ]
            self._git("add", *layout_files)
            self._git("commit", "-m", "chore: init bundle")

    def _branch_for(self, concept_id: str) -> str:
        return "review/" + concept_id.replace("/", "-")

    def _current_branch(self) -> str:
        return self._git("rev-parse", "--abbrev-ref", "HEAD")

    def submit(self, concept_id: str, *, message: str | None = None) -> str:
        """Commit the draft on a review branch, returning the branch name."""
        self.init()
        branch = self._branch_for(concept_id)
        relative = self.bundle.path_for_id(concept_id).relative_to(self.bundle.root).as_posix()
        self._git("checkout", "-b", branch)
        self._git("add", relative)
        if self._git("status", "--porcelain", relative).strip():
            self._git("commit", "-m", message or f"draft: {concept_id}")
        return branch

    def approve_draft(self, concept_id: str, *, reviewer: str, message: str | None = None) -> ReviewResult:
        """One-shot review: branch+commit the working-tree draft, merge, then stamp."""
        self.init()
        branch = self._branch_for(concept_id)
        relative = self.bundle.path_for_id(concept_id).relative_to(self.bundle.root).as_posix()
        if self._current_branch() != "main":
            self._git("checkout", "main")
        self._git("checkout", "-B", branch)
        self._git("add", relative)
        if self._git("status", "--porcelain", relative).strip():
            self._git("commit", "-m", message or f"draft: {concept_id}")
        self._git("checkout", "main")
        self._git("merge", "--no-ff", branch, "-m", f"Merge {branch}")

        concept = self.bundle.read_concept(concept_id)
        stamped = stamp_verified(concept, reviewer=reviewer)
        self.bundle.save_concept(stamped)
        self._git("add", relative)
        self._git("commit", "-m", f"ci: verify {concept_id} (human:{reviewer})")
        commit = self._git("rev-parse", "HEAD")
        self._git("branch", "-d", branch, check=False)
        return ReviewResult(concept_id=concept_id, approved=True, commit=commit, branch=branch)

    def approve(self, concept_id: str, *, reviewer: str, message: str | None = None) -> ReviewResult:
        """Merge the review branch, then stamp verified/stable (the CI step)."""
        self.init()
        branch = self._branch_for(concept_id)
        self._git("checkout", "main")
        self._git("merge", "--no-ff", branch, "-m", message or f"Merge {branch}")

        concept = self.bundle.read_concept(concept_id)
        stamped = stamp_verified(concept, reviewer=reviewer)
        self.bundle.save_concept(stamped)
        relative = self.bundle.path_for_id(concept_id).relative_to(self.bundle.root).as_posix()
        self._git("add", relative)
        self._git("commit", "-m", f"ci: verify {concept_id} (human:{reviewer})")
        commit = self._git("rev-parse", "HEAD")
        self._git("branch", "-d", branch, check=False)
        return ReviewResult(concept_id=concept_id, approved=True, commit=commit, branch=branch)

    def reject(self, concept_id: str, *, message: str | None = None) -> ReviewResult:
        """Discard the review branch without stamping the draft."""
        self.init()
        branch = self._branch_for(concept_id)
        self._git("checkout", "main")
        self._git("branch", "-D", branch, check=False)
        return ReviewResult(concept_id=concept_id, approved=False, branch=branch)
