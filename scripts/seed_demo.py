#!/usr/bin/env python3
"""Seed a demo OKF knowledge bundle.

The knowledge bundle is data and lives outside the code repo by default
(``~/.mykb/kb``). This script is idempotent: running it again reuses existing
business knowledge and only re-runs the eval.

Usage:
    python scripts/seed_demo.py [bundle_root]
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from mykb.connectors.markdown_dir import MarkdownDirConnector
from mykb.connectors.sync import Importer
from mykb.evaluation.evalset import EvalCase, EvalSetManager
from mykb.evaluation.runner import EvalRunner
from mykb.extraction.drafter import Drafter
from mykb.extraction.llm import FakeLLM
from mykb.extraction.review import GitReview
from mykb.okf.bundle import Bundle
from mykb.retrieval.service import build_retrieval_service


def main() -> int:
    root = (
        Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path.home() / ".mykb" / "kb"
    )
    bundle = Bundle(root)
    bundle.ensure_layout(title="mykb Demo KB")

    with tempfile.TemporaryDirectory() as tmp:
        source_dir = Path(tmp)
        (source_dir / "ltv.md").write_text(
            "# LTV\n\n90 day LTV 按客户聚合 90 天内订单金额。\n", encoding="utf-8"
        )
        (source_dir / "orders.md").write_text(
            "# Orders\n\norders 表一行一个已支付订单。\n", encoding="utf-8"
        )
        Importer(
            bundle, MarkdownDirConnector(source_dir, base_uri="https://wiki.example.com")
        ).run()

    drafter = Drafter(bundle, FakeLLM())
    reviewer = GitReview(bundle)

    def ensure_knowledge(source_id: str, relative_path: str, title: str) -> str:
        concept_id = f"knowledge/{relative_path}"
        if bundle.path_for_id(concept_id).exists():
            return concept_id
        draft_id = drafter.draft_to_bundle([source_id], relative_path=relative_path, title=title)
        reviewer.approve_draft(draft_id, reviewer="alice")
        return draft_id

    ltv_id = ensure_knowledge("raw/markdown-dir/ltv", "finance/ltv", "LTV 计算口径")
    orders_id = ensure_knowledge("raw/markdown-dir/orders", "sales/orders", "订单表说明")

    # Keep one un-approved draft so the review page has content.
    if not bundle.path_for_id("knowledge/finance/ltv-v2").exists():
        drafter.draft_to_bundle(
            ["raw/markdown-dir/ltv"],
            relative_path="finance/ltv-v2",
            title="LTV 口径（待审草稿）",
        )

    EvalSetManager(bundle).create(
        "finance-basics",
        [
            EvalCase(
                question="ltv 怎么算",
                reference_answer="90 day LTV 按客户聚合",
                expected_concept=ltv_id,
                domain="finance",
                difficulty="easy",
            ),
            EvalCase(
                question="orders 表",
                reference_answer="orders 表一行一个已支付订单",
                expected_concept=orders_id,
                domain="sales",
                difficulty="easy",
            ),
        ],
        title="财务基础",
    )

    run = EvalRunner(bundle, build_retrieval_service(root)).run("finance-basics")
    print(f"seeded {root}")
    print("  knowledge: finance/ltv, sales/orders; draft: finance/ltv-v2")
    print(f"  eval finance-basics: A={run.a_score:.3f} B={run.b_score:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
