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

    sync_index = sub.add_parser(
        "sync-index", help="Versioned sync of verified knowledge into retrieval engines"
    )
    sync_index.add_argument("root", help="Bundle root directory")

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

    if args.command == "sync-index":
        from .retrieval.service import build_retrieval_service

        service = build_retrieval_service(args.root)
        version = getattr(service.engines["knowledge"], "version", None)
        print(f"index synced at version {version}")
        return 0

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
