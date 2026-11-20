from __future__ import annotations

from pathlib import Path

from mykb.connectors import create_connector, list_connectors
from mykb.connectors.base import Connector
from mykb.connectors.markdown_dir import MarkdownDirConnector
from mykb.connectors.sync import Importer
from mykb.okf.bundle import Bundle


def _write_source(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "a.md").write_text("# Alpha\n\nAlpha content\n", encoding="utf-8")
    (src / "sub" / "b.md").write_text("---\ntitle: Beta\n---\nBeta content\n", encoding="utf-8")
    return src


def test_registry_discovers_markdown_connector():
    assert "markdown-dir" in list_connectors()
    connector = create_connector("markdown-dir", source_dir=".")
    assert isinstance(connector, MarkdownDirConnector)
    assert isinstance(connector, Connector)


def test_markdown_connector_sync_and_normalize(tmp_path):
    src = _write_source(tmp_path)
    connector = MarkdownDirConnector(src)
    items = connector.sync()
    assert {i.key for i in items} == {"a.md", "sub/b.md"}

    concepts = connector.normalize(items)
    by_title = {c.frontmatter["title"]: c for c in concepts}
    assert by_title["a"].type == "源数据"
    assert by_title["a"].generated["by"].startswith("process:")
    assert by_title["a"].resource
    assert by_title["Beta"].type == "源数据"


def test_importer_writes_source_concepts_to_raw(tmp_path):
    src = _write_source(tmp_path)
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout()
    connector = MarkdownDirConnector(src, base_uri="https://wiki.example.com")
    result = Importer(bundle, connector).run()

    assert sorted(result.added) == ["raw/markdown-dir/a", "raw/markdown-dir/sub/b"]
    concept = bundle.read_concept("raw/markdown-dir/a")
    assert concept.type == "源数据"
    assert concept.status == "draft"
    assert concept.resource == "https://wiki.example.com/a.md"
    assert concept.generated["by"] == "process:markdown-dir"


def test_incremental_sync_skips_unchanged_and_updates_changed(tmp_path):
    src = _write_source(tmp_path)
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout()
    connector = MarkdownDirConnector(src)
    importer = Importer(bundle, connector)

    first = importer.run()
    assert len(first.added) == 2

    second = importer.run()
    assert second.added == []
    assert second.updated == []
    assert len(second.skipped) == 2

    (src / "a.md").write_text("# Alpha\n\nChanged content\n", encoding="utf-8")
    third = importer.run()
    assert third.added == []
    assert third.updated == ["raw/markdown-dir/a"]
    assert "Changed content" in bundle.read_concept("raw/markdown-dir/a").body
