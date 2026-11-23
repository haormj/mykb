from __future__ import annotations

from mykb.connectors.markdown_dir import MarkdownDirConnector
from mykb.connectors.sync import Importer
from mykb.evaluation.runner import EvalRunner
from mykb.evaluation.types import CaseData
from mykb.extraction.drafter import Drafter
from mykb.extraction.llm import FakeLLM
from mykb.extraction.review import GitReview
from mykb.maintenance.lifecycle import mark_needs_review, re_draft
from mykb.maintenance.lineage_trace import trace_affected
from mykb.maintenance.staleness import detect_stale_sources
from mykb.okf.bundle import Bundle
from mykb.retrieval.engines.markdown_rag import LocalMarkdownRAG
from mykb.retrieval.interface import RetrievalService
from mykb.retrieval.sync import IndexSync


def test_full_knowledge_lifecycle_loop(tmp_path):
    # 1. Import a markdown source into the raw layer.
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "ltv.md").write_text("# LTV\n\n90 day LTV is computed per customer.\n", encoding="utf-8")

    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout()
    Importer(bundle, MarkdownDirConnector(source_dir, base_uri="https://wiki")).run()

    source_id = "raw/markdown-dir/ltv"
    assert bundle.read_concept(source_id).generated["by"] == "process:markdown-dir"

    # 2. AI drafts business knowledge from it.
    drafter = Drafter(bundle, FakeLLM())
    draft_id = drafter.draft_to_bundle([source_id], relative_path="finance/ltv", title="LTV 业务知识")
    assert bundle.read_concept(draft_id).status == "draft"

    # 3. Human review merges and stamps verified.
    GitReview(bundle).approve_draft(draft_id, reviewer="alice")
    assert bundle.read_concept(draft_id).is_verified_stable()

    # 4. Versioned sync into the retrieval engine.
    engine = LocalMarkdownRAG()
    IndexSync(bundle, [engine]).sync()
    service = RetrievalService(knowledge_engine=engine)
    assert service.search("ltv").hits

    # 5. Run eval cases (A = knowledge quality, B = end-to-end).
    result = EvalRunner(bundle, service).run(
        [
            CaseData(
                question="ltv",
                reference_answer="90 day LTV per customer",
                expected_concept=draft_id,
                domain="finance",
                difficulty="easy",
            )
        ]
    )
    assert result.a_score == 1.0
    assert 0.0 <= result.b_score <= 1.0

    # 6. A source goes stale -> trace dependents -> mark needs-review.
    source = bundle.read_concept(source_id)
    source.frontmatter["stale_after"] = "2000-01-01T00:00:00Z"
    bundle.save_concept(source)

    stale = {item.concept_id for item in detect_stale_sources(bundle)}
    assert source_id in stale
    affected = trace_affected(bundle, source_id)
    assert draft_id in affected
    mark_needs_review(bundle, affected, reason="source stale")
    assert bundle.read_concept(draft_id).status == "needs-review"

    # 8. Re-extract a fresh draft from the same sources.
    new_draft = re_draft(bundle, draft_id, drafter)
    assert bundle.read_concept(new_draft).status == "draft"
