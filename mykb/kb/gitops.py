"""Git plumbing for knowledge-base repositories."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from ..okf.bundle import Bundle

AUTHOR_NAME = "mykb-agent"
AUTHOR_EMAIL = "agent@mykb.local"
LFS_ATTRIBUTES = (
    "*.png filter=lfs diff=lfs merge=lfs -text",
    "*.jpg filter=lfs diff=lfs merge=lfs -text",
    "*.jpeg filter=lfs diff=lfs merge=lfs -text",
    "*.gif filter=lfs diff=lfs merge=lfs -text",
    "*.webp filter=lfs diff=lfs merge=lfs -text",
)


class GitError(RuntimeError):
    """Raised when a git operation fails."""


def inject_credential(url: str, token: str | None) -> str:
    """Embed an HTTPS token into a remote URL for server-side pushes."""
    if not token:
        return url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return url
    host = parts.hostname
    if parts.port:
        host = f"{host}:{parts.port}"
    netloc = f"oauth2:{token}@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _git(
    *args: str,
    cwd: str | Path | None = None,
    check: bool = True,
    with_author: bool = False,
) -> str:
    command = ["git"]
    if cwd is not None:
        command += ["-C", str(cwd)]
    if with_author:
        command += [
            "-c",
            f"user.name={AUTHOR_NAME}",
            "-c",
            f"user.email={AUTHOR_EMAIL}",
        ]
    command += list(args)
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if check and proc.returncode != 0:
        raise GitError(proc.stderr.strip() or proc.stdout.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def _has_commit(path: Path) -> bool:
    return bool(_git("rev-parse", "--verify", "HEAD", cwd=path, check=False))


def has_git_lfs() -> bool:
    """Return whether the git-lfs extension is available on this host."""
    return shutil.which("git-lfs") is not None


def ensure_lfs(path: Path) -> bool:
    """Configure standard Git LFS for a knowledge-base repository.

    Without the ``git-lfs`` binary we skip configuration entirely: adding the
    filter attributes would make ``git add`` of binary assets fail, while
    markdown-only imports must keep working in reduced environments.
    """
    if not has_git_lfs():
        return False
    attributes = path / ".gitattributes"
    existing = attributes.read_text(encoding="utf-8").splitlines() if attributes.exists() else []
    missing = [line for line in LFS_ATTRIBUTES if line not in existing]
    if missing:
        content = "\n".join([*existing, *missing]) + "\n"
        attributes.write_text(content, encoding="utf-8")
    _git("lfs", "install", "--local", cwd=path)
    return True


def probe_remote_lfs(path: Path, remote: str) -> bool:
    """Probe whether a remote exposes the Git LFS batch/locks API."""
    try:
        _git("lfs", "locks", "--remote", remote, cwd=path)
    except GitError:
        return False
    return True


def _is_http(url: str) -> bool:
    return urlsplit(url).scheme in ("http", "https")


def _commit_all(path: Path, message: str) -> None:
    _git("add", "-A", cwd=path)
    if _git("status", "--porcelain", cwd=path):
        _git("commit", "-m", message, cwd=path, with_author=True)


def init_local_repo(path: Path, *, title: str) -> None:
    """Create a fresh bundle repository at ``path``."""
    path.mkdir(parents=True, exist_ok=False)
    _git("init", "-b", "main", cwd=path)
    Bundle(path).ensure_layout(title=title)
    ensure_lfs(path)
    _commit_all(path, "chore: init bundle")


def clone_or_init_with_remote(
    path: Path,
    *,
    title: str,
    git_url: str,
    branch: str,
    token: str | None,
) -> None:
    """Clone a remote bundle (empty or populated) and initialise the layout."""
    remote = inject_credential(git_url, token)
    _git("clone", remote, str(path))
    if not _has_commit(path):
        _git("checkout", "-B", branch, cwd=path)
    else:
        remote_branches = _git("ls-remote", "--heads", "origin", cwd=path)
        if f"refs/heads/{branch}" in remote_branches:
            _git("checkout", branch, cwd=path)
        else:
            _git("checkout", "-B", branch, cwd=path)
    Bundle(path).ensure_layout(title=title)
    ensure_lfs(path)
    _commit_all(path, "chore: init bundle layout")
    _git("push", "-u", "origin", branch, cwd=path)


def remote_has_commits(git_url: str, token: str | None = None) -> bool:
    remote = inject_credential(git_url, token)
    output = _git("ls-remote", "--heads", remote)
    return bool(output.strip())


def bind_remote(
    path: Path,
    *,
    git_url: str,
    branch: str,
    token: str | None,
) -> None:
    if remote_has_commits(git_url, token):
        raise GitError("remote already contains commits; only empty remotes can be bound")
    remote = inject_credential(git_url, token)
    if _is_http(git_url):
        if not has_git_lfs():
            raise GitError(
                "git-lfs is required to bind an HTTPS remote; install git-lfs first"
            )
        ensure_lfs(path)
        if not probe_remote_lfs(path, remote):
            raise GitError(
                "remote does not support Git LFS; derived assets cannot be pushed"
            )
    _git("remote", "remove", "origin", cwd=path, check=False)
    _git("remote", "add", "origin", remote, cwd=path)
    _git("push", "-u", "origin", branch, cwd=path)


def push(path: Path, branch: str, token: str | None = None) -> None:
    _git("push", "origin", branch, cwd=path)


def commit_all(path: Path, message: str) -> None:
    """Public wrapper: stage and commit every change in ``path``."""
    ensure_lfs(path)
    _commit_all(path, message)


def current_branch(path: Path) -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD", cwd=path)


def has_branch(path: Path, branch: str) -> bool:
    ref = _git("rev-parse", "--verify", f"refs/heads/{branch}", cwd=path, check=False)
    return bool(ref)


def checkout(path: Path, branch: str) -> None:
    _git("checkout", branch, cwd=path)


def checkout_new_branch(path: Path, branch: str, *, base: str = "main") -> None:
    """Create/reset ``branch`` at ``base`` and check it out."""
    if current_branch(path) != base:
        checkout(path, base)
    _git("checkout", "-B", branch, base, cwd=path)


def merge_branch(path: Path, branch: str, message: str) -> None:
    if current_branch(path) != "main":
        checkout(path, "main")
    _git("merge", "--no-ff", branch, "-m", message, cwd=path, with_author=True)


def delete_branch(path: Path, branch: str) -> None:
    if current_branch(path) == branch:
        checkout(path, "main")
    _git("branch", "-D", branch, cwd=path, check=False)


def changed_files_vs(path: Path, base: str, branch: str) -> list[str]:
    output = _git("diff", "--name-only", "-z", f"{base}...{branch}", cwd=path)
    return [item for item in output.split("\x00") if item]


def diff_text(path: Path, base: str, branch: str) -> str:
    return _git("diff", f"{base}...{branch}", cwd=path)


def reset_hard(path: Path) -> None:
    _git("reset", "--hard", cwd=path)


def force_checkout(path: Path, branch: str) -> None:
    _git("checkout", "-f", branch, cwd=path)
