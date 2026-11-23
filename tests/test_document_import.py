from __future__ import annotations

import hashlib
import io
import subprocess
import threading
import time
import uuid
import zipfile
from pathlib import Path

import pytest

from mykb.conversion import (
    Asset,
    ConversionResult,
    ConversionUnavailableError,
    ConverterService,
    MarkdownPassthroughConverter,
    RawDocument,
)
from mykb.db.models import ImportTask
from mykb.importing.service import mark_stale_running_failed, run_import_task
from mykb.kb import gitops
from mykb.okf.bundle import Bundle
from mykb.okf.model import Concept
from tests.helpers import create_kb, register

ACTIVE_IMPORT = {"queued", "running", "converting"}
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PNG = b"\x89PNG\r\n\x1a\nfake-image"


def _wait_import(client, headers, kb_id: str, task_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    body: dict = {}
    while time.time() < deadline:
        body = client.get(f"/kbs/{kb_id}/import-tasks/{task_id}", headers=headers).json()
        if body["status"] not in ACTIVE_IMPORT:
            return body
        time.sleep(0.05)
    raise AssertionError(f"task {task_id} did not finish conversion: {body}")


def _wait_review(client, headers, kb_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        mrs = client.get(f"/kbs/{kb_id}/review/mrs", headers=headers).json()["mrs"]
        ready = [mr for mr in mrs if mr["status"] == "reviewing"]
        if ready:
            return ready[0]
        tasks = client.get(f"/kbs/{kb_id}/import-tasks", headers=headers).json()["tasks"]
        if (
            tasks
            and all(t["status"] in {"failed", "cancelled", "succeeded"} for t in tasks)
            and not ready
        ):
            raise AssertionError(f"no review MR produced: {tasks}")
        time.sleep(0.05)
    raise AssertionError("timed out waiting for review MR")


def _approve_mr(client, headers, kb_id: str, item_id: str) -> None:
    response = client.post(
        f"/kbs/{kb_id}/review/mrs/{item_id}/approve",
        params={"reviewer": "alice"},
        headers=headers,
    )
    assert response.status_code == 200, response.text


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _branch_show(path: Path, branch: str, relative: str) -> str:
    return _git(path, "show", f"{branch}:{relative}")


def _branch_files(path: Path, branch: str) -> list[str]:
    return _git(path, "ls-tree", "-r", "--name-only", branch).splitlines()


def _zip(name: str, content: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, content)
    return buffer.getvalue()


def _zip_entries(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


class _StubConverter:
    name = "stub"

    def __init__(self, *, fail_unavailable: bool = False) -> None:
        self.fail_unavailable = fail_unavailable

    def supports(self, suffix: str, mime: str) -> bool:
        return suffix == ".docx"

    def convert(self, document: RawDocument) -> ConversionResult:
        if self.fail_unavailable:
            raise ConversionUnavailableError("conversion service unavailable")
        return ConversionResult(
            markdown="# Converted\n\n![img](img-1.png)",
            title="Converted",
            assets=[Asset(name="img-1.png", data=PNG, source_name="img-1.png")],
            producer="stub@1",
        )


def _use_stub_converter(client, *, fail_unavailable: bool = False) -> None:
    client.app.state.converter_service = ConverterService(
        client.app.state.settings,
        converters=[
            MarkdownPassthroughConverter(),
            _StubConverter(fail_unavailable=fail_unavailable),
        ],
    )


def _approve_all(client, headers, kb_id: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        mrs = client.get(f"/kbs/{kb_id}/review/mrs", headers=headers).json()["mrs"]
        ready = [mr for mr in mrs if mr["status"] == "reviewing"]
        if ready:
            _approve_mr(client, headers, kb_id, ready[0]["item_id"])
            continue
        tasks = client.get(f"/kbs/{kb_id}/import-tasks", headers=headers).json()["tasks"]
        if tasks and tasks[0]["status"] in {"merged", "failed", "succeeded", "partial"}:
            return
        time.sleep(0.05)
    raise AssertionError("could not drain review queue")


def test_upload_markdown_creates_raw_document(client):
    headers = register(client, "import-owner")
    kb = create_kb(client, headers, "import-kb")
    path = Path(kb["local_path"])

    response = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("note.md", b"# Note\n\nalpha content", "text/markdown"))],
        headers=headers,
    )
    assert response.status_code == 201, response.text
    task = _wait_import(client, headers, kb["id"], response.json()["id"])
    assert task["total"] == 1 and task["added"] == 1 and task["failed"] == 0

    mr = _wait_review(client, headers, kb["id"])
    assert mr["concept_id"] == "raw/upload/note"
    assert not (path / "raw" / "upload" / "note.md").exists()
    assert client.get(f"/kbs/{kb['id']}/documents", headers=headers).json()["documents"] == []

    raw = Concept.from_text(_branch_show(path, mr["branch"], "raw/upload/note.md"))
    assert raw.type == "源数据"
    assert raw.frontmatter["x-source-format"] == "md"
    assert raw.frontmatter["x-original-name"] == "note.md"
    assert raw.frontmatter["x-original-sha256"] == hashlib.sha256(
        b"# Note\n\nalpha content"
    ).hexdigest()
    assert raw.frontmatter["x-original-size"] == len(b"# Note\n\nalpha content")
    assert raw.frontmatter["x-parsed-by"] == "passthrough"
    assert raw.frontmatter["x-import-task"] == task["id"]

    _approve_mr(client, headers, kb["id"], mr["item_id"])
    documents = client.get(f"/kbs/{kb['id']}/documents", headers=headers).json()["documents"]
    assert documents[0]["concept_id"] == "raw/upload/note"


def test_upload_zip_and_reject_traversal(client):
    headers = register(client, "zip-owner")
    kb = create_kb(client, headers, "zip-kb")

    ok = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("docs.zip", _zip("docs/guide.md", "# Guide\n\nguide"), "application/zip"))],
        headers=headers,
    )
    assert ok.status_code == 201, ok.text
    task = _wait_import(client, headers, kb["id"], ok.json()["id"])
    assert task["added"] == 1
    mr = _wait_review(client, headers, kb["id"])
    assert mr["concept_id"] == "raw/upload/docs/guide"

    bad = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("evil.zip", _zip("../evil.md", "evil"), "application/zip"))],
        headers=headers,
    )
    assert bad.status_code == 400


def test_unsupported_type_and_oversize_rejected(client):
    headers = register(client, "limit-owner")
    kb = create_kb(client, headers, "limit-kb")

    for name, content in (
        ("a.exe", b"binary"),
        ("a.pdf", b"%PDF-1.7"),
        ("a.doc", b"\xd0\xcf\x11\xe0"),
    ):
        bad_type = client.post(
            f"/kbs/{kb['id']}/import-tasks",
            files=[("files", (name, content, "application/octet-stream"))],
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
    _wait_import(client, owner, kb["id"], allowed.json()["id"])

    assert client.get(f"/kbs/{other['id']}/import-tasks", headers=owner).json()["tasks"] == []
    assert client.get(f"/kbs/{other['id']}/documents", headers=owner).json()["documents"] == []
    assert client.get(f"/kbs/{other['id']}/review/mrs", headers=owner).json()["mrs"] == []


def test_import_merges_and_pushes_to_remote(client, tmp_path):
    headers = register(client, "remote-import-owner")
    remote = tmp_path / "import-remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    kb = create_kb(client, headers, "import-remote-kb", git_url=str(remote))
    before = _git(remote, "rev-parse", "refs/heads/main")

    response = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("remote.md", b"# Remote\n\ncontent", "text/markdown"))],
        headers=headers,
    )
    _wait_import(client, headers, kb["id"], response.json()["id"])
    mr = _wait_review(client, headers, kb["id"])
    _approve_mr(client, headers, kb["id"], mr["item_id"])

    after = _git(remote, "rev-parse", "refs/heads/main")
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
            extraction_locks=app.state.extraction_locks,
            extraction_guard=app.state.extraction_locks_guard,
        )

    threads = [threading.Thread(target=run, args=(task_id,)) for task_id in task_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)
    assert max_active == 1

    tasks = client.get(f"/kbs/{kb['id']}/import-tasks", headers=headers).json()["tasks"]
    assert all(task["status"] != "failed" for task in tasks)


def test_upload_docx_converts_with_assets_and_provenance(client, monkeypatch):
    headers = register(client, "docx-owner")
    kb = create_kb(client, headers, "docx-kb")
    path = Path(kb["local_path"])
    _use_stub_converter(client)
    monkeypatch.setattr(gitops, "has_git_lfs", lambda: True)
    monkeypatch.setattr(gitops, "ensure_lfs", lambda _path: True)
    data = b"PK\x03\x04docx-binary"

    response = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("report.docx", data, DOCX_MIME))],
        headers=headers,
    )
    assert response.status_code == 201, response.text
    task = _wait_import(client, headers, kb["id"], response.json()["id"])
    assert task["total"] == 1 and task["added"] == 1

    mr = _wait_review(client, headers, kb["id"])
    raw = Concept.from_text(_branch_show(path, mr["branch"], "raw/upload/report.docx.md"))
    frontmatter = raw.frontmatter
    assert frontmatter["title"] == "Converted"
    assert frontmatter["x-source-format"] == "docx"
    assert frontmatter["x-original-name"] == "report.docx"
    assert frontmatter["x-original-sha256"] == hashlib.sha256(data).hexdigest()
    assert frontmatter["x-original-size"] == len(data)
    assert frontmatter["x-parsed-by"] == "stub@1"
    assert str(frontmatter["resource"]).startswith("upload://")
    assert "report.docx.assets/" in raw.body

    asset_name = raw.body.split("report.docx.assets/", 1)[1].split(")", 1)[0]
    files = _branch_files(path, mr["branch"])
    assert f"raw/upload/report.docx.assets/{asset_name}" in files
    assert not any(name.endswith("report.docx") for name in files)

    _approve_mr(client, headers, kb["id"], mr["item_id"])
    asset = path / "raw" / "upload" / "report.docx.assets" / asset_name
    assert asset.read_bytes() == PNG
    assert not (client.app.state.settings.tmp_root / task["id"]).exists()


def test_docx_without_parser_is_partial_and_keeps_markdown(client):
    headers = register(client, "no-parser-owner")
    kb = create_kb(client, headers, "no-parser-kb")
    path = Path(kb["local_path"])

    response = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[
            ("files", ("note.md", b"# Note", "text/markdown")),
            ("files", ("report.docx", b"PK\x03\x04binary", DOCX_MIME)),
        ],
        headers=headers,
    )
    task = _wait_import(client, headers, kb["id"], response.json()["id"])
    assert task["status"] == "partial", task
    assert task["added"] == 1 and task["failed"] == 1
    assert "not configured" in (task["error"] or "")

    mr = _wait_review(client, headers, kb["id"])
    assert mr["concept_id"] == "raw/upload/note"
    files = _branch_files(path, mr["branch"])
    assert "raw/upload/note.md" in files
    assert not any("report.docx" in name for name in files)


def test_unavailable_parser_fails_task_without_half_written_docx(client):
    headers = register(client, "unavailable-owner")
    kb = create_kb(client, headers, "unavailable-kb")
    _use_stub_converter(client, fail_unavailable=True)

    response = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[
            ("files", ("a.md", b"# A", "text/markdown")),
            ("files", ("b.docx", b"PK\x03\x04binary", DOCX_MIME)),
        ],
        headers=headers,
    )
    task = _wait_import(client, headers, kb["id"], response.json()["id"])
    assert task["status"] == "failed", task
    assert "unavailable" in (task["error"] or "")
    assert client.get(f"/kbs/{kb['id']}/review/mrs", headers=headers).json()["mrs"] == []


def test_zip_with_mixed_markdown_and_docx_entries(client, monkeypatch):
    headers = register(client, "mixed-zip-owner")
    kb = create_kb(client, headers, "mixed-zip-kb")
    path = Path(kb["local_path"])
    _use_stub_converter(client)
    monkeypatch.setattr(gitops, "has_git_lfs", lambda: True)
    monkeypatch.setattr(gitops, "ensure_lfs", lambda _path: True)
    archive = _zip_entries(
        {
            "docs/a.md": b"# A\n\nmarkdown",
            "docs/b.docx": b"PK\x03\x04binary",
        }
    )

    response = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("docs.zip", archive, "application/zip"))],
        headers=headers,
    )
    task = _wait_import(client, headers, kb["id"], response.json()["id"])
    assert task["total"] == 2 and task["added"] == 2 and task["failed"] == 0

    _approve_all(client, headers, kb["id"])
    bundle = Bundle(path)
    assert bundle.path_for_id("raw/upload/docs/a").exists()
    assert bundle.path_for_id("raw/upload/docs/b.docx").exists()
    assert (path / "raw" / "upload" / "docs" / "b.docx.assets").is_dir()


def test_asset_quota_failure_keeps_existing_content(client, monkeypatch):
    headers = register(client, "quota-owner")
    kb = create_kb(client, headers, "quota-kb")
    path = Path(kb["local_path"])
    _use_stub_converter(client)
    monkeypatch.setattr(gitops, "has_git_lfs", lambda: True)
    monkeypatch.setattr(gitops, "ensure_lfs", lambda _path: True)
    settings = client.app.state.settings
    client.app.state.settings = settings.__class__(
        **{**settings.__dict__, "kb_asset_quota_bytes": 1}
    )

    response = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("report.docx", b"PK\x03\x04binary", DOCX_MIME))],
        headers=headers,
    )
    task = _wait_import(client, headers, kb["id"], response.json()["id"])
    assert task["failed"] == 1 and task["added"] == 0
    assert "quota" in (task["error"] or "")
    assert client.get(f"/kbs/{kb['id']}/review/mrs", headers=headers).json()["mrs"] == []

    bundle = Bundle(path)
    assert not bundle.path_for_id("raw/upload/report.docx").exists()
    assert not (path / "raw" / "upload" / "report.docx.assets").exists()


@pytest.mark.skipif(not gitops.has_git_lfs(), reason="git-lfs is not installed")
def test_docx_assets_are_committed_as_lfs_pointers(client):
    headers = register(client, "lfs-owner")
    kb = create_kb(client, headers, "lfs-kb")
    path = Path(kb["local_path"])
    _use_stub_converter(client)

    response = client.post(
        f"/kbs/{kb['id']}/import-tasks",
        files=[("files", ("report.docx", b"PK\x03\x04binary", DOCX_MIME))],
        headers=headers,
    )
    _wait_import(client, headers, kb["id"], response.json()["id"])
    mr = _wait_review(client, headers, kb["id"])
    raw = Concept.from_text(_branch_show(path, mr["branch"], "raw/upload/report.docx.md"))
    asset_name = raw.body.split("report.docx.assets/", 1)[1].split(")", 1)[0]
    relative = f"raw/upload/report.docx.assets/{asset_name}"

    _approve_mr(client, headers, kb["id"], mr["item_id"])
    assert (path / relative).read_bytes() == PNG

    attributes = (path / ".gitattributes").read_text(encoding="utf-8")
    assert "*.png filter=lfs diff=lfs merge=lfs -text" in attributes
    blob = _git(path, "show", f"HEAD:{relative}")
    assert blob.startswith("version https://git-lfs.github.com/spec/v1")
    lfs_files = _git(path, "lfs", "ls-files")
    assert relative in lfs_files
