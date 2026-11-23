from __future__ import annotations

import subprocess

import pytest

from mykb.kb import gitops


def test_init_local_repo_configures_lfs_when_available(tmp_path):
    if not gitops.has_git_lfs():
        pytest.skip("git-lfs is not installed in this environment")
    path = tmp_path / "kb"
    gitops.init_local_repo(path, title="KB")
    attributes = (path / ".gitattributes").read_text(encoding="utf-8")
    for line in gitops.LFS_ATTRIBUTES:
        assert line in attributes
    configured = subprocess.run(
        ["git", "-C", str(path), "config", "--local", "--get", "filter.lfs.clean"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "git-lfs" in configured


def test_ensure_lfs_is_noop_without_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(gitops, "has_git_lfs", lambda: False)
    path = tmp_path / "kb"
    path.mkdir()
    assert gitops.ensure_lfs(path) is False
    assert not (path / ".gitattributes").exists()


def test_bind_remote_requires_lfs_binary_for_https(tmp_path, monkeypatch):
    monkeypatch.setattr(gitops, "remote_has_commits", lambda *a, **k: False)
    monkeypatch.setattr(gitops, "has_git_lfs", lambda: False)
    with pytest.raises(gitops.GitError, match="git-lfs is required"):
        gitops.bind_remote(
            tmp_path,
            git_url="https://git.example.com/team/kb.git",
            branch="main",
            token="token",
        )


def test_bind_remote_rejects_remote_without_lfs(tmp_path, monkeypatch):
    monkeypatch.setattr(gitops, "remote_has_commits", lambda *a, **k: False)
    monkeypatch.setattr(gitops, "has_git_lfs", lambda: True)
    monkeypatch.setattr(gitops, "ensure_lfs", lambda _path: True)
    monkeypatch.setattr(gitops, "probe_remote_lfs", lambda _path, _remote: False)
    with pytest.raises(gitops.GitError, match="does not support Git LFS"):
        gitops.bind_remote(
            tmp_path,
            git_url="https://git.example.com/team/kb.git",
            branch="main",
            token="token",
        )


def test_bind_remote_accepts_lfs_capable_https_remote(tmp_path, monkeypatch):
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(gitops, "remote_has_commits", lambda *a, **k: False)
    monkeypatch.setattr(gitops, "has_git_lfs", lambda: True)
    monkeypatch.setattr(gitops, "ensure_lfs", lambda _path: True)
    monkeypatch.setattr(gitops, "probe_remote_lfs", lambda _path, _remote: True)
    monkeypatch.setattr(
        gitops, "_git", lambda *args, **kwargs: calls.append(args) or ""
    )
    gitops.bind_remote(
        tmp_path,
        git_url="https://git.example.com/team/kb.git",
        branch="main",
        token="token",
    )
    assert ("remote", "add", "origin", "https://oauth2:token@git.example.com/team/kb.git") in calls


def test_bind_remote_allows_local_path_without_lfs(tmp_path, monkeypatch):
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(gitops, "remote_has_commits", lambda *a, **k: False)
    monkeypatch.setattr(gitops, "has_git_lfs", lambda: False)
    monkeypatch.setattr(
        gitops, "_git", lambda *args, **kwargs: calls.append(args) or ""
    )
    gitops.bind_remote(tmp_path, git_url=str(tmp_path / "remote.git"), branch="main", token=None)
    assert any(call[:2] == ("remote", "add") for call in calls)


def test_probe_remote_lfs_reports_git_errors(tmp_path, monkeypatch):
    def _raise(*args, **kwargs):
        raise gitops.GitError("no lfs")

    monkeypatch.setattr(gitops, "_git", _raise)
    assert gitops.probe_remote_lfs(tmp_path, "https://example.com/kb.git") is False

    monkeypatch.setattr(gitops, "_git", lambda *args, **kwargs: "")
    assert gitops.probe_remote_lfs(tmp_path, "https://example.com/kb.git") is True
