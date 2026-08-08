"""synth — generate a synthetic customs corpus from one authoritative declaration.

Dev tool (reads a private seed, produces public synthetic cases). Kept beside the
verifier for convenience; only the produced `corpus/` and `evalkit/` need to ship.

Chain: load_seed -> make_case (recombine + fake parties + jitter) -> render_xml
(+ atoms) -> guardrails. See cli.py.
"""

from __future__ import annotations

from .guardrails import consistency, leak_scan
from .ir import Case, GoodLine, Party
from .recombine import make_case, make_cases
from .render_xml import render_atoms, render_xml
from .seed import Seed, load_seed
from .stamps import signature_svg, stamp_svg

__all__ = [
    "Case",
    "GoodLine",
    "Party",
    "Seed",
    "consistency",
    "leak_scan",
    "load_seed",
    "make_case",
    "make_cases",
    "render_atoms",
    "render_xml",
    "signature_svg",
    "stamp_svg",
]


def __main__() -> None:  # pragma: no cover
    from .cli import main

    raise SystemExit(main())
