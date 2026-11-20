"""Build a retrieval service from environment configuration."""

from __future__ import annotations

import os
from pathlib import Path

from ..okf.bundle import Bundle
from .engines.codegraph import LocalCodeGraph
from .engines.markdown_rag import LocalMarkdownRAG, WeKnoraAdapter
from .interface import RetrievalEngine, RetrievalService
from .sync import IndexSync


def build_default_engines() -> tuple[RetrievalEngine, RetrievalEngine]:
    """Knowledge engine (WeKnora when configured, else local) + local codegraph."""
    url = os.environ.get("MYKB_WEKNORA_URL")
    knowledge: RetrievalEngine
    if url:
        knowledge = WeKnoraAdapter(base_url=url, api_key=os.environ.get("MYKB_WEKNORA_KEY"))
    else:
        knowledge = LocalMarkdownRAG()
    return knowledge, LocalCodeGraph()


def build_retrieval_service(
    bundle_root: str | Path, *, sync: bool = True
) -> RetrievalService:
    bundle = Bundle(Path(bundle_root))
    knowledge, code = build_default_engines()
    if sync:
        IndexSync(bundle, [knowledge], code_engine=code).sync()
    return RetrievalService(knowledge_engine=knowledge, code_engine=code)
