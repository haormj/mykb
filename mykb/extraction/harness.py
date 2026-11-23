"""Extraction harness: constrain LLM output into stable OKF business knowledge.

The harness turns a structured extraction result into an OKF concept with a
deterministic identity, claim-level provenance and extraction metadata, then
validates it before anything is written.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any

from ..okf.bundle import Bundle
from ..okf.model import Concept
from ..util import now_iso

PROMPT_VERSION = "v1"
KNOWLEDGE_TYPE = "业务知识"

# Required body sections per knowledge type. Unknown types fall back to the
# generic template.
KNOWLEDGE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "业务知识": ("要点",),
    "术语": ("定义",),
    "流程": ("步骤",),
    "规则": ("规则",),
    "指标": ("口径",),
}


class ExtractionValidationError(ValueError):
    """Raised when a draft fails the pre-write validation gate."""


def slugify(text: str, *, fallback: str = "knowledge") -> str:
    normalized = unicodedata.normalize("NFKC", text.strip().lower())
    chars = [ch if ch.isalnum() or ch in "-_" else "-" for ch in normalized]
    slug = re.sub(r"-+", "-", "".join(chars)).strip("-")
    return slug[:120] or fallback


def stable_relative_path(topic: str) -> str:
    """Derive a deterministic knowledge path from a topic/entity key."""
    return f"topics/{slugify(topic)}"


def normalize_output(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce a raw LLM result into the extraction output shape."""
    if not isinstance(raw, dict):
        raise ExtractionValidationError("extraction output must be an object")
    title = str(raw.get("title") or "").strip()
    summary = str(raw.get("summary") or "").strip()
    tags = [str(tag) for tag in (raw.get("tags") or []) if str(tag).strip()]
    claims_raw = raw.get("claims") or []
    claims: list[dict[str, Any]] = []
    for item in claims_raw:
        if isinstance(item, str):
            text, sources = item, []
        elif isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            sources = [str(source) for source in (item.get("sources") or [])]
        else:
            continue
        if text:
            claims.append({"text": text, "sources": sources})
    conflicts = [
        dict(item) for item in (raw.get("conflicts") or []) if isinstance(item, dict)
    ]
    open_questions = [str(q) for q in (raw.get("open_questions") or []) if str(q).strip()]
    return {
        "title": title,
        "summary": summary,
        "tags": tags,
        "claims": claims,
        "conflicts": conflicts,
        "open_questions": open_questions,
    }


def render_body(output: dict[str, Any], title: str) -> str:
    lines = [f"# {title}", ""]
    summary = output.get("summary")
    if summary:
        lines += [str(summary), ""]
    claims = output.get("claims") or []
    if claims:
        lines.append("## 要点")
        for claim in claims:
            lines.append(f"- {claim['text']}")
        lines.append("")
    open_questions = output.get("open_questions") or []
    if open_questions:
        lines.append("## 待解问题")
        for question in open_questions:
            lines.append(f"- {question}")
        lines.append("")
    return "\n".join(lines)


def _source_entries(source_ids: list[str], source_meta: dict[str, dict[str, Any]]) -> list[dict]:
    entries: list[dict] = []
    for source_id in source_ids:
        meta = source_meta.get(source_id, {})
        entry: dict[str, Any] = {"id": source_id}
        if meta.get("resource"):
            entry["resource"] = meta["resource"]
        if meta.get("title"):
            entry["title"] = meta["title"]
        entries.append(entry)
    return entries


def build_concept(
    output: dict[str, Any],
    *,
    source_ids: list[str],
    source_meta: dict[str, dict[str, Any]],
    model: str,
    source_hash: str,
    task_id: str | None = None,
    title: str | None = None,
    concept_type: str = KNOWLEDGE_TYPE,
) -> Concept:
    """Build an OKF business-knowledge concept from structured output."""
    resolved_title = (title or output.get("title") or "业务知识").strip() or "业务知识"
    claims = [dict(claim) for claim in output.get("claims") or []]
    aggregate: list[str] = []
    for source_id in source_ids:
        if source_id not in aggregate:
            aggregate.append(source_id)
    for claim in claims:
        for source_id in claim.get("sources") or []:
            if source_id not in aggregate:
                aggregate.append(source_id)

    frontmatter: dict[str, Any] = {
        "type": concept_type,
        "title": resolved_title,
        "generated": {"by": f"ai:{model}", "at": now_iso()},
        "status": "draft",
        "tags": list(output.get("tags") or []),
        "sources": _source_entries(aggregate, source_meta),
        "claims": claims,
        "x-extraction": {
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "source_hash": source_hash,
            "task": task_id,
        },
    }
    if output.get("conflicts"):
        frontmatter["x-conflicts"] = list(output["conflicts"])
    if output.get("open_questions"):
        frontmatter["x-open-questions"] = list(output["open_questions"])
    return Concept(frontmatter=frontmatter, body=render_body(output, resolved_title))


def claims_of(concept: Concept) -> list[dict[str, Any]]:
    claims = concept.frontmatter.get("claims")
    if not isinstance(claims, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in claims:
        if isinstance(item, dict) and item.get("text"):
            normalized.append(
                {"text": str(item["text"]), "sources": [str(s) for s in item.get("sources") or []]}
            )
    return normalized


def semantic_signature(concept: Concept) -> tuple:
    """Stable signature ignoring timestamps/model for idempotent merging."""
    tags = tuple(str(tag) for tag in (concept.frontmatter.get("tags") or []))
    claims = tuple((claim["text"], tuple(claim["sources"])) for claim in claims_of(concept))
    return (concept.title, tags, claims, concept.body.strip())


def validate_concept(
    concept: Concept,
    bundle: Bundle,
    *,
    allowed_source_ids: list[str] | None = None,
    target_id: str | None = None,
) -> list[str]:
    """Return pre-write validation issues (empty list means valid)."""
    issues: list[str] = []
    if concept.type != KNOWLEDGE_TYPE:
        issues.append(f"type must be '{KNOWLEDGE_TYPE}', got {concept.type!r}")
    if not (concept.title or "").strip():
        issues.append("title is required")
    known_sources = set(allowed_source_ids or [])
    known_sources.update(cid for cid, _ in bundle.iter_concepts("raw"))
    claims = claims_of(concept)
    if not claims:
        issues.append("at least one claim is required")
    for claim in claims:
        if not claim["sources"]:
            issues.append(f"claim has no sources: {claim['text'][:40]!r}")
            continue
        for source_id in claim["sources"]:
            if source_id not in known_sources:
                issues.append(f"claim cites unknown source: {source_id}")
    for link in re.findall(r"\]\(([^)\s]+)\)", concept.body):
        if link.endswith(".md") and not link.startswith(("http://", "https://")):
            target = bundle.root / link
            if not target.exists():
                issues.append(f"broken link in body: {link}")
    if target_id:
        for concept_id, other in bundle.iter_concepts("knowledge"):
            if concept_id != target_id and other.title == concept.title:
                issues.append(f"duplicate knowledge entity title: {concept.title!r}")
                break
    return issues


def apply_concept(
    bundle: Bundle, concept: Concept, level: str, relative_path: str
) -> tuple[str, bool]:
    """Write a concept idempotently; return ``(concept_id, changed)``."""
    tail = relative_path.replace("\\", "/").lstrip("/").removesuffix(".md")
    concept_id = bundle.concept_id(f"{level}/{tail}")
    path = bundle.path_for_id(concept_id)
    if path.exists():
        existing = Concept.from_file(path, id=concept_id)
        if semantic_signature(existing) == semantic_signature(concept):
            concept.id = concept_id
            return concept_id, False
    bundle.write_concept(concept, level, relative_path)
    return concept_id, True


def revise_for_removed_source(concept: Concept, removed_source_id: str) -> Concept | None:
    """Drop claims citing a removed source.

    Returns ``None`` when no claim survives (the whole page loses its evidence),
    otherwise a copy with the surviving claims and a recomputed source list.
    """
    claims = claims_of(concept)
    survivors = [c for c in claims if removed_source_id not in c["sources"]]
    if not survivors:
        return None
    frontmatter = dict(concept.frontmatter)
    frontmatter["claims"] = survivors
    sources = list(frontmatter.get("sources") or [])
    frontmatter["sources"] = [
        entry
        for entry in sources
        if (entry.get("id") if isinstance(entry, dict) else entry) != removed_source_id
    ]
    frontmatter["status"] = "needs-review"
    body_lines = ["## 要点"] + [f"- {claim['text']}" for claim in survivors]
    frontmatter_body = concept.body.split("## 要点", 1)
    body = frontmatter_body[0].rstrip() + "\n\n" + "\n".join(body_lines) + "\n"
    return Concept(frontmatter=frontmatter, body=body, id=concept.id)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
