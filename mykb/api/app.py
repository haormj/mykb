"""FastAPI application factory.

Routes are registered incrementally by capability modules. The factory accepts a
bundle root so tests and the CLI can point the app at a temporary bundle.
"""

from __future__ import annotations

import difflib
import os
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from ..evaluation.evalset import EvalCase, EvalSetManager
from ..evaluation.runner import EvalRunner
from ..evaluation.scoreboard import Scoreboard
from ..extraction.review import GitReview
from ..okf.bundle import Bundle
from ..retrieval.interface import RetrievalService
from ..retrieval.service import build_retrieval_service


def default_bundle_root() -> Path:
    """Knowledge bundle lives outside the code repo by default (data, not code)."""
    configured = os.environ.get("MYKB_BUNDLE_ROOT")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".mykb" / "kb"


class EvalCaseIn(BaseModel):
    question: str
    reference_answer: str
    expected_concept: str | None = None
    domain: str | None = None
    difficulty: str | None = None


class EvalSetIn(BaseModel):
    name: str
    title: str | None = None
    cases: list[EvalCaseIn]


def create_app(bundle_root: str | Path | None = None) -> FastAPI:
    app = FastAPI(title="mykb", version="0.1.0")
    root = Path(bundle_root) if bundle_root is not None else default_bundle_root()
    app.state.bundle_root = root
    app.state.retrieval_service = None

    def service() -> RetrievalService:
        if app.state.retrieval_service is None:
            app.state.retrieval_service = build_retrieval_service(root)
        return app.state.retrieval_service

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "bundle_root": str(root)}

    @app.get("/retrieve")
    def retrieve(q: str, kind: str = "knowledge", top_k: int = 5) -> dict:
        return asdict(service().search(q, kind=kind, top_k=top_k))

    @app.get("/answer")
    def answer(q: str) -> dict[str, str]:
        return {"query": q, "answer": service().answer(q)}

    @app.post("/index-sync")
    def index_sync() -> dict:
        app.state.retrieval_service = build_retrieval_service(root)
        version = getattr(app.state.retrieval_service.engines["knowledge"], "version", None)
        return {"status": "ok", "version": version}

    # -- evaluation -------------------------------------------------------
    @app.post("/eval/sets")
    def create_eval_set(payload: EvalSetIn) -> dict:
        manager = EvalSetManager(Bundle(root))
        cases = [EvalCase(**case.model_dump(exclude_none=True)) for case in payload.cases]
        concept_id = manager.create(payload.name, cases, title=payload.title)
        return {"id": concept_id, "name": payload.name}

    @app.get("/eval/sets")
    def list_eval_sets() -> dict:
        return {"sets": EvalSetManager(Bundle(root)).list()}

    @app.post("/eval/run")
    def run_eval(name: str) -> dict:
        bundle = Bundle(root)
        run = EvalRunner(bundle, service()).run(name)
        return run.to_dict()

    @app.get("/eval/sets/{name}/trend")
    def eval_trend(name: str) -> dict:
        return {"trend": Scoreboard(Bundle(root)).trend(name)}

    # -- review -----------------------------------------------------------
    @app.get("/review/drafts")
    def review_drafts() -> dict:
        bundle = Bundle(root)
        drafts = [
            {"concept_id": concept_id, "title": concept.title, "status": concept.status}
            for concept_id, concept in bundle.iter_concepts("knowledge")
            if concept.status in ("draft", "needs-review")
        ]
        return {"drafts": drafts}

    @app.get("/review/diff")
    def review_diff(concept_id: str) -> dict:
        bundle = Bundle(root)
        concept = bundle.read_concept(concept_id)
        source_texts: list[str] = []
        for source_id in concept.source_ids():
            try:
                source_texts.append(bundle.read_concept(source_id).body)
            except FileNotFoundError:
                continue
        source_text = "\n\n".join(source_texts)
        diff = "\n".join(
            difflib.unified_diff(
                source_text.splitlines(),
                concept.body.splitlines(),
                fromfile="sources",
                tofile="draft",
                lineterm="",
            )
        )
        return {"concept_id": concept_id, "diff": diff or concept.body}

    @app.post("/review/approve")
    def review_approve(concept_id: str, reviewer: str) -> dict:
        bundle = Bundle(root)
        result = GitReview(bundle).approve_draft(concept_id, reviewer=reviewer)
        app.state.retrieval_service = None
        return {
            "concept_id": result.concept_id,
            "approved": result.approved,
            "commit": result.commit,
        }

    return app


app = create_app()
