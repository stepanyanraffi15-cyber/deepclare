"""Command-line entry point.

The delivery edge, and the only place in the process that reads the environment. Its three
commands are the three things this build can do: draft a declaration from a submission,
rebuild the nomenclature tree, and rebuild the vector collection over it.

Nothing below decides anything about a declaration. It parses arguments, loads settings
once, builds the ports, runs the chain and writes what came back — which is what keeps the
run itself executable with no command line, no filesystem and no network present.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from deepclare.config import ConfigurationError, Settings, load_settings

if TYPE_CHECKING:
    from deepclare.domain import DocumentRole
    from deepclare.intake import SubmittedFile

DEFAULT_OUTPUT_DIR = "out"
DECLARATION_FILE = "declaration.xml"
REVIEW_FILE = "review.txt"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m deepclare")
    subcommands = parser.add_subparsers(dest="command", required=True)

    run = subcommands.add_parser(
        "run", help="Produce a declaration draft from a submission"
    )
    run.add_argument("document", help="Path to the commercial invoice")
    run.add_argument(
        "--consignment-note",
        metavar="PATH",
        help="Path to the CMR or other consignment note, if there is one",
    )
    run.add_argument(
        "--out",
        metavar="DIR",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Where to write the declaration and the review report (default: "
        f"./{DEFAULT_OUTPUT_DIR})",
    )
    run.add_argument(
        "--no-page-classifier",
        action="store_true",
        help="Skip page classification; every page keeps its source file's role",
    )
    run.add_argument(
        "--no-consistency",
        action="store_true",
        help="Skip the cross-line reconciliation pass",
    )
    run.add_argument(
        "--show-chain",
        action="store_true",
        help="Print the chain and its branch conditions before running",
    )

    build = subcommands.add_parser(
        "build-reference",
        help="Rebuild the nomenclature tree and attach its text to the vectors",
    )
    build.add_argument(
        "--reacquire",
        action="store_true",
        help="Ignore the snapshot and enumerate the authority again",
    )
    build.add_argument(
        "--entries-only",
        action="store_true",
        help="Write the entries artifact but leave the vector payloads untouched",
    )

    index = subcommands.add_parser(
        "build-index",
        help="Embed every filable code and write the vector collection",
    )
    index.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the collection first. Required the first time, and "
        "whenever the embedding model or width changes",
    )

    subcommands.add_parser(
        "serve",
        help="Run the M15 service edge — dev-only auth, one worker, no persistence",
    )

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.command == "build-reference":
        return _build_reference(settings, args.reacquire, args.entries_only)

    if args.command == "build-index":
        return _build_index(settings, args.recreate)

    if args.command == "serve":
        return _serve(settings)

    if args.command == "run":
        return _run(
            settings,
            invoice=Path(args.document),
            consignment_note=(
                Path(args.consignment_note) if args.consignment_note else None
            ),
            out=Path(args.out),
            classify_pages=not args.no_page_classifier,
            reconcile_lines=not args.no_consistency,
            show_chain=args.show_chain,
        )

    return 1


# --- run ------------------------------------------------------------------------------


def _run(
    settings: Settings,
    *,
    invoice: Path,
    consignment_note: Path | None,
    out: Path,
    classify_pages: bool,
    reconcile_lines: bool,
    show_chain: bool,
) -> int:
    """Draft one declaration and write it, plus the account of what needs a human."""
    from deepclare.domain import DocumentRole
    from deepclare.review import render_report
    from deepclare.run import (
        RunInput,
        describe_chain,
        execute,
        format_summary,
        open_ports,
    )

    files = [_submitted(invoice, DocumentRole.INVOICE)]
    if consignment_note is not None:
        files.append(_submitted(consignment_note, DocumentRole.CONSIGNMENT_NOTE))

    if show_chain:
        print(describe_chain())
        print()

    run_input = RunInput(files=tuple(files))
    with open_ports(
        settings,
        features=run_input.options.classification_features,
        classify_pages=classify_pages,
        reconcile_lines=reconcile_lines,
    ) as ports:
        state = execute(run_input, ports)

    out.mkdir(parents=True, exist_ok=True)
    declaration_path = out / DECLARATION_FILE
    review_path = out / REVIEW_FILE
    declaration_path.write_text(state.require_filed().xml, encoding="utf-8")
    review_path.write_text(
        render_report(state.require_report()), encoding="utf-8"
    )

    print()
    print("=" * 78)
    print("RUN SUMMARY")
    print("=" * 78)
    print(format_summary(state))
    print()
    print(f"declaration   {declaration_path}")
    print(f"review report {review_path}")
    print()
    print(
        "This is a draft. Nothing here is filed, and every item in the review report is "
        "something a human confirms before it is."
    )
    return 0


def _submitted(path: Path, role: "DocumentRole") -> "SubmittedFile":
    """One uploaded file, read off disk exactly as it is.

    The role is declared rather than inferred from the name: the caller named the file on
    the command line, and a declared role is a stronger hint than a guess at a filename.
    """
    from deepclare.intake import SubmittedFile

    if not path.is_file():
        raise SystemExit(f"no such file: {path}")
    return SubmittedFile(
        file_name=path.name, content=path.read_bytes(), declared_role=role
    )


# --- serve ------------------------------------------------------------------------------


def _serve(settings: Settings) -> int:
    """Run the M15 service edge. Foreground, one process — there is nothing here yet
    that a process manager or a reverse proxy would coordinate."""
    import uvicorn

    from deepclare.service import create_app

    app = create_app(settings)
    uvicorn.run(app, host=settings.service_host, port=settings.service_port)
    return 0


# --- reference data -------------------------------------------------------------------


def _build_reference(settings: Settings, reacquire: bool, entries_only: bool) -> int:
    """Acquire the tree, resolve every code's ancestry, publish, and enrich the vectors."""
    from qdrant_client import QdrantClient

    from deepclare.reference.authority import acquire_tree
    from deepclare.reference.enrich import enrich_collection, write_entries
    from deepclare.reference.tree import SourceNode, build_entries

    snapshot = Path(settings.reference_snapshot_dir) / "nodes.jsonl"
    nodes = acquire_tree(
        api_base=settings.nomenclature_api_base,
        max_node_id=settings.nomenclature_max_node_id,
        workers=settings.nomenclature_crawl_workers,
        snapshot=snapshot,
        reacquire=reacquire,
    )

    entries = build_entries([SourceNode.model_validate(n) for n in nodes])
    write_entries(Path(settings.reference_dir), entries)

    with_ancestors = sum(1 for e in entries if e.ancestors)
    deepest = max((len(e.ancestors) for e in entries), default=0)
    print(f"\nnodes acquired    {len(nodes)}")
    print(f"filable codes     {len(entries)}")
    print(f"  with ancestry   {with_ancestors} (deepest chain {deepest})")
    print(f"  with a unit     {sum(1 for e in entries if e.supplementary_unit)}")

    if entries_only:
        print("\nvector payloads left untouched (--entries-only)")
        return 0

    client = QdrantClient(path=str(settings.qdrant_path))
    try:
        updated, unmatched = enrich_collection(
            client, settings.qdrant_collection, entries
        )
    finally:
        client.close()
    print(f"\npoints enriched   {updated}")
    if unmatched:
        print(
            f"points with no matching code: {unmatched} — the vectors and the tree "
            f"disagree and one of them is stale"
        )
    return 0


def _build_index(settings: Settings, recreate: bool) -> int:
    """Embed every filable code and write the vector collection.

    One embedding call per code — 14,000-odd of them — so this is minutes and real money.
    The collection is normally copied rather than rebuilt; this exists so a clone with
    neither half of the reference layer can reach a working state.
    """
    from qdrant_client import QdrantClient

    from deepclare.embedding import GeminiEmbedder
    from deepclare.reference.enrich import read_entries
    from deepclare.reference.index import build_index

    entries = read_entries(Path(settings.reference_dir))
    print(f"entries to embed  {len(entries)}")
    print(
        f"embedding model   {settings.classify_embedding_model} at "
        f"{settings.classify_embedding_dim} dimensions"
    )

    embedder = GeminiEmbedder(settings)
    client = QdrantClient(path=str(settings.qdrant_path))
    try:
        written = build_index(
            entries=entries,
            embed_documents=embedder.embed_documents,
            qdrant_client=client,
            collection=settings.qdrant_collection,
            dimensions=settings.classify_embedding_dim,
            recreate=recreate,
        )
    finally:
        embedder.close()
        client.close()
    print(f"\npoints written    {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
