"""Local upload ingestion and the database-backed import task worker."""

from __future__ import annotations

import io
import shutil
import threading
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..connectors.upload import UploadDirConnector
from ..conversion import (
    ConversionError,
    ConversionLimitError,
    ConversionUnavailableError,
    ConverterService,
)
from ..conversion.assets import rewrite_asset_links
from ..conversion.base import SUPPORTED_SUFFIXES, RawDocument
from ..conversion.service import (
    asset_quota_exceeded,
    concept_alias,
    concept_relative_path,
)
from ..db.models import ImportTask, KnowledgeBase
from ..kb import gitops
from ..kb.context import RetrievalCache
from ..kb.service import remote_credential
from ..okf.bundle import Bundle
from .concepts import build_source_concept

ALLOWED_EXTENSIONS = SUPPORTED_SUFFIXES | {".zip"}
ARCHIVE_EXTENSIONS = SUPPORTED_SUFFIXES


class UploadError(ValueError):
    """A user-facing upload validation error."""


def _now() -> datetime:
    return datetime.now(UTC)


def _safe_name(name: str) -> str:
    return Path(name.replace("\\", "/")).name.strip()


def safe_extract_zip(data: bytes, target: Path, settings: Settings) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UploadError("invalid zip archive") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > settings.upload_max_zip_entries:
            raise UploadError("zip archive has too many entries")
        actual_total = 0
        for info in infos:
            if info.is_dir():
                continue
            raw_name = info.filename.replace("\\", "/")
            parts = [part for part in raw_name.split("/") if part not in ("", ".")]
            if (
                not parts
                or raw_name.startswith("/")
                or any(part == ".." for part in parts)
                or ":" in parts[0]
            ):
                raise UploadError("zip archive contains an unsafe path")
            if Path(parts[-1]).suffix.lower() not in ARCHIVE_EXTENSIONS:
                continue
            destination = target.joinpath(*parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as output:
                while True:
                    chunk = source.read(64 * 1024)
                    if not chunk:
                        break
                    actual_total += len(chunk)
                    if actual_total > settings.upload_max_bytes:
                        raise UploadError("upload exceeds size limit")
                    output.write(chunk)


def prepare_upload(
    task_id: str, settings: Settings, files: list[tuple[str, bytes]]
) -> tuple[Path, dict[str, Any]]:
    """Stage uploaded files under the task temp directory; return its config."""
    if not files:
        raise UploadError("at least one file is required")

    target = settings.tmp_root / task_id
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)

    total_bytes = 0
    records: list[dict[str, Any]] = []
    try:
        for original_name, data in files:
            safe_name = _safe_name(original_name)
            if not safe_name:
                raise UploadError("file name is required")
            extension = Path(safe_name).suffix.lower()
            if extension not in ALLOWED_EXTENSIONS:
                allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
                raise UploadError(f"unsupported file type: {safe_name}; allowed: {allowed}")
            total_bytes += len(data)
            if total_bytes > settings.upload_max_bytes:
                raise UploadError("upload exceeds size limit")
            if extension == ".zip":
                safe_extract_zip(data, target, settings)
            else:
                (target / safe_name).write_bytes(data)
            records.append({"name": safe_name, "size": len(data)})
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return target, {"files": records, "total_bytes": total_bytes}


def _lock_for(kb_id: str, locks: dict[str, threading.Lock], guard: threading.Lock):
    with guard:
        lock = locks.get(kb_id)
        if lock is None:
            lock = threading.Lock()
            locks[kb_id] = lock
        return lock


def mark_stale_running_failed(factory: sessionmaker[Session]) -> int:
    """Mark tasks left running by a crash as failed; returns the number updated."""
    with factory() as session:
        result = session.execute(
            update(ImportTask)
            .where(ImportTask.status == "running")
            .values(
                status="failed",
                error="interrupted by service restart",
                finished_at=_now(),
            )
        )
        session.commit()
        return int(getattr(result, "rowcount", 0) or 0)


def task_payload(task: ImportTask) -> dict[str, Any]:
    def iso(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    return {
        "id": task.id,
        "kb_id": task.kb_id,
        "source_type": task.source_type,
        "status": task.status,
        "total": task.total,
        "added": task.added,
        "updated": task.updated,
        "skipped": task.skipped,
        "failed": task.failed,
        "error": task.error,
        "created_by": task.created_by,
        "created_at": iso(task.created_at),
        "started_at": iso(task.started_at),
        "finished_at": iso(task.finished_at),
    }


def _import_document(
    *,
    bundle: Bundle,
    document: RawDocument,
    connector: UploadDirConnector,
    converter: ConverterService,
    task: ImportTask,
    settings: Settings,
) -> bool:
    """Convert and write one document; return whether a concept already existed."""
    result = converter.convert(document)
    relative = concept_relative_path(document.key)
    alias = concept_alias(relative)
    result.markdown = rewrite_asset_links(result.markdown, result.assets, alias)

    if result.assets and not gitops.has_git_lfs():
        raise ConversionUnavailableError(
            "git-lfs is required to store converted image assets; install git-lfs first"
        )
    if result.assets and asset_quota_exceeded(
        bundle, result.assets, settings.kb_asset_quota_bytes
    ):
        raise ConversionLimitError("knowledge base asset quota exceeded")

    concept = build_source_concept(
        result=result,
        document=document,
        connector_name=connector.name,
        source_type=connector.source_type,
        resource=connector.resource_for(document.key),
        task_id=task.id,
    )
    concept_id = bundle.concept_id(f"raw/{connector.name}/{relative}")
    existed = bundle.path_for_id(concept_id).exists()

    level_relative = f"{connector.name}/{relative}"
    asset_dir = bundle.asset_dir_for("raw", level_relative)
    backup = asset_dir.with_name(f"{asset_dir.name}.bak")
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
    if asset_dir.exists():
        shutil.move(str(asset_dir), str(backup))
    try:
        if result.assets:
            bundle.write_assets("raw", level_relative, result.assets)
        bundle.write_concept(concept, "raw", level_relative)
    except Exception:
        shutil.rmtree(asset_dir, ignore_errors=True)
        if backup.exists():
            shutil.move(str(backup), str(asset_dir))
        raise
    else:
        shutil.rmtree(backup, ignore_errors=True)
    return existed


def run_import_task(
    task_id: str,
    *,
    session_factory: sessionmaker[Session],
    settings: Settings,
    cache: RetrievalCache,
    locks: dict[str, threading.Lock],
    lock_guard: threading.Lock,
    on_item: Callable[[ImportTask], None] | None = None,
    converter: ConverterService | None = None,
) -> None:
    """Execute one queued import task under the knowledge base's serial lock."""
    session = session_factory()
    temp_dir = settings.tmp_root / task_id
    converter = converter or ConverterService(settings)
    try:
        task = session.get(ImportTask, task_id)
        if task is None:
            return
        kb = session.get(KnowledgeBase, task.kb_id)
        if kb is None:
            task.status = "failed"
            task.error = "knowledge base no longer exists"
            task.finished_at = _now()
            session.commit()
            return

        lock = _lock_for(kb.id, locks, lock_guard)
        with lock:
            session.refresh(task)
            if task.status != "queued":
                return
            task.status = "running"
            task.started_at = _now()
            session.commit()

            bundle = Bundle(Path(kb.local_path))
            connector = UploadDirConnector(temp_dir, base_uri=f"upload://{task.id}")
            try:
                documents = connector.sync()
            except Exception as exc:  # unreadable staging directory
                raise RuntimeError(f"failed to read uploaded content: {exc}") from exc

            task.total = len(documents)
            session.commit()

            errors: list[str] = []
            fatal: Exception | None = None
            for document in documents:
                session.refresh(task)
                if task.status == "cancelled":
                    break
                if on_item is not None:
                    on_item(task)
                try:
                    existed = _import_document(
                        bundle=bundle,
                        document=document,
                        connector=connector,
                        converter=converter,
                        task=task,
                        settings=settings,
                    )
                    if existed:
                        task.updated += 1
                    else:
                        task.added += 1
                except ConversionUnavailableError as exc:
                    fatal = exc
                    break
                except ConversionError as exc:
                    task.failed += 1
                    errors.append(f"{document.key}: {exc}")
                except Exception as exc:  # noqa: BLE001 - count and continue per item
                    task.failed += 1
                    errors.append(f"{document.key}: {exc}")
                session.commit()

            if task.added or task.updated:
                gitops.commit_all(Path(kb.local_path), f"import: {task.id}")
                if kb.git_url:
                    gitops.push(Path(kb.local_path), kb.git_branch, remote_credential(kb, settings))

            session.refresh(task)
            if task.status != "cancelled":
                if fatal is not None:
                    task.status = "failed"
                    errors.append(str(fatal))
                else:
                    task.status = "partial" if task.failed else "succeeded"
            task.finished_at = _now()
            task.error = "\n".join(errors)[:2048] or None
            session.commit()
            cache.invalidate(kb.id)
    except Exception as exc:  # noqa: BLE001 - persist the failure on the task
        session.rollback()
        task = session.get(ImportTask, task_id)
        if task is not None:
            task.status = "failed"
            task.error = str(exc)[:2048]
            task.finished_at = _now()
            session.commit()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        session.close()
