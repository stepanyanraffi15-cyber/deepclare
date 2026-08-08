"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from deepclare.config import ConfigurationError, Settings, load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m deepclare")
    subcommands = parser.add_subparsers(dest="command", required=True)

    run = subcommands.add_parser(
        "run", help="Produce a declaration draft from a submission"
    )
    run.add_argument("document", help="Path to the commercial invoice")

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

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.command == "build-reference":
        return _build_reference(settings, args.reacquire, args.entries_only)

    if args.command == "run":
        raise NotImplementedError(
            "The run pipeline is not built yet. Missing, in build order: the page-type "
            "classifier intake injects, the spreadsheet reading path (M6 reads pages, "
            "not workbooks), classification (M9), declaration assembly (M11), and the "
            "filing format adapter (M12)."
        )

    return 1


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
    updated, unmatched = enrich_collection(
        client, settings.qdrant_collection, entries
    )
    print(f"\npoints enriched   {updated}")
    if unmatched:
        print(
            f"points with no matching code: {unmatched} — the vectors and the tree "
            f"disagree and one of them is stale"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
