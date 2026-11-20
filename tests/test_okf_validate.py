from __future__ import annotations

from mykb.okf.bundle import Bundle
from mykb.okf.validate import validate_bundle


def test_valid_bundle_has_no_issues(tmp_path):
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout()
    (bundle.root / "raw" / "ok.md").write_text("---\ntype: 源数据\n---\nhi\n", encoding="utf-8")
    assert validate_bundle(bundle.root) == []


def test_missing_type_is_reported(tmp_path):
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout()
    (bundle.root / "raw" / "bad.md").write_text("---\ntitle: no type\n---\n", encoding="utf-8")
    issues = validate_bundle(bundle.root)
    assert len(issues) == 1
    assert issues[0].path == "raw/bad.md"
    assert "type" in issues[0].reason


def test_missing_frontmatter_is_reported(tmp_path):
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout()
    (bundle.root / "knowledge" / "bad.md").write_text("# no frontmatter\n", encoding="utf-8")
    issues = validate_bundle(bundle.root)
    assert any(i.path == "knowledge/bad.md" and "frontmatter" in i.reason for i in issues)


def test_unknown_extension_fields_are_allowed(tmp_path):
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout()
    (bundle.root / "raw" / "ext.md").write_text(
        "---\ntype: 源数据\nx-acme-owner: team\n---\n", encoding="utf-8"
    )
    assert validate_bundle(bundle.root) == []
