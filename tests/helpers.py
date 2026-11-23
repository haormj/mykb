from __future__ import annotations


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register(client, username: str = "alice", password: str = "secret123") -> dict[str, str]:
    response = client.post(
        "/auth/register", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return auth(response.json()["token"])


def login(client, username: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return auth(response.json()["token"])


def create_kb(client, headers: dict[str, str], name: str = "kb", **kwargs) -> dict:
    response = client.post("/kbs", json={"name": name, **kwargs}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def publish_current(client, kb: dict, *, commit: str | None = None) -> dict:
    """Materialize and activate a snapshot for ``kb`` from its current bundle.

    Uses the platform orchestrator directly (not the HTTP task) so tests can
    exercise the explicit-publish flow before a publish task exists.
    """
    import uuid
    from pathlib import Path

    from mykb.okf.bundle import Bundle
    from mykb.retrieval.index import select_indexable_knowledge
    from mykb.retrieval.publish import SnapshotPublisher

    app = client.app
    bundle = Bundle(Path(kb["local_path"]))
    concepts = select_indexable_knowledge(bundle)
    label = commit or uuid.uuid4().hex
    with app.state.session_factory() as session:
        version = SnapshotPublisher(
            app.state.retrieval_backend, sleep=lambda _s: None
        ).publish(session, kb_id=kb["id"], concepts=concepts, git_commit=label)
        return {"id": version.id, "status": version.status, "version": label}
