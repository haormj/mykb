from __future__ import annotations

import datetime as dt

import pytest

from mykb.okf.model import Concept, FrontmatterError, parse, serialize


def test_roundtrip_preserves_unknown_and_ordering():
    text = (
        "---\n"
        "type: Playbook\n"
        "title: Incident\n"
        "x-acme-owner: team-a\n"
        "tags:\n"
        "  - oncall\n"
        "---\n"
        "# Steps\n\nDo the thing.\n"
    )
    frontmatter, body = parse(text)
    assert frontmatter["type"] == "Playbook"
    assert frontmatter["x-acme-owner"] == "team-a"
    assert body.startswith("# Steps")

    rendered = serialize(frontmatter, body)
    frontmatter2, body2 = parse(rendered)
    assert frontmatter2 == frontmatter
    assert body2 == body


def test_missing_frontmatter_raises():
    with pytest.raises(FrontmatterError):
        parse("# just a heading\n")


def test_unterminated_frontmatter_raises():
    with pytest.raises(FrontmatterError):
        parse("---\ntype: X\n# no closing\n")


def test_datetime_normalized_to_string():
    frontmatter, _ = parse("---\ntype: Metric\nstale_after: 2026-12-31\n---\n")
    assert frontmatter["stale_after"] == "2026-12-31"
    assert isinstance(frontmatter["stale_after"], str)


def test_concept_properties_and_verified_stable():
    concept = Concept(
        frontmatter={
            "type": "业务知识",
            "status": "stable",
            "verified": [{"by": "human:alice", "at": "2026-01-01T00:00:00Z"}],
            "sources": [{"id": "raw/a", "resource": "https://x/a"}],
            "generated": {"by": "ai:gpt", "at": "2026-01-01T00:00:00Z"},
        },
        body="hello",
        id="knowledge/thing",
    )
    assert concept.type == "业务知识"
    assert concept.is_verified_stable()
    assert concept.source_ids() == ["raw/a"]
    assert concept.generated["by"] == "ai:gpt"


def test_concept_without_verified_is_not_stable():
    concept = Concept(frontmatter={"type": "业务知识", "status": "draft"}, body="x")
    assert not concept.is_verified_stable()


def test_iso_datetime_object_serializes_as_string():
    fm = {"type": "Metric", "completed": dt.date(2026, 1, 2)}
    rendered = serialize(fm, "")
    assert "completed: '2026-01-02'" in rendered or "completed: 2026-01-02" in rendered
