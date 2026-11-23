"""Single-flight document-level extraction pipeline.

Each source document becomes one review branch (``change/doc-...``) holding the
raw concept plus the business-knowledge changes it causes. Only one branch is
open per knowledge base; the next document is processed after the previous MR is
merged or rejected.
"""

from __future__ import annotations

import threading
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..db.models import ExtractionItem, ImportTask, KnowledgeBase
from ..kb import gitops
from ..kb.service import remote_credential
from ..maintenance.lineage_trace import trace_affected
from ..okf.bundle import Bundle
from .drafter import Drafter
from .harness import (
    ExtractionValidationError,
    apply_concept,
    claims_of,
    revise_for_removed_source,
    stable_relative_path,
    validate_concept,
)
from .llm import LLMClient, get_default_llm
from .queue import (
    ACTION_DELETE,
    STATUS_FAILED,
    STATUS_MERGED,
    STATUS_QUEUED,
    STATUS_REJECTED,
    STATUS_REVIEWING,
    claim_next,
    has_open_review,
    mark_item,
    refresh_import_task_status,
)
from .review import stamp_verified
from .staging import cleanup_staged, load_staged, write_raw_concept


class PipelineError(RuntimeError):
    """A user-facing extraction pipeline error."""


def _lock_for(kb_id: str, locks: dict[str, threading.Lock] | None, guard) -> threading.Lock:
    if locks is None:
        return threading.Lock()
    with guard:
        lock = locks.get(kb_id)
        if lock is None:
            lock = threading.Lock()
            locks[kb_id] = lock
        return lock


def _affected_knowledge(bundle: Bundle, source_id: str) -> list[str]:
    affected: set[str] = set(trace_affected(bundle, source_id))
    for concept_id, concept in bundle.iter_concepts("knowledge"):
        if source_id in concept.source_ids() or any(source_id in claim["sources"] for claim in claims_of(concept)):
            affected.add(concept_id)
    return sorted(affected)


def _extract_knowledge(bundle: Bundle, item: ExtractionItem, drafter: Drafter) -> None:
    source_id = item.concept_id
    affected = _affected_knowledge(bundle, source_id)
    if affected:
        for page_id in affected:
            page = bundle.read_concept(page_id)
            source_ids = page.source_ids() or [source_id]
            concept = drafter.propose_concept(
                source_ids, title=page.title, task_id=item.id
            )
            if page.verified:
                concept.frontmatter["verified"] = list(page.verified)
            concept.frontmatter["status"] = "draft"
            issues = validate_concept(
                concept, bundle, allowed_source_ids=source_ids, target_id=page_id
            )
            if issues:
                raise ExtractionValidationError(f"{page_id}: {'; '.join(issues)}")
            relative = page_id.split("/", 1)[1]
            apply_concept(bundle, concept, "knowledge", relative)
        return

    concept = drafter.propose_concept([source_id], task_id=item.id)
    target = stable_relative_path(concept.title or source_id)
    concept_id = bundle.concept_id(f"knowledge/{target}")
    issues = validate_concept(
        concept, bundle, allowed_source_ids=[source_id], target_id=concept_id
    )
    if issues:
        raise ExtractionValidationError("; ".join(issues))
    apply_concept(bundle, concept, "knowledge", target)


def _delete_and_revise(bundle: Bundle, item: ExtractionItem) -> None:
    source_id = item.concept_id
    affected = _affected_knowledge(bundle, source_id)
    bundle.path_for_id(source_id).unlink(missing_ok=True)
    tail = source_id.split("/", 1)[1] if "/" in source_id else source_id
    bundle.remove_assets("raw", tail)
    for page_id in affected:
        page = bundle.read_concept(page_id)
        revised = revise_for_removed_source(page, source_id)
        if revised is None:
            bundle.path_for_id(page_id).unlink(missing_ok=True)
        else:
            bundle.save_concept(revised)


def _branch_name(item: ExtractionItem) -> str:
    slug = item.concept_id.replace("/", "-").replace(".", "-")
    return f"change/doc-{slug}-{item.id[:8]}"


def _build_branch(
    bundle: Bundle, item: ExtractionItem, settings: Settings, drafter: Drafter
) -> str | None:
    root = bundle.root
    branch = _branch_name(item)
    gitops.checkout_new_branch(root, branch, base="main")
    if item.action == ACTION_DELETE:
        _delete_and_revise(bundle, item)
    else:
        concept, assets = load_staged(settings, item.id)
        write_raw_concept(bundle, concept_id=item.concept_id, concept=concept, assets=assets)
        _extract_knowledge(bundle, item, drafter)

    gitops.commit_all(root, f"{item.action}: {item.concept_id}")
    changed = bool(gitops.changed_files_vs(root, "main", branch))
    if changed:
        gitops.checkout(root, "main")
        return branch
    gitops.delete_branch(root, branch)
    return None


def process_pending(
    kb_id: str,
    *,
    session_factory: sessionmaker[Session],
    settings: Settings,
    llm: LLMClient | None = None,
    locks: dict[str, threading.Lock] | None = None,
    guard: threading.Lock | None = None,
    cache=None,
) -> str | None:
    """Build at most one document-level MR for a KB, respecting single-flight."""
    if not settings.extraction_enabled:
        return None
    lock = _lock_for(kb_id, locks, guard or threading.Lock())
    with lock:
        session = session_factory()
        try:
            kb = session.get(KnowledgeBase, kb_id)
            if kb is None:
                return None
            bundle = Bundle(Path(kb.local_path))
            drafter = Drafter(bundle, llm or get_default_llm())
            while True:
                session.expire_all()
                if has_open_review(session, kb_id):
                    return None
                item = claim_next(session, kb_id)
                if item is None:
                    return None
                parent = session.get(ImportTask, item.import_task_id) if item.import_task_id else None
                if parent is not None and parent.status == "cancelled":
                    cleanup_staged(settings, item.id)
                    mark_item(session, item, STATUS_REJECTED)
                    continue
                try:
                    branch = _build_branch(bundle, item, settings, drafter)
                except Exception as exc:  # noqa: BLE001 - record and continue queue
                    _recover_to_main(bundle)
                    mark_item(session, item, STATUS_FAILED, error=str(exc)[:2048])
                    refresh_import_task_status(session, item.import_task_id)
                    continue
                if branch is None:
                    cleanup_staged(settings, item.id)
                    mark_item(session, item, STATUS_MERGED)
                    refresh_import_task_status(session, item.import_task_id)
                    continue
                mark_item(session, item, STATUS_REVIEWING, branch=branch)
                refresh_import_task_status(session, item.import_task_id)
                return item.id
        finally:
            session.close()


def _recover_to_main(bundle: Bundle) -> None:
    try:
        gitops.force_checkout(bundle.root, "main")
        gitops.reset_hard(bundle.root)
    except Exception:  # noqa: BLE001 - best-effort recovery
        return


def approve_item(
    item_id: str,
    *,
    session_factory: sessionmaker[Session],
    settings: Settings,
    reviewer: str,
    llm: LLMClient | None = None,
    locks: dict[str, threading.Lock] | None = None,
    guard: threading.Lock | None = None,
    cache=None,
) -> dict:
    session = session_factory()
    try:
        item = session.get(ExtractionItem, item_id)
        if item is None:
            raise PipelineError("review item not found")
        if item.status != STATUS_REVIEWING or not item.branch:
            raise PipelineError(f"review item is {item.status}, not reviewable")
        kb = session.get(KnowledgeBase, item.kb_id)
        if kb is None:
            raise PipelineError("knowledge base not found")
        bundle = Bundle(Path(kb.local_path))
        branch = item.branch
        changed = gitops.changed_files_vs(bundle.root, "main", branch)
        gitops.merge_branch(bundle.root, branch, f"merge {branch}")
        stamped = 0
        for relative in changed:
            if not (relative.startswith("knowledge/") and relative.endswith(".md")):
                continue
            concept_id = bundle.concept_id(relative)
            if not bundle.path_for_id(concept_id).exists():
                continue
            concept = bundle.read_concept(concept_id)
            bundle.save_concept(stamp_verified(concept, reviewer=reviewer))
            stamped += 1
        if stamped:
            gitops.commit_all(bundle.root, f"ci: verify {branch} (human:{reviewer})")
        if kb.git_url:
            gitops.push(bundle.root, kb.git_branch, remote_credential(kb, settings))
        gitops.delete_branch(bundle.root, branch)
        cleanup_staged(settings, item.id)
        mark_item(session, item, STATUS_MERGED)
        refresh_import_task_status(session, item.import_task_id)
        kb_id = item.kb_id
        task_id = item.import_task_id
        if cache is not None:
            cache.invalidate(kb_id)
    finally:
        session.close()

    process_pending(
        kb_id,
        session_factory=session_factory,
        settings=settings,
        llm=llm,
        locks=locks,
        guard=guard,
        cache=cache,
    )
    return {"item_id": item_id, "status": STATUS_MERGED, "stamped": stamped, "task_id": task_id}


def reject_item(
    item_id: str,
    *,
    session_factory: sessionmaker[Session],
    settings: Settings,
    llm: LLMClient | None = None,
    locks: dict[str, threading.Lock] | None = None,
    guard: threading.Lock | None = None,
    cache=None,
) -> dict:
    session = session_factory()
    try:
        item = session.get(ExtractionItem, item_id)
        if item is None:
            raise PipelineError("review item not found")
        if item.status != STATUS_REVIEWING:
            raise PipelineError(f"review item is {item.status}, not reviewable")
        kb = session.get(KnowledgeBase, item.kb_id)
        if kb is not None and item.branch:
            bundle = Bundle(Path(kb.local_path))
            gitops.delete_branch(bundle.root, item.branch)
        cleanup_staged(settings, item.id)
        mark_item(session, item, STATUS_REJECTED)
        refresh_import_task_status(session, item.import_task_id)
        kb_id = item.kb_id
        task_id = item.import_task_id
    finally:
        session.close()

    process_pending(
        kb_id,
        session_factory=session_factory,
        settings=settings,
        llm=llm,
        locks=locks,
        guard=guard,
        cache=cache,
    )
    return {"item_id": item_id, "status": STATUS_REJECTED, "task_id": task_id}


def redraft_item(
    item_id: str,
    *,
    session_factory: sessionmaker[Session],
    settings: Settings,
    llm: LLMClient | None = None,
    locks: dict[str, threading.Lock] | None = None,
    guard: threading.Lock | None = None,
    cache=None,
) -> dict:
    """Accept raw, discard the knowledge draft and re-extract into the same MR."""
    session = session_factory()
    try:
        item = session.get(ExtractionItem, item_id)
        if item is None:
            raise PipelineError("review item not found")
        if item.status != STATUS_REVIEWING:
            raise PipelineError(f"review item is {item.status}, not reviewable")
        kb = session.get(KnowledgeBase, item.kb_id)
        if kb is not None and item.branch:
            bundle = Bundle(Path(kb.local_path))
            gitops.delete_branch(bundle.root, item.branch)
        mark_item(session, item, STATUS_QUEUED, branch=None)
        refresh_import_task_status(session, item.import_task_id)
        kb_id = item.kb_id
    finally:
        session.close()

    process_pending(
        kb_id,
        session_factory=session_factory,
        settings=settings,
        llm=llm,
        locks=locks,
        guard=guard,
        cache=cache,
    )
    return {"item_id": item_id, "status": STATUS_QUEUED, "kb_id": kb_id}


def concept_files_changed(bundle: Bundle, branch: str) -> list[str]:
    return gitops.changed_files_vs(bundle.root, "main", branch)
