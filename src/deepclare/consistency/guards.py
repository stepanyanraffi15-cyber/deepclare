"""The checks a prompt cannot enforce, applied to whatever the rewriter returns.

The rewrite prompt states every one of these rules. That is not why they are here: a
prompt is a request and a guardrail is a decision, and the specification records both of
the losses below as measured behaviour of a model that had been asked not to do them.

Four refusals, each keeping the original line rather than filing the proposal:

* **Nothing, or nothing Armenian.** The declaration is filed in Armenian; a blank or
  Latin-script line is not a worse description, it is not a description.
* **A deterministic segment not reproduced verbatim.** The size and shipment-quantity
  segments are computed from the documents' own figures. A model restyling one is a model
  writing a figure, which is the one thing this module must never do.
* **A size or number token lost.** A token the invoice name prints and the current text
  keeps is what tells two members of a product family apart. Conforming a family is
  exactly the operation that tends to erase it.
* **A family collapsed.** Two lines that read differently and come out reading the same
  are two goods the declaration can no longer distinguish. The check fires only when the
  rewrite is what merged them; lines that already read alike are left alone.

Nothing here repairs. A refused proposal is dropped and the line stands as drafted, which
is the whole degradation contract of this module in one sentence.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping

from deepclare.consistency.records import DraftedLine
from deepclare.description import detect_source_language
from deepclare.domain import SourceLanguage

_NUMBER_TOKEN = re.compile(r"\d+(?:[.,]\d+)*")
"""A figure as it is printed, decimal separator included, so `42.5` is one token and not
two. The same shape the description writer's fabricated-figure check uses, for the same
reason: a figure is what a reader sees, not what a tokenizer sees."""


def refusal_for_description(line: DraftedLine, proposed: str) -> str | None:
    """Why this rewritten description must not be filed, or `None` if it may be."""
    text = proposed.strip()
    if not text:
        return "the rewrite returned no text for this line"

    if detect_source_language(text) is not SourceLanguage.ARMENIAN:
        return (
            f"the rewritten text carries no Armenian — {text!r}. The declaration is "
            "filed in Armenian and text in another script is not a description with a "
            "defect"
        )

    missing = tuple(
        segment for segment in line.deterministic_segments if segment not in text
    )
    if missing:
        return (
            f"the rewrite does not reproduce {_listed(missing)} verbatim. Those segments "
            "are computed from the documents' own figures and appended; a rewrite is not "
            "allowed to restate one"
        )

    dropped = dropped_number_tokens(line, text)
    if dropped:
        return (
            f"the rewrite drops {_listed(dropped)}, which the invoice name states and "
            "the current text keeps. That token is what tells this line apart from its "
            "siblings"
        )
    return None


def dropped_number_tokens(line: DraftedLine, proposed: str) -> tuple[str, ...]:
    """Figures the invoice name states, the current text keeps, and the rewrite loses.

    Compared blind to the decimal separator, so a text that writes `42,5` where the
    invoice printed `42.5` has not dropped anything. The comparison is deliberately
    against the *current* text as well as the invoice name: a detail the drafted
    description already left out is not this pass's to restore.
    """
    current = _separator_blind(line.description)
    candidate = _separator_blind(proposed)
    kept = (
        token
        for token in _number_tokens(line.source_name)
        if token in current
    )
    return tuple(dict.fromkeys(token for token in kept if token not in candidate))


def collapsed_lines(
    drafted: Mapping[str, str], resulting: Mapping[str, str]
) -> frozenset[str]:
    """Lines whose rewrite has to be dropped because it merged two distinct lines.

    `resulting` is the final text of every line, whether it was rewritten or not, so a
    proposal that collides with a line nobody touched is caught too. Only the lines that
    actually changed are named: reverting them always resolves the collision, because
    their drafted texts differed.
    """
    by_text: dict[str, list[str]] = defaultdict(list)
    for line_id, text in resulting.items():
        by_text[text].append(line_id)

    collapsed: set[str] = set()
    for line_ids in by_text.values():
        if len(line_ids) < 2:
            continue
        if len({drafted[line_id] for line_id in line_ids}) == 1:
            continue
        collapsed.update(
            line_id
            for line_id in line_ids
            if resulting[line_id] != drafted[line_id]
        )
    return frozenset(collapsed)


def _number_tokens(text: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            _separator_blind(match.group(0))
            for match in _NUMBER_TOKEN.finditer(text)
        )
    )


def _separator_blind(text: str) -> str:
    return text.replace(",", ".")


def _listed(entries: tuple[str, ...]) -> str:
    return ", ".join(repr(entry) for entry in entries)
