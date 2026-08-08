"""M4 Reference Data Service — the one canonical query surface over the nomenclature.

In: queries only. Out: entries, menus, prefix-scoped semantic top-k with the scope
applied inside the store, chapter legal notes, a code-existence verdict, and the dataset
vintage backing every answer.

It must not know who is asking, why, or what a declaration is. It never abstains, never
flags for review, never applies a domain tie-break, and never knows a tenant. Those are
decisions, and decisions belong to the modules that own them.

Two failure shapes are defended against here rather than discovered from accuracy later:

  * **Startup precondition.** The artifacts are large derived objects no checkout
    reproduces. Their absence is a loud refusal at construction, never a runtime where
    every classification silently returns nothing.

  * **Silent under-return.** A vector point whose code is missing from the metadata
    would be dropped from results, so a top-k could return fewer than k with no signal.
    That discrepancy is counted and reported on every search instead.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

CHAPTER_LEVEL = 1
HEADING_LEVEL = 2
LEAF_LEVEL = 5
SUBHEADING_CODE_LENGTH = 6
LEAF_CODE_LENGTH = 10
NATIONAL_CODE_LENGTH = 11
CHAPTER_NOTE_BUDGET = 1500
"""Characters of legal note the final pick is given. A whole note can run past 18,000
characters, which would crowd out the candidates it is meant to help judge."""

NO_NOTE = "(none)"
"""What the classification call sees when a chapter has no note. Explicit, so an absent
note reads as a known absence rather than an empty string that might be a bug."""


class QueryEmbedder(Protocol):
    """Turns a search query into a vector.

    The index was built with one specific model at one specific width; a different
    pairing does not align with these vectors. Implementations carry both so a run can
    pin what it actually used.
    """

    @property
    def model(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed_query(self, text: str) -> list[float]: ...


class ArtifactUnavailableError(RuntimeError):
    """The reference data is missing or unusable. Fatal at construction, by design."""


class Entry(BaseModel):
    """One filable code: its names, its supplementary unit, its taxonomic path."""

    model_config = ConfigDict(frozen=True)

    code: str
    level: int
    name_en: str | None = None
    name_hy: str | None = None
    name_ru: str | None = None
    supplementary_unit: str | None = None
    path_en: str | None = None
    path_hy: str | None = None

    def title(self) -> str:
        return self.name_en or self.name_hy or self.name_ru or self.code


class Candidate(BaseModel):
    """One retrieved code with its similarity and the path a model reads to judge it."""

    model_config = ConfigDict(frozen=True)

    code: str
    similarity: float
    entry: Entry

    def render(self) -> str:
        """`code — chapter › heading › … › leaf`.

        The path rather than the bare leaf name, because roughly three in ten leaves are
        named only "other" and mean nothing alone — and because the model must be able to
        see that *none* of the candidates is the right category and abstain.
        """
        return f"{self.code} — {self.entry.path_en or self.entry.title()}"


@dataclass(frozen=True)
class SearchOutcome:
    """Candidates, plus the honesty about what happened while retrieving them."""

    candidates: list[Candidate]
    scope: str
    dropped_unknown_codes: int
    """Vector hits whose code is absent from the metadata. Non-zero means the two halves
    of the index disagree and one of them is stale."""


class NomenclatureStore:
    """Metadata and retrieval over one nomenclature vintage."""

    def __init__(
        self,
        *,
        artifact_dir: Path,
        qdrant_client: object,
        collection: str,
        embedder: QueryEmbedder,
    ) -> None:
        loaded = _load(Path(artifact_dir))
        self._entries, self._headings, self._subheadings, self._notes, self._meta = loaded
        self._chapters = sorted(
            (e for e in self._entries.values() if e.level == CHAPTER_LEVEL),
            key=lambda e: e.code,
        )
        self._client = qdrant_client
        self._collection = collection
        self._embedder = embedder

    # --- provenance of every answer ----------------------------------------

    @property
    def vintage(self) -> str:
        """Which edition of the tree backs every answer. Without it, an accuracy change
        cannot be attributed to the model rather than the data."""
        return str(self._meta.get("built_at", "unknown"))

    @property
    def embedding_pairing(self) -> tuple[str, int]:
        return self._embedder.model, self._embedder.dimensions

    # --- lookups -----------------------------------------------------------

    def entry(self, code: str) -> Entry | None:
        return self._entries.get(code)

    def exists(self, code: str) -> bool:
        """The existence gate's backing query.

        Accepts the 10-digit leaf form and the filed 11-digit national form, whose first
        ten digits must be an entry. Anything else — wrong length, letters, an all-zeros
        filler of the kind found in real stored declarations — is not a code.
        """
        cleaned = code.strip()
        if not cleaned.isdigit():
            return False
        if len(cleaned) == NATIONAL_CODE_LENGTH:
            cleaned = cleaned[:LEAF_CODE_LENGTH]
        if len(cleaned) != LEAF_CODE_LENGTH or set(cleaned) == {"0"}:
            return False
        found = self._entries.get(cleaned)
        return found is not None and found.level == LEAF_LEVEL

    # --- menus -------------------------------------------------------------

    def chapter_menu(self) -> list[tuple[str, str]]:
        """Every chapter with a title, for the first narrowing call to shortlist from."""
        return [(e.code, e.title()) for e in self._chapters]

    def known_chapters(self) -> set[str]:
        return {e.code for e in self._chapters}

    def heading_menu(self, chapters: list[str]) -> list[tuple[str, str]]:
        """Headings of the given chapters, with titles that are never blank.

        Built from the heading-title map rather than by scanning entries: 271 headings
        have no explicit node of their own, and scanning would silently lose them.
        Heading mis-narrowing is unrecoverable — it filters the correct code out of
        retrieval entirely — so the menu must be complete.
        """
        wanted = set(chapters)
        return sorted(
            (code, title)
            for code, title in self._headings.items()
            if code[:2] in wanted
        )

    def heading_title(self, heading: str) -> str | None:
        """One heading's title, or None if the tree has no such heading."""
        return self._headings.get(heading)

    def subheading_menu(self, headings: list[str]) -> list[tuple[str, str]]:
        """The 6-digit subheadings of the given headings, with titles.

        This tree publishes no 6-digit nodes of its own — the level exists only as an
        intermediate step in each leaf's ancestry — so the menu is derived from that
        ancestry. It is the harmonized level where the legal splits live: voltage classes,
        retail versus bulk form, material thresholds, a named kind against a residual
        "other".
        """
        wanted = set(headings)
        return sorted(
            (code, title)
            for code, title in self._subheadings.items()
            if code[:4] in wanted
        )

    def chapter_note(self, chapter: str, *, budget: int = CHAPTER_NOTE_BUDGET) -> str:
        """The chapter's legal note, truncated to the prompt budget.

        This is the legal text that separates two codes which look equally plausible.
        """
        note = self._notes.get(chapter, "").strip()
        return note[:budget] if note else NO_NOTE

    # --- retrieval ---------------------------------------------------------

    def search(
        self, query: str, *, prefixes: list[str] | None = None, limit: int = 10
    ) -> SearchOutcome:
        """Cosine top-k over leaves, optionally scoped by code prefixes.

        No similarity threshold is applied: every retrieved candidate is shown to the
        model, which is what lets it judge that none of them fits. Candidates are
        deduplicated by code keeping the maximum similarity, then sorted descending.
        """
        from qdrant_client import models as qmodels

        vector = self._embedder.embed_query(query)
        conditions: list[object] = [
            qmodels.FieldCondition(
                key="level", match=qmodels.MatchValue(value=LEAF_LEVEL)
            )
        ]
        scope = "unfiltered"
        if prefixes:
            field = _prefix_field(prefixes)
            conditions.append(
                qmodels.FieldCondition(key=field, match=qmodels.MatchAny(any=prefixes))
            )
            scope = f"{field} in {sorted(prefixes)}"

        hits = self._client.query_points(
            self._collection,
            query=vector,
            limit=limit * 3,  # over-fetch so dropping a stray code cannot shrink the result
            query_filter=qmodels.Filter(must=conditions),
            with_payload=True,
        ).points

        best: dict[str, float] = {}
        dropped = 0
        for hit in hits:
            code = str(hit.payload.get("code", ""))
            if code not in self._entries:
                dropped += 1
                continue
            if hit.score > best.get(code, -1.0):
                best[code] = hit.score

        if dropped:
            logger.warning(
                "%d retrieved codes are absent from the metadata and were dropped; "
                "the vectors and the tree disagree and one of them is stale",
                dropped,
            )

        ranked = sorted(best.items(), key=lambda pair: pair[1], reverse=True)[:limit]
        return SearchOutcome(
            candidates=[
                Candidate(code=code, similarity=score, entry=self._entries[code])
                for code, score in ranked
            ],
            scope=scope,
            dropped_unknown_codes=dropped,
        )


def _prefix_field(prefixes: list[str]) -> str:
    """Pick the payload field matching the prefix width, so the scope is applied in the
    store rather than by scanning results."""
    widths = {len(p) for p in prefixes}
    if len(widths) != 1:
        raise ValueError(f"all scope prefixes must share a width, got {sorted(widths)}")
    field = {2: "p2", 4: "p4", 6: "p6", 8: "p8"}.get(widths.pop())
    if field is None:
        raise ValueError("no payload field indexes prefixes of that width")
    return field


def _load(
    directory: Path,
) -> tuple[dict[str, Entry], dict[str, str], dict[str, str], dict[str, str], dict]:
    entries_path = directory / "entries.jsonl"
    headings_path = directory / "headings.json"
    if not entries_path.exists() or not headings_path.exists():
        raise ArtifactUnavailableError(
            f"Reference artifact at {directory} is incomplete. Expected entries.jsonl "
            f"and headings.json.\nBuild it with:  python -m deepclare build-reference"
        )

    entries: dict[str, Entry] = {}
    subheadings: dict[str, str] = {}
    with entries_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            _collect_subheadings(raw, subheadings)
            entries[raw["code"]] = Entry(
                code=raw["code"],
                level=raw["level"],
                name_en=raw.get("name_en"),
                name_hy=raw.get("name_hy"),
                name_ru=raw.get("name_ru"),
                supplementary_unit=raw.get("supplementary_unit"),
                path_en=_render_path(raw, "en"),
                path_hy=_render_path(raw, "hy"),
            )
    if not entries:
        raise ArtifactUnavailableError(f"{entries_path} contains no entries")

    headings = json.loads(headings_path.read_text(encoding="utf-8"))
    notes_path = directory / "notes.json"
    notes = (
        json.loads(notes_path.read_text(encoding="utf-8"))
        if notes_path.exists()
        else {}
    )
    meta_path = directory / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

    if not notes:
        logger.warning(
            "no chapter legal notes in %s — every classification will run without legal "
            "context, silently. This materially affects accuracy.",
            directory,
        )
    logger.info(
        "reference loaded: %d entries, %d heading titles, %d subheading titles, "
        "%d chapter notes, vintage %s",
        len(entries), len(headings), len(subheadings), len(notes),
        meta.get("built_at", "unknown"),
    )
    return entries, headings, subheadings, notes, meta


def _collect_subheadings(raw: dict, into: dict[str, str]) -> None:
    """Record the 6-digit levels this entry passes through on its way down the tree."""
    for ancestor in raw.get("ancestors", []):
        code = ancestor.get("code")
        name = ancestor.get("name_en") or ancestor.get("name_ru")
        if code and name and len(code) == SUBHEADING_CODE_LENGTH:
            into.setdefault(code, name)


def _render_path(raw: dict, language: str) -> str | None:
    """Broad to specific, ending in the code's own name.

    Section headers are dropped: they sit above chapters and lengthen the path without
    helping anyone tell two codes apart.
    """
    parts = [
        text
        for ancestor in raw.get("ancestors", [])
        if ancestor.get("kind") != "header"
        and (text := (ancestor.get(f"name_{language}") or ancestor.get("name_en")))
    ]
    own = raw.get(f"name_{language}") or raw.get("name_en")
    if own:
        parts.append(own)
    tidy = [p.strip().rstrip(":").strip() for p in parts if p and p.strip()]
    return " › ".join(tidy) or None
