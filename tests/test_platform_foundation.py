from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mykb.auth.service import find_or_create_sso_user
from mykb.db.bootstrap import bootstrap
from mykb.db.models import User
from mykb.okf.bundle import Bundle
from mykb.okf.model import Concept
from tests.helpers import auth, create_kb, register


def test_unique_constraints_and_bootstrap_idempotent(app):
    factory = app.state.session_factory
    with factory() as session:
        bootstrap(session, {"ADMIN_USERNAME": "root", "ADMIN_PASSWORD": "root-pass"})
        bootstrap(session, {"ADMIN_USERNAME": "root", "ADMIN_PASSWORD": "root-pass"})
        roots = session.scalars(select(User).where(User.username == "root")).all()
        assert len(roots) == 1

        session.add(User(username="root", display_name="dup"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_sso_identity_reuses_account(app):
    factory = app.state.session_factory
    with factory() as session:
        first = find_or_create_sso_user(
            session, provider="oidc", external_id="u-1", username="sso-user"
        )
        session.commit()
        second = find_or_create_sso_user(
            session, provider="oidc", external_id="u-1", username="other-name"
        )
        session.commit()
        assert first.id == second.id


def test_auth_flow(client):
    response = client.post("/auth/register", json={"username": "alice", "password": "secret123"})
    assert response.status_code == 200
    token = response.json()["token"]
    headers = auth(token)

    assert client.get("/auth/me", headers=headers).json()["username"] == "alice"
    assert client.get("/auth/me").status_code == 401
    assert (
        client.post("/auth/login", json={"username": "alice", "password": "wrong"}).status_code
        == 401
    )
    assert (
        client.post("/auth/register", json={"username": "alice", "password": "secret123"}).status_code
        == 400
    )

    assert client.post("/auth/logout", headers=headers).status_code == 200
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_platform_admin_gate(client):
    user_headers = register(client, "plain")
    admin_headers = auth(
        client.post("/auth/login", json={"username": "root", "password": "root-pass"}).json()["token"]
    )
    assert client.get("/admin/users", headers=user_headers).status_code == 403
    assert client.get("/admin/users", headers=admin_headers).status_code == 200


def test_no_default_knowledge_base(client):
    headers = register(client, "fresh")
    assert client.get("/kbs", headers=headers).json()["knowledge_bases"] == []


def test_local_kb_lifecycle(client):
    headers = register(client, "kb-owner")
    kb = create_kb(client, headers, "本地知识库")
    path = Path(kb["local_path"])

    assert path.is_dir()
    assert (path / ".git").is_dir()
    for level in ("raw", "knowledge", "evals"):
        assert (path / level / "index.md").exists()
    head = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    assert head.stdout.strip()

    assert client.post("/kbs", json={"name": "本地知识库"}, headers=headers).status_code == 409
    listing = client.get("/kbs", headers=headers).json()["knowledge_bases"]
    assert [item["id"] for item in listing] == [kb["id"]]
    assert client.get(f"/kbs/{kb['id']}", headers=headers).json()["my_role"] == "owner"


def test_remote_create_and_bind(client, tmp_path):
    headers = register(client, "remote-owner")

    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    kb = create_kb(client, headers, "remote-kb", git_url=str(remote))
    assert kb["has_remote"] is True
    pushed = subprocess.run(
        ["git", "-C", str(remote), "rev-parse", "--verify", "refs/heads/main"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert pushed.returncode == 0

    local = create_kb(client, headers, "bind-kb")
    empty = tmp_path / "empty.git"
    subprocess.run(["git", "init", "--bare", str(empty)], check=True, capture_output=True)
    bound = client.post(
        f"/kbs/{local['id']}/remote", json={"git_url": str(empty)}, headers=headers
    )
    assert bound.status_code == 200, bound.text

    second = create_kb(client, headers, "bind-conflict")
    conflict = client.post(
        f"/kbs/{second['id']}/remote", json={"git_url": str(empty)}, headers=headers
    )
    assert conflict.status_code == 400


def test_unreachable_remote_rolls_back(client, tmp_path):
    headers = register(client, "rollback-user")
    missing = tmp_path / "does-not-exist.git"
    response = client.post(
        "/kbs", json={"name": "bad-remote", "git_url": str(missing)}, headers=headers
    )
    assert response.status_code == 400
    assert client.get("/kbs", headers=headers).json()["knowledge_bases"] == []
    assert list((tmp_path / "kbs").iterdir()) == []


def test_member_roles_and_boundaries(client):
    owner = register(client, "owner1")
    kb = create_kb(client, owner, "members-kb")
    base = f"/kbs/{kb['id']}/members"

    editor = register(client, "editor1")
    viewer = register(client, "viewer1")
    admin = register(client, "admin1")

    assert (
        client.post(base, json={"username": "editor1", "role": "editor"}, headers=owner).status_code
        == 201
    )
    assert (
        client.post(base, json={"username": "viewer1", "role": "viewer"}, headers=owner).status_code
        == 201
    )
    assert (
        client.post(base, json={"username": "admin1", "role": "admin"}, headers=owner).status_code
        == 201
    )

    # An editor may not manage members.
    assert (
        client.post(base, json={"username": "admin1", "role": "viewer"}, headers=editor).status_code
        == 403
    )
    # An admin may not grant admin or above.
    assert (
        client.post(base, json={"username": "owner1", "role": "admin"}, headers=admin).status_code
        == 403
    )
    # Viewer is read-only for retrieval but cannot review.
    assert client.get(f"/kbs/{kb['id']}/review/drafts", headers=viewer).status_code == 403

    members = client.get(base, headers=owner).json()["members"]
    assert {m["username"] for m in members} == {"owner1", "editor1", "viewer1", "admin1"}

    transferred = client.post(f"{base}/" + _user_id(members, "editor1") + "/transfer", headers=owner)
    assert transferred.status_code == 200, transferred.text
    members = client.get(base, headers=editor).json()["members"]
    assert _role(members, "editor1") == "owner"
    assert _role(members, "owner1") == "admin"


def test_kb_scoped_isolation(client):
    headers = register(client, "scope-user")
    first = create_kb(client, headers, "scope-a")
    second = create_kb(client, headers, "scope-b")

    bundle_a = Bundle(first["local_path"])
    bundle_b = Bundle(second["local_path"])
    bundle_a.write_concept(
        Concept(
            frontmatter={
                "type": "业务知识",
                "status": "stable",
                "verified": [{"by": "human:alice", "at": "2026-01-01T00:00:00Z"}],
            },
            body="alpha unique term",
        ),
        "knowledge",
        "topic/a",
    )
    bundle_b.write_concept(
        Concept(
            frontmatter={
                "type": "业务知识",
                "status": "stable",
                "verified": [{"by": "human:alice", "at": "2026-01-01T00:00:00Z"}],
            },
            body="beta other term",
        ),
        "knowledge",
        "topic/b",
    )

    hits_a = client.get(
        f"/kbs/{first['id']}/retrieve", params={"q": "alpha"}, headers=headers
    ).json()["hits"]
    hits_b = client.get(
        f"/kbs/{second['id']}/retrieve", params={"q": "alpha"}, headers=headers
    ).json()["hits"]
    assert [hit["concept_id"] for hit in hits_a] == ["knowledge/topic/a"]
    assert hits_b == []


def test_legacy_global_routes_removed(client):
    for path in ("/retrieve", "/answer", "/eval/sets", "/review/drafts", "/index-sync"):
        assert client.get(path).status_code == 404


def _user_id(members: list[dict], username: str) -> str:
    return next(m["user_id"] for m in members if m["username"] == username)


def _role(members: list[dict], username: str) -> str:
    return next(m["role"] for m in members if m["username"] == username)
