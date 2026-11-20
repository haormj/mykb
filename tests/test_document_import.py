from __future__ import annotations

import io
import subprocess
import threading
import time
import uuid
import zipfile
from pathlib import Path

from mykb.db.models import ImportTask
from mykb.importing.service import mark_stale_running_failed, run_import_task
from mykb.okf.bundle import Bundle
from tests.helpers import create_kb, register

TERMINAL = {"succeeded", "partial", "failed", "cancelled"}


def _wait_task(client, headers, kb_id: str, task_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/kbs/{kb_id}/import-tasks/{task_id}", headers=headers)
        body = response.json()
        if body["status"] in TERMINAL:
            return body
        time.sleep(0.05)
    raise AssertionError(f"task {task_id} did not finish in time: {body}")


def _zip(name: str, content: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, content)
    return buffer.getvalue()


def test_upload_markdown_creates_raw_document(client):
    headers = register(client, "import-owner")
    kb = create_kb(client, headers, "import-kb")
    path = Path(kb["local_path"])
    before = subprocess.run(
        ["git", "-C", str(path), "rev-list", "--count", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    response = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("note.md", b"# Note\n\nalpha content", "text/markdown"))],
        headers=headers,
    )
    assert response.status_code == 201, response.text
    task = _wait_task(client, headers, kb["id"], response.json()["id"])
    assert task["status"] == "succeeded", task
    assert task["total"] == 1 and task["added"] == 1 and task["failed"] == 0

    documents = client.get(f"/kbs/{kb['id']}/documents", headers=headers).json()["documents"]
    assert len(documents) == 1
    document = documents[0]
    assert document["concept_id"] == "raw/upload/note"
    assert document["import_task_id"] == task["id"]
    assert document["resource"].startswith("upload://")

    concept = Bundle(path).read_concept("raw/upload/note")
    assert concept.type == "源数据"

    after = subprocess.run(
        ["git", "-C", str(path), "rev-list", "--count", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert int(after) == int(before) + 1


def test_upload_zip_and_reject_traversal(client):
    headers = register(client, "zip-owner")
    kb = create_kb(client, headers, "zip-kb")

    ok = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("docs.zip", _zip("docs/guide.md", "# Guide\n\nguide"), "application/zip"))],
        headers=headers,
    )
    assert ok.status_code == 201, ok.text
    task = _wait_task(client, headers, kb["id"], ok.json()["id"])
    assert task["status"] == "succeeded"

    bad = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("evil.zip", _zip("../evil.md", "evil"), "application/zip"))],
        headers=headers,
    )
    assert bad.status_code == 400


def test_unsupported_type_and_oversize_rejected(client):
    headers = register(client, "limit-owner")
    kb = create_kb(client, headers, "limit-kb")

    bad_type = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("a.exe", b"binary", "application/octet-stream"))],
        headers=headers,
    )
    assert bad_type.status_code == 400

    original = client.app.state.settings.upload_max_bytes
    client.app.state.settings = client.app.state.settings.__class__(
        **{**client.app.state.settings.__dict__, "upload_max_bytes": 4}
    )
    try:
        oversize = client.post(
            f"/kbs/{kb['id']}/import-tasks",
            files=[("files", ("big.md", b"much too large", "text/markdown"))],
            headers=headers,
        )
        assert oversize.status_code == 400
    finally:
        client.app.state.settings = client.app.state.settings.__class__(
            **{**client.app.state.settings.__dict__, "upload_max_bytes": original}
        )


def test_partial_when_an_item_fails(client):
    headers = register(client, "partial-owner")
    kb = create_kb(client, headers, "partial-kb")
    blocked = Path(kb["local_path"]) / "raw" / "upload" / "blocked.md"
    blocked.parent.mkdir(parents=True, exist_ok=True)
    blocked.mkdir()

    response = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[
            ("files", ("blocked.md", b"# Blocked", "text/markdown")),
            ("files", ("good.md", b"# Good", "text/markdown")),
        ],
        headers=headers,
    )
    assert response.status_code == 201, response.text
    task = _wait_task(client, headers, kb["id"], response.json()["id"])
    assert task["status"] == "partial", task
    assert task["failed"] == 1 and task["added"] == 1


def test_cancel_queued_task_and_worker_skips(client):
    headers = register(client, "cancel-owner")
    kb = create_kb(client, headers, "cancel-kb")

    class _NoopExecutor:
        def submit(self, *_args, **_kwargs):
            return None

    client.app.state.import_executor = _NoopExecutor()  # type: ignore[assignment]
    response = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("late.md", b"# Late", "text/markdown"))],
        headers=headers,
    )
    task_id = response.json()["id"]
    assert response.json()["status"] == "queued"

    cancelled = client.post(
        f"/kbs/{kb['id']}/import-tasks/{task_id}/cancel", headers=headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    app = client.app
    run_import_task(
        task_id,
        session_factory=app.state.session_factory,
        settings=app.state.settings,
        cache=app.state.retrieval_cache,
        locks=app.state.kb_locks,
        lock_guard=app.state.kb_locks_guard,
    )
    assert not (app.state.settings.tmp_root / task_id).exists()


def test_restart_marks_running_as_failed(client):
    headers = register(client, "restart-owner")
    kb = create_kb(client, headers, "restart-kb")
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    app = client.app
    with app.state.session_factory() as session:
        session.add(
            ImportTask(
                kb_id=kb["id"],
                source_type="upload",
                source_config={},
                status="running",
                created_by=user_id,
            )
        )
        session.commit()

    assert mark_stale_running_failed(app.state.session_factory) >= 1
    tasks = client.get(f"/kbs/{kb['id']}/import-tasks", headers=headers).json()["tasks"]
    assert tasks[0]["status"] == "failed"


def test_permissions_and_cross_kb_isolation(client):
    owner = register(client, "perm-owner")
    kb = create_kb(client, owner, "perm-kb")
    other = create_kb(client, owner, "perm-other")

    viewer = register(client, "perm-viewer")
    client.post(
        f"/kbs/{kb['id']}/members",
        json={"username": "perm-viewer", "role": "viewer"},
        headers=owner,
    )

    denied = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("x.md", b"# X", "text/markdown"))],
        headers=viewer,
    )
    assert denied.status_code == 403

    allowed = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("x.md", b"# X", "text/markdown"))],
        headers=owner,
    )
    assert allowed.status_code == 201
    _wait_task(client, owner, kb["id"], allowed.json()["id"])

    assert client.get(f"/kbs/{other['id']}/import-tasks", headers=owner).json()["tasks"] == []
    assert client.get(f"/kbs/{other['id']}/documents", headers=owner).json()["documents"] == []


def test_import_commits_and_pushes_to_remote(client, tmp_path):
    headers = register(client, "remote-import-owner")
    remote = tmp_path / "import-remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    kb = create_kb(client, headers, "import-remote-kb", git_url=str(remote))
    before = subprocess.run(
        ["git", "-C", str(remote), "rev-parse", "refs/heads/main"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    response = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("remote.md", b"# Remote\n\ncontent", "text/markdown"))],
        headers=headers,
    )
    task = _wait_task(client, headers, kb["id"], response.json()["id"])
    assert task["status"] == "succeeded"

    after = subprocess.run(
        ["git", "-C", str(remote), "rev-parse", "refs/heads/main"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert after != before


def test_same_kb_imports_are_serialized(client):
    headers = register(client, "serial-owner")
    kb = create_kb(client, headers, "serial-kb")
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    app = client.app
    settings = app.state.settings

    task_ids: list[str] = []
    for index in range(2):
        task_id = str(uuid.uuid4())
        staging = settings.tmp_root / task_id
        staging.mkdir(parents=True, exist_ok=True)
        (staging / f"{index}.md").write_text(f"# Doc {index}\n\ncontent", encoding="utf-8")
        with app.state.session_factory() as session:
            session.add(
                ImportTask(
                    id=task_id,
                    kb_id=kb["id"],
                    source_type="upload",
                    source_config={},
                    status="queued",
                    created_by=user_id,
                )
            )
            session.commit()
        task_ids.append(task_id)

    guard = threading.Lock()
    active = 0
    max_active = 0

    def on_item(_task) -> None:
        nonlocal active, max_active
        with guard:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.1)
        with guard:
            active -= 1

    def run(task_id: str) -> None:
        run_import_task(
            task_id,
            session_factory=app.state.session_factory,
            settings=settings,
            cache=app.state.retrieval_cache,
            locks=app.state.kb_locks,
            lock_guard=app.state.kb_locks_guard,
            on_item=on_item,
        )

    threads = [threading.Thread(target=run, args=(task_id,)) for task_id in task_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert all(not thread.is_alive() for thread in threads)
    assert max_active == 1

    tasks = client.get(f"/kbs/{kb['id']}/import-tasks", headers=headers).json()["tasks"]
    assert all(task["status"] == "succeeded" for task in tasks)
