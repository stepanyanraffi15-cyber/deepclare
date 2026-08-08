"""Turning state into the strings the prompt files name.

Values only. Every label, every instruction and every explanation of what an absence
means lives in the prompt file — this module renders a menu, a candidate list and a
stated absence, and nothing here reads as English prose to a model that is not data.

One function is not a rendering but a contract: `deterministic_query` composes the search
text the same way the index composed the text it embedded. See its docstring.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from deepclare.classification.line import ClassificationLine
from deepclare.reference.store import Candidate, NomenclatureStore

UNKNOWN = "unknown"
"""A scalar the documents do not state. Absence is always stated to a model, never
omitted: an absent key and an empty one are different signals and only one is a fact."""

NOTHING = "(none)"
"""A block with no entries."""

EM_DASH_JOIN = " — "
"""The separator the index's own embedded text uses. Not decorative: see
`deterministic_query`."""

_MARKER = "   <- matches a likely 6-digit subheading"


def value(text: str | None) -> str:
    """A scalar, or the literal that says it is not stated."""
    cleaned = (text or "").strip()
    return cleaned or UNKNOWN


def bullets(entries: Iterable[str]) -> str:
    """A block of entries, or the literal that says the block is empty."""
    lines = [f"- {entry.strip()}" for entry in entries if entry.strip()]
    return "\n".join(lines) if lines else NOTHING


def menu(entries: Sequence[tuple[str, str]]) -> str:
    """A numbered code-and-title menu, one entry per line.

    Numbered because the model is asked to choose *from the list*, and a numbered list is
    a list it can be seen to have read rather than a set of codes it might have known.
    """
    if not entries:
        return NOTHING
    return "\n".join(
        f"{index:>4}. {code} — {tidy(title)}"
        for index, (code, title) in enumerate(entries, start=1)
    )


def candidate_list(
    candidates: Sequence[Candidate], preferred_subheadings: Sequence[str] = ()
) -> str:
    """The retrieved candidates, each as its full taxonomic path.

    The path rather than the leaf name, because roughly three leaves in ten are named
    only "other" and mean nothing alone — and because the final pick has to be able to
    see that *none* of these is the right category, which a list of bare codes cannot
    show it.

    A matching subheading adds a marker to the row. It never removes a row: hard
    narrowing losses are unrecoverable, so the preference annotates and does not filter.
    """
    if not candidates:
        return NOTHING
    preferred = set(preferred_subheadings)
    rows = []
    for index, candidate in enumerate(candidates, start=1):
        row = f"{index:>4}. {candidate.render()}"
        if candidate.code[:6] in preferred:
            row += _MARKER
        rows.append(row)
    return "\n".join(rows)


def tidy(title: str) -> str:
    """One path or menu segment, without the authority's trailing colon."""
    return " ".join(title.split()).rstrip(":").strip()


def deterministic_query(
    store: NomenclatureStore,
    line: ClassificationLine,
    chapters: Sequence[str],
    headings: Sequence[str],
) -> str:
    """The search text to embed when no model wrote one.

    THE SYMMETRY CONTRACT. Every vector in the index was built from an English,
    broad-to-specific, em-dash-separated noun phrase: `<chapter> — <heading> — <leaf>`. A
    query phrased that way and a query phrased as an ordinary English sentence land in
    different regions of the same space. Measured against this collection: the structured
    form scored 0.84 against the correct leaf where a plain English phrase for the same
    goods scored 0.65. Change one side and the other must change with it.

    So this fallback composes the query from the index's own text wherever it can — the
    chapter title and the heading title are literally the document side's own words — and
    supplies only the leaf slot from the goods line. It is a degradation and it is used
    only when the model returned an empty query: the goods name is in whatever language
    the invoice was printed in, against an English index.
    """
    parts = []
    if chapters:
        chapter = store.entry(chapters[0])
        if chapter is not None:
            parts.append(tidy(chapter.title()))
    if headings:
        heading = store.heading_title(headings[0])
        if heading:
            parts.append(tidy(heading))
    parts.append(tidy(line.source_name))
    return EM_DASH_JOIN.join(parts)
