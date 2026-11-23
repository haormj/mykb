from __future__ import annotations

import subprocess

from mykb.kb import gitops


def _git(repo, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@test", *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "commit", "--allow-empty", "-m", "base")
    return repo


def test_changed_files_vs_returns_unquoted_unicode_paths(tmp_path):
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-b", "feature")
    target = repo / "knowledge" / "topics" / "退款政策.md"
    target.parent.mkdir(parents=True)
    target.write_text("body", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "add unicode concept")

    changed = gitops.changed_files_vs(repo, "main", "feature")

    assert changed == ["knowledge/topics/退款政策.md"]
    assert changed[0].startswith("knowledge/")


def test_changed_files_vs_handles_paths_with_spaces(tmp_path):
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-b", "feature")
    target = repo / "knowledge" / "my concept.md"
    target.parent.mkdir(parents=True)
    target.write_text("body", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "add concept with space")

    changed = gitops.changed_files_vs(repo, "main", "feature")

    assert changed == ["knowledge/my concept.md"]
