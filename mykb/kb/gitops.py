"""Git plumbing for knowledge-base repositories."""

from __future__ import annotations

import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from ..okf.bundle import Bundle

AUTHOR_NAME = "mykb-agent"
AUTHOR_EMAIL = "agent@mykb.local"


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


def _commit_all(path: Path, message: str) -> None:
    _git("add", "-A", cwd=path)
    if _git("status", "--porcelain", cwd=path):
        _git("commit", "-m", message, cwd=path, with_author=True)


def init_local_repo(path: Path, *, title: str) -> None:
    """Create a fresh bundle repository at ``path``."""
    path.mkdir(parents=True, exist_ok=False)
    _git("init", "-b", "main", cwd=path)
    Bundle(path).ensure_layout(title=title)
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
    _git("remote", "remove", "origin", cwd=path, check=False)
    _git("remote", "add", "origin", remote, cwd=path)
    _git("push", "-u", "origin", branch, cwd=path)


def push(path: Path, branch: str, token: str | None = None) -> None:
    _git("push", "origin", branch, cwd=path)


def commit_all(path: Path, message: str) -> None:
    """Public wrapper: stage and commit every change in ``path``."""
    _commit_all(path, message)
