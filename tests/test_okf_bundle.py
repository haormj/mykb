from __future__ import annotations

from mykb.okf.bundle import Bundle
from mykb.okf.model import Concept


def _bundle(tmp_path):
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout(title="Acme KB")
    return bundle


def test_ensure_layout_creates_levels_and_root_index(tmp_path):
    bundle = _bundle(tmp_path)
    for level in ("raw", "knowledge", "evals"):
        assert (bundle.root / level).is_dir()
        assert (bundle.root / level / "index.md").exists()
    frontmatter, _ = bundle.root_index()
    assert frontmatter["okf_version"] == "0.3"
    assert frontmatter["title"] == "Acme KB"
    assert "version" in frontmatter


def test_write_and_read_concept_roundtrip(tmp_path):
    bundle = _bundle(tmp_path)
    concept = Concept(frontmatter={"type": "源数据", "resource": "https://x/doc"}, body="body")
    cid = bundle.write_concept(concept, "raw", "confluence/doc")
    assert cid == "raw/confluence/doc"
    assert (bundle.root / "raw" / "confluence" / "doc.md").exists()

    loaded = bundle.read_concept(cid)
    assert loaded.id == cid
    assert loaded.type == "源数据"
    assert loaded.resource == "https://x/doc"


def test_iter_concepts_skips_reserved_and_other_levels(tmp_path):
    bundle = _bundle(tmp_path)
    bundle.write_concept(Concept(frontmatter={"type": "源数据"}), "raw", "a")
    bundle.write_concept(Concept(frontmatter={"type": "业务知识"}), "knowledge", "b")
    (bundle.root / "raw" / "log.md").write_text("log\n", encoding="utf-8")

    raw_ids = [cid for cid, _ in bundle.iter_concepts("raw")]
    assert raw_ids == ["raw/a"]

    all_ids = sorted(cid for cid, _ in bundle.iter_concepts())
    assert all_ids == ["knowledge/b", "raw/a"]
