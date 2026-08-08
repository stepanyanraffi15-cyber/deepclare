"""The commodity nomenclature as a tree, with every level the authority publishes.

Part of M3 (Reference Data Build). Dossier 10 §3 M3: this must not know about the
pipeline, the declaration, the filing contract, tenancy, or the service edge.

WHY THE INTERMEDIATE LEVELS MATTER, which is the whole point of this module:

Only 2-digit chapters, 4-digit headings and 10-digit leaves are filable, so an earlier
build kept those and discarded everything between them. That loses the text that makes a
leaf identifiable. Measured on the current tree, **29.5% of leaves are named exactly
"other"** — the name is not wrong, it is simply relative to a parent that was thrown
away. Four leaves under heading 3923 all read "other", and their parents say:

    3923301090   bottles, flasks, phials … › of a capacity not exceeding 2 l
    3923299000   bags and sacks (including cones) › of other plastics
    3923309090   bottles, flasks, phials … › of a capacity exceeding 2 l
    3923900000   (nothing between — genuinely a catch-all)

A small bottle, a plastic bag, a large bottle and a true catch-all, indistinguishable
without their ancestry. Choosing between them, or recognising that none of them fits, is
impossible from the leaf name alone.

So this module keeps every node the authority serves — including the 6- and 8-digit
groups and the code-less folders — and resolves each filable code's full ancestor chain.
The chain is text only: it is never filed, and it does not change which codes exist.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

FILABLE_CODE_LENGTHS = {2: 1, 4: 2, 10: 5}
"""Code length to level. Only these are filable and only these carry a vector; every
other node exists to give them context."""

NATIONAL_CODE_LENGTH = 11
"""Armenia adds a rare national 11th digit. Fold such a code onto its 10-digit parent —
the declaration side re-appends a national digit at filing time."""

_NO_UNIT = {"", "-"}
"""The authority's sentinel for "this code has no supplementary unit"."""


class SourceNode(BaseModel):
    """One node as the authority serves it, before any interpretation."""

    model_config = ConfigDict(extra="ignore")

    id: int
    parentId: int | None = None
    code: str | None = None
    name: str | None = None
    nameEn: str | None = None
    nameRu: str | None = None
    type: str | None = None
    unit: str | None = None


class Ancestor(BaseModel):
    """One step of a code's ancestry. `code` is absent on the folder levels."""

    model_config = ConfigDict(frozen=True)

    code: str | None = None
    kind: str | None = Field(default=None, description="the authority's own node type")
    name_en: str | None = None
    name_hy: str | None = None
    name_ru: str | None = None

    def label(self, language: str) -> str | None:
        chosen = getattr(self, f"name_{language}", None)
        return chosen or self.name_en or self.name_hy or self.name_ru


class TreeEntry(BaseModel):
    """A filable code with its names, its supplementary unit, and its full ancestry."""

    model_config = ConfigDict(frozen=True)

    code: str
    level: int
    name_en: str | None = None
    name_hy: str | None = None
    name_ru: str | None = None
    supplementary_unit: str | None = Field(
        default=None,
        description="As the authority serves it — a Russian abbreviation such as 'шт'. "
        "Resolved to an OKEI code later, by the unit alias table.",
    )
    ancestors: tuple[Ancestor, ...] = ()
    """Broad to specific, ending at this code's immediate parent. Includes the 6- and
    8-digit groups and the code-less folders."""

    def path(self, language: str = "en", *, separator: str = " › ") -> str:
        """The taxonomic path a person or a model reads, ending in this code's own name.

        Section headers are dropped: they are an organisational level above chapters and
        add length without adding discrimination.
        """
        parts = [
            label
            for ancestor in self.ancestors
            if ancestor.kind != "header" and (label := ancestor.label(language))
        ]
        own = getattr(self, f"name_{language}", None) or self.name_en
        if own:
            parts.append(own)
        return separator.join(_tidy(p) for p in parts)


def _tidy(text: str) -> str:
    """Authority text often ends in a colon, which reads badly mid-path."""
    return text.strip().rstrip(":").strip()


def build_entries(nodes: list[SourceNode]) -> list[TreeEntry]:
    """Resolve every filable code to its names, unit and ancestry.

    Ancestry is walked through the authority's own parent links rather than derived from
    code prefixes, because the levels that matter here — the folders — carry no code to
    derive a prefix from.
    """
    by_id = {node.id: node for node in nodes}
    entries: dict[str, TreeEntry] = {}

    for node in nodes:
        code = _filable_code(node)
        if code is None:
            continue

        entry = TreeEntry(
            code=code,
            level=FILABLE_CODE_LENGTHS[len(code)],
            name_en=_clean(node.nameEn),
            name_hy=_clean(node.name),
            name_ru=_clean(node.nameRu),
            supplementary_unit=_supplementary_unit(node.unit),
            ancestors=_ancestors_of(node, by_id),
        )

        existing = entries.get(code)
        if existing is None or _is_richer(entry, existing):
            entries[code] = entry

    return sorted(entries.values(), key=lambda e: e.code)


def _filable_code(node: SourceNode) -> str | None:
    """The node's filable code, or None if it is a context-only node."""
    code = (node.code or "").strip()
    if not code.isdigit():
        return None
    if len(code) == NATIONAL_CODE_LENGTH:
        code = code[:10]
    return code if len(code) in FILABLE_CODE_LENGTHS else None


def _ancestors_of(node: SourceNode, by_id: dict[int, SourceNode]) -> tuple[Ancestor, ...]:
    """Walk parent links to the root, broadest first.

    Guards against a cycle in the authority's data rather than trusting it: a malformed
    parent link would otherwise hang the whole build.
    """
    chain: list[Ancestor] = []
    seen: set[int] = {node.id}
    current = node.parentId

    while current is not None and current in by_id and current not in seen:
        seen.add(current)
        parent = by_id[current]
        chain.append(
            Ancestor(
                code=(parent.code or "").strip() or None,
                kind=parent.type,
                name_en=_clean(parent.nameEn),
                name_hy=_clean(parent.name),
                name_ru=_clean(parent.nameRu),
            )
        )
        current = parent.parentId

    chain.reverse()
    return tuple(chain)


def _is_richer(candidate: TreeEntry, incumbent: TreeEntry) -> bool:
    """De-duplication: the authority can serve one code twice. Prefer English, then depth."""
    if bool(candidate.name_en) != bool(incumbent.name_en):
        return bool(candidate.name_en)
    return len(candidate.ancestors) > len(incumbent.ancestors)


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    return " ".join(text.split()) or None


def _supplementary_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    cleaned = unit.strip()
    return None if cleaned in _NO_UNIT else cleaned
