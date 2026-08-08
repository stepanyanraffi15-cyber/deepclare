"""The filing contract, checked against every accepted declaration we have.

This replaces a set of unit tests that asserted a contract nobody had ever seen. Those
tests passed while the adapter emitted element names appearing in zero real filings —
which is the failure mode unit tests written from a specification cannot catch, because
they encode the same assumption the code does.

These do not assert an assumption. They assert against 71 declarations of the shape the
portal accepts, which is the only oracle available. Two properties:

  * **round trip** — reading a filing and writing it back reproduces it. Anything the
    reader silently loses or the writer silently invents shows up as a difference.
  * **conformance** — the checker passes every real filing. A checker that rejects a
    genuine accepted document is broken, however reasonable its rule sounds.

No network, no provider, no model. Just files on disk.
"""

from __future__ import annotations

import glob
from pathlib import Path

import pytest

from deepclare.filing import RuleStatus, check
from deepclare.filing.document import parse_document, serialize

CORPUS = sorted(glob.glob("evalkit/corpus/*/case-*/ground_truth.xml"))

pytestmark = pytest.mark.skipif(
    not CORPUS, reason="the evaluation corpus is not present in this checkout"
)


def _elements(xml: str) -> list[tuple[str, str, str]]:
    """Every element as (path, prefix, text), so a difference names where it is."""
    root = parse_document(xml)
    found: list[tuple[str, str, str]] = []

    def walk(element, path: str) -> None:
        here = f"{path}/{element.name}"
        found.append((here, element.prefix, (element.text or "").strip()))
        for child in element.children:
            walk(child, here)

    walk(root, "")
    return found


def test_every_accepted_filing_survives_a_round_trip() -> None:
    """Read then write must return what arrived, element for element."""
    differing: list[str] = []
    for path in CORPUS:
        original = Path(path).read_text(encoding="utf-8")
        rewritten = serialize(parse_document(original))
        if _elements(original) != _elements(rewritten):
            differing.append(Path(path).parent.name)

    assert not differing, (
        f"{len(differing)} of {len(CORPUS)} filings changed under a round trip: "
        f"{differing[:5]}"
    )


def test_the_conformance_checker_accepts_every_real_filing() -> None:
    """A rule that fails a genuine accepted declaration is a bug in the rule."""
    rejected: list[str] = []
    for path in CORPUS:
        xml = Path(path).read_text(encoding="utf-8")
        result = check(parse_document(xml), xml)
        failed = [
            outcome.rule
            for outcome in result.outcomes
            if outcome.status is RuleStatus.FAIL
        ]
        if failed:
            rejected.append(f"{Path(path).parent.name}: {failed}")

    assert not rejected, (
        f"the checker failed {len(rejected)} of {len(CORPUS)} accepted filings: "
        f"{rejected[:3]}"
    )
