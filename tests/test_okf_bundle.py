from __future__ import annotations

import os

import pytest

from mykb.okf.bundle import Bundle
from mykb.okf.model import Concept

PNG = b"\x89PNG\r\n\x1a\nfake-image"


def _bundle(tmp_path):
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout(title="Acme KB")
    return bundle


def test_ensure_layout_creates_levels_and_root_index(tmp_path):
    bundle = _bundle(tmp_path)
    for level in ("raw", "knowledge"):
        assert (bundle.root / level).is_dir()
        assert (bundle.root / level / "index.md").exists()
    assert not (bundle.root / "evals").exists()
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


def test_read_asset_returns_bytes_and_mime(tmp_path):
    bundle = _bundle(tmp_path)
    bundle.write_concept(Concept(frontmatter={"type": "源数据"}), "raw", "upload/report.docx")
    directory = bundle.asset_dir_for("raw", "upload/report.docx")
    directory.mkdir(parents=True)
    (directory / "001-abc.png").write_bytes(PNG)

    data, mime = bundle.read_asset("raw/upload/report.docx", "001-abc.png")

    assert data == PNG
    assert mime == "image/png"


def test_read_asset_rejects_unsafe_names(tmp_path):
    bundle = _bundle(tmp_path)
    bundle.write_concept(Concept(frontmatter={"type": "源数据"}), "raw", "upload/report.docx")
    bundle.asset_dir_for("raw", "upload/report.docx").mkdir(parents=True)
    (bundle.root / "raw" / "upload" / "secret.png").write_bytes(PNG)

    for name in ("../secret.png", "/etc/passwd", "..", ".", "", "sub/img.png", "a\\b.png"):
        with pytest.raises(ValueError):
            bundle.read_asset("raw/upload/report.docx", name)


def test_read_asset_rejects_cross_concept_reads(tmp_path):
    bundle = _bundle(tmp_path)
    bundle.write_concept(Concept(frontmatter={"type": "源数据"}), "raw", "upload/a")
    bundle.write_concept(Concept(frontmatter={"type": "源数据"}), "raw", "upload/b")
    bundle.asset_dir_for("raw", "upload/a").mkdir(parents=True)
    other = bundle.asset_dir_for("raw", "upload/b")
    other.mkdir(parents=True)
    (other / "only-b.png").write_bytes(PNG)

    with pytest.raises(FileNotFoundError):
        bundle.read_asset("raw/upload/a", "only-b.png")


def test_read_asset_rejects_symlink_escape(tmp_path):
    bundle = _bundle(tmp_path)
    bundle.write_concept(Concept(frontmatter={"type": "源数据"}), "raw", "upload/a")
    directory = bundle.asset_dir_for("raw", "upload/a")
    directory.mkdir(parents=True)
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG)
    os.symlink(outside, directory / "link.png")

    with pytest.raises(FileNotFoundError):
        bundle.read_asset("raw/upload/a", "link.png")


def test_read_asset_detects_lfs_pointer(tmp_path):
    bundle = _bundle(tmp_path)
    bundle.write_concept(Concept(frontmatter={"type": "源数据"}), "raw", "upload/a")
    directory = bundle.asset_dir_for("raw", "upload/a")
    directory.mkdir(parents=True)
    (directory / "pointer.png").write_bytes(
        b"version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 12\n"
    )

    with pytest.raises(FileNotFoundError):
        bundle.read_asset("raw/upload/a", "pointer.png")


def test_read_asset_requires_level_prefix(tmp_path):
    bundle = _bundle(tmp_path)

    with pytest.raises(ValueError):
        bundle.read_asset("upload/a", "x.png")
