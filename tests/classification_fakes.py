"""Stand-ins for the two things classification needs from outside itself.

Not collected by pytest (only `test_*.py` is). They exist so that the traversal, the
layer stack and every branch condition can be exercised with no network, no provider key
and no reference artifact — which is what makes those tests worth running on every
change.

Both fakes are deliberately dumb. The store answers from dictionaries the test wrote and
the model answers from a queue the test filled; neither knows anything about codes. A
fake that reimplemented the thing it replaces would pass tests the real one fails.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pydantic import BaseModel

from deepclare.classification.line import ClassificationLine
from deepclare.description import LineContext
from deepclare.domain import Provenance, SourceLanguage, Traced, ValueOrigin
from deepclare.models import Decoding, ModelCall, ModelResult, ModelTier
from deepclare.prompting import Prompt
from deepclare.reference.store import Candidate, Entry, SearchOutcome

EXTRACTED = Provenance(origin=ValueOrigin.EXTRACTED, source_document_id="invoice")


def traced(value: str) -> Traced[str]:
    return Traced[str](value=value, provenance=EXTRACTED)


def entry(code: str, name: str, unit: str | None = None) -> Entry:
    level = {2: 1, 4: 2}.get(len(code), 5)
    return Entry(
        code=code,
        level=level,
        name_en=name,
        supplementary_unit=unit,
        path_en=f"chapter {code[:2]} › heading {code[:4]} › {name}",
    )


def candidate(code: str, similarity: float, name: str = "a leaf") -> Candidate:
    return Candidate(code=code, similarity=similarity, entry=entry(code, name))


def line(
    line_id: str = "1",
    *,
    description_hy: str = "ԱՊՐԱՆՔ",
    search_term_hy: str = "ԱՊՐԱՆՔ",
    source_name: str = "GOODS",
    printed_code: str | None = None,
    catalogue_code: str | None = None,
    material: str | None = None,
) -> ClassificationLine:
    return ClassificationLine(
        line_id=line_id,
        description_hy=description_hy,
        search_term_hy=search_term_hy,
        source_name=source_name,
        source_language=SourceLanguage.ENGLISH_LATIN,
        material=material,
        printed_code=traced(printed_code) if printed_code else None,
        catalogue_code=traced(catalogue_code) if catalogue_code else None,
    )


def context(line_id: str = "1", goods_name: str = "GOODS") -> LineContext:
    return LineContext(
        line_id=line_id,
        goods_name=goods_name,
        source_language=SourceLanguage.ENGLISH_LATIN,
    )


class FakeStore:
    """Answers reference queries from what the test put in it."""

    def __init__(
        self,
        *,
        entries: Sequence[Entry] = (),
        headings: dict[str, str] | None = None,
        subheadings: dict[str, str] | None = None,
        notes: dict[str, str] | None = None,
        search: Callable[[str, list[str] | None, int], list[Candidate]] | None = None,
    ) -> None:
        self._entries = {e.code: e for e in entries}
        self._headings = headings or {}
        self._subheadings = subheadings or {}
        self._notes = notes or {}
        self._search = search or (lambda _query, _prefixes, _limit: [])
        self.searches: list[tuple[str, list[str] | None, int]] = []

    def entry(self, code: str) -> Entry | None:
        return self._entries.get(code)

    def exists(self, code: str) -> bool:
        """The real store's contract, restated: the 10-digit leaf form and the filed
        11-digit national form, digits only, never a run of zeros."""
        cleaned = code.strip()
        if not cleaned.isdigit():
            return False
        if len(cleaned) == 11:
            cleaned = cleaned[:10]
        if len(cleaned) != 10 or set(cleaned) == {"0"}:
            return False
        found = self._entries.get(cleaned)
        return found is not None and found.level == 5

    def known_chapters(self) -> set[str]:
        return {e.code for e in self._entries.values() if e.level == 1}

    def chapter_menu(self) -> list[tuple[str, str]]:
        return sorted(
            (e.code, e.title()) for e in self._entries.values() if e.level == 1
        )

    def heading_menu(self, chapters: list[str]) -> list[tuple[str, str]]:
        wanted = set(chapters)
        return sorted(
            (code, title)
            for code, title in self._headings.items()
            if code[:2] in wanted
        )

    def heading_title(self, heading: str) -> str | None:
        return self._headings.get(heading)

    def subheading_menu(self, headings: list[str]) -> list[tuple[str, str]]:
        wanted = set(headings)
        return sorted(
            (code, title)
            for code, title in self._subheadings.items()
            if code[:4] in wanted
        )

    def chapter_note(self, chapter: str, *, budget: int = 1500) -> str:
        return self._notes.get(chapter, "")[:budget] or "(none)"

    def search(
        self, query: str, *, prefixes: list[str] | None = None, limit: int = 10
    ) -> SearchOutcome:
        self.searches.append((query, prefixes, limit))
        found = self._search(query, prefixes, limit)
        return SearchOutcome(
            candidates=list(found),
            scope="fake" if prefixes else "unfiltered",
            dropped_unknown_codes=0,
        )


class FakeModel:
    """Returns queued answers, one per call, and records what it was asked."""

    def __init__(self, answers: Sequence[BaseModel]) -> None:
        self._answers = list(answers)
        self.prompts: list[Prompt] = []
        self.tiers: list[ModelTier] = []

    def generate(
        self,
        *,
        tier: ModelTier,
        prompt: Prompt,
        output: type[BaseModel],
        decoding: Decoding | None = None,
    ) -> ModelResult:
        if not self._answers:
            raise AssertionError(
                f"the fake model ran out of answers; it was asked for a {output.__name__}"
            )
        answer = self._answers.pop(0)
        if not isinstance(answer, output):
            raise AssertionError(
                f"the next queued answer is a {type(answer).__name__} but the call asked "
                f"for a {output.__name__}"
            )
        self.prompts.append(prompt)
        self.tiers.append(tier)
        return ModelResult[output](
            value=answer,
            call=ModelCall(
                tier=tier,
                model_id="fake",
                prompt_name=prompt.name,
                prompt_version=prompt.version,
                decoding=Decoding(max_output_tokens=1024),
                usage={},
            ),
        )

    @property
    def remaining(self) -> int:
        return len(self._answers)
