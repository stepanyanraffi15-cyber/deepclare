"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
import sys

from deepclare.config import ConfigurationError, load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m deepclare")
    subcommands = parser.add_subparsers(dest="command", required=True)

    run = subcommands.add_parser(
        "run", help="Produce a declaration draft from a submission"
    )
    run.add_argument("document", help="Path to the commercial invoice")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    try:
        load_settings()
    except ConfigurationError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.command == "run":
        raise NotImplementedError(
            "The run pipeline is not built yet. Missing, in build order: the page-type "
            "classifier intake injects, the spreadsheet reading path (M6 reads pages, "
            "not workbooks), classification (M9), declaration assembly (M11), and the "
            "filing format adapter (M12)."
        )

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
