"""Command-line entry point for mykb."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .okf.bundle import Bundle
from .okf.validate import validate_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mykb", description="Enterprise knowledge platform")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate an OKF bundle for conformance")
    validate.add_argument("root", nargs="?", default=".", help="Bundle root directory")

    run_import = sub.add_parser("import", help="Import a data source into the raw layer")
    run_import.add_argument("root", help="Bundle root directory")
    run_import.add_argument("--connector", required=True, help="Connector name")
    run_import.add_argument("--source-dir", required=True, help="Source directory")
    run_import.add_argument("--base-uri", default=None, help="External base URI for resources")
    run_import.add_argument(
        "--no-incremental", action="store_true", help="Re-import even unchanged content"
    )

    publish = sub.add_parser("publish", help="Publish a knowledge base snapshot")
    publish.add_argument("kb_id", help="Knowledge base id")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "validate":
        issues = validate_bundle(Path(args.root))
        if issues:
            for issue in issues:
                print(f"FAIL {issue}", file=sys.stderr)
            return 1
        print("OKF bundle is valid")
        return 0

    if args.command == "import":
        from .connectors import create_connector
        from .connectors.sync import Importer

        bundle = Bundle(Path(args.root))
        bundle.ensure_layout()
        connector = create_connector(
            args.connector, source_dir=args.source_dir, base_uri=args.base_uri
        )
        result = Importer(bundle, connector).run(incremental=not args.no_incremental)
        print(
            f"imported: added={len(result.added)} updated={len(result.updated)} "
            f"skipped={len(result.skipped)}"
        )
        return 0

    if args.command == "publish":
        from .config import load_settings
        from .db.models import KnowledgeBase, PublishTask
        from .db.session import create_db_engine, create_session_factory
        from .retrieval.service import build_knowledge_backend
        from .retrieval.sync import get_head_commit
        from .retrieval.tasks import run_publish_task

        settings = load_settings()
        engine = create_db_engine(settings.database_url)
        factory = create_session_factory(engine)
        backend = build_knowledge_backend(settings)
        with factory() as session:
            kb = session.get(KnowledgeBase, args.kb_id)
            if kb is None:
                print(f"knowledge base {args.kb_id} not found", file=sys.stderr)
                return 1
            task = PublishTask(
                kb_id=kb.id,
                git_commit=get_head_commit(kb.local_path) or "unversioned",
                status="queued",
            )
            session.add(task)
            session.commit()
            task_id = task.id

        run_publish_task(
            task_id,
            session_factory=factory,
            backend=backend,
            retention=settings.weknora_retention,
            sleep=lambda _s: None,
        )
        with factory() as session:
            finished = session.get(PublishTask, task_id)
            if finished is None:
                print("publish task disappeared", file=sys.stderr)
                return 1
            print(
                f"publish {finished.status}: doc "
                f"{finished.doc_completed}/{finished.doc_total}"
            )
            return 0 if finished.status == "ready" else 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
