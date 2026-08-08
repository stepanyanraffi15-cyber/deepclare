"""The retrieval contract: what the store does with what the vectors return.

Four rules the classifier depends on and cannot enforce for itself, all tested against
the real store with a stand-in vector client and an artifact written into a temp
directory:

* the prefix scope is applied **inside** the store, as a filter on the payload's own
  prefix fields, never by scanning the results;
* **no similarity threshold** — every retrieved candidate survives;
* duplicates collapse by code keeping the **maximum** similarity, sorted descending;
* a retrieved code the tree does not know is counted and reported rather than quietly
  shrinking the result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from deepclare.reference.store import ArtifactUnavailableError, NomenclatureStore


@dataclass
class Point:
    payload: dict
    score: float


class FakeQdrant:
    """Returns the points the test gave it, and remembers how it was asked."""

    def __init__(self, points: list[Point]) -> None:
        self._points = points
        self.filters: list[object] = []
        self.limits: list[int] = []

    def query_points(self, collection, *, query, limit, query_filter, with_payload):
        self.filters.append(query_filter)
        self.limits.append(limit)
        return type("Response", (), {"points": self._points})()


class FakeEmbedder:
    model = "models/gemini-embedding-001"
    dimensions = 768

    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.0] * self.dimensions


ENTRIES = [
    {"code": "39", "level": 1, "name_en": "PLASTICS AND ARTICLES THEREOF"},
    {
        "code": "3923210000",
        "level": 5,
        "name_en": "of polymers of ethylene",
        "supplementary_unit": "шт",
        "ancestors": [
            {"kind": "header", "name_en": "SECTION VII"},
            {"code": "39", "kind": "group", "name_en": "PLASTICS AND ARTICLES THEREOF"},
            {"code": "3923", "kind": "group", "name_en": "Articles for packing:"},
            {"code": "392321", "kind": "group", "name_en": "sacks and bags:"},
        ],
    },
    {
        "code": "3923290000",
        "level": 5,
        "name_en": "of other plastics",
        "ancestors": [
            {"code": "39", "kind": "group", "name_en": "PLASTICS AND ARTICLES THEREOF"},
            {"code": "3923", "kind": "group", "name_en": "Articles for packing:"},
            {"code": "392329", "kind": "group", "name_en": "from other plastics:"},
        ],
    },
]


@pytest.fixture
def artifact(tmp_path: Path) -> Path:
    directory = tmp_path / "nomenclature"
    directory.mkdir()
    (directory / "entries.jsonl").write_text(
        "\n".join(json.dumps(entry, ensure_ascii=False) for entry in ENTRIES),
        encoding="utf-8",
    )
    (directory / "headings.json").write_text(
        json.dumps({"3923": "Articles for the conveyance or packing of goods:"}),
        encoding="utf-8",
    )
    return directory


def store(artifact: Path, points: list[Point]) -> tuple[NomenclatureStore, FakeQdrant]:
    client = FakeQdrant(points)
    return (
        NomenclatureStore(
            artifact_dir=artifact,
            qdrant_client=client,
            collection="atg_aa_codes",
            embedder=FakeEmbedder(),
        ),
        client,
    )


def point(code: str, score: float) -> Point:
    return Point(
        payload={"code": code, "level": 5, "p2": code[:2], "p4": code[:4]}, score=score
    )


def test_a_missing_artifact_is_a_construction_failure_not_a_runtime_one(tmp_path):
    with pytest.raises(ArtifactUnavailableError, match="incomplete"):
        NomenclatureStore(
            artifact_dir=tmp_path,
            qdrant_client=FakeQdrant([]),
            collection="atg_aa_codes",
            embedder=FakeEmbedder(),
        )


def test_every_retrieved_candidate_survives_however_low_it_scored(artifact):
    subject, _ = store(
        artifact, [point("3923210000", 0.83), point("3923290000", 0.02)]
    )
    outcome = subject.search("a — b — c")
    assert [c.code for c in outcome.candidates] == ["3923210000", "3923290000"]


def test_duplicates_collapse_by_code_keeping_the_highest_similarity(artifact):
    subject, _ = store(
        artifact,
        [point("3923210000", 0.61), point("3923210000", 0.88), point("3923290000", 0.7)],
    )
    outcome = subject.search("a — b — c")
    assert [(c.code, c.similarity) for c in outcome.candidates] == [
        ("3923210000", 0.88),
        ("3923290000", 0.7),
    ]


def test_candidates_come_back_in_descending_similarity(artifact):
    subject, _ = store(
        artifact, [point("3923290000", 0.4), point("3923210000", 0.9)]
    )
    outcome = subject.search("a — b — c")
    assert [c.similarity for c in outcome.candidates] == [0.9, 0.4]


def test_the_limit_is_applied_after_the_deduplication(artifact):
    subject, _ = store(
        artifact, [point("3923210000", 0.9), point("3923290000", 0.8)]
    )
    outcome = subject.search("a — b — c", limit=1)
    assert [c.code for c in outcome.candidates] == ["3923210000"]


class TestScoping:
    def test_a_four_digit_scope_filters_on_the_payload_field_that_indexes_it(self, artifact):
        subject, client = store(artifact, [point("3923210000", 0.9)])
        subject.search("a — b — c", prefixes=["3923"])
        keys = [condition.key for condition in client.filters[0].must]
        assert keys == ["level", "p4"]

    def test_a_two_digit_scope_uses_the_two_digit_field(self, artifact):
        subject, client = store(artifact, [point("3923210000", 0.9)])
        subject.search("a — b — c", prefixes=["39"])
        assert [condition.key for condition in client.filters[0].must] == ["level", "p2"]

    def test_an_unscoped_search_still_restricts_to_leaves(self, artifact):
        subject, client = store(artifact, [point("3923210000", 0.9)])
        outcome = subject.search("a — b — c")
        assert [condition.key for condition in client.filters[0].must] == ["level"]
        assert outcome.scope == "unfiltered"

    def test_prefixes_of_mixed_widths_have_no_single_field_and_are_refused(self, artifact):
        subject, _ = store(artifact, [])
        with pytest.raises(ValueError, match="share a width"):
            subject.search("a — b — c", prefixes=["39", "3923"])


def test_a_retrieved_code_the_tree_does_not_know_is_counted_not_hidden(artifact):
    subject, _ = store(artifact, [point("3923210000", 0.9), point("9999999999", 0.8)])
    outcome = subject.search("a — b — c")
    assert outcome.dropped_unknown_codes == 1
    assert [c.code for c in outcome.candidates] == ["3923210000"]


def test_a_candidate_renders_as_its_full_path_not_its_leaf_name(artifact):
    subject, _ = store(artifact, [point("3923210000", 0.9)])
    rendered = subject.search("a — b — c").candidates[0].render()
    assert rendered.startswith("3923210000 — ")
    assert "PLASTICS AND ARTICLES THEREOF" in rendered
    assert "sacks and bags" in rendered
    assert rendered.endswith("of polymers of ethylene")


class TestMenus:
    def test_the_heading_menu_comes_from_the_title_map_not_from_the_entries(self, artifact):
        subject, _ = store(artifact, [])
        assert subject.heading_menu(["39"]) == [
            ("3923", "Articles for the conveyance or packing of goods:")
        ]

    def test_the_subheading_menu_is_derived_from_the_leaves_own_ancestry(self, artifact):
        subject, _ = store(artifact, [])
        assert subject.subheading_menu(["3923"]) == [
            ("392321", "sacks and bags:"),
            ("392329", "from other plastics:"),
        ]

    def test_a_chapter_with_no_note_says_so_explicitly(self, artifact):
        subject, _ = store(artifact, [])
        assert subject.chapter_note("39") == "(none)"


class TestExistence:
    @pytest.mark.parametrize(
        "code", ["3923210000", "39232100000", " 3923210000 "]
    )
    def test_the_leaf_form_and_the_filed_national_form_both_exist(self, artifact, code):
        subject, _ = store(artifact, [])
        assert subject.exists(code)

    @pytest.mark.parametrize(
        "code", ["00000000000", "3923", "39232100AB", "9999999999", "39"]
    )
    def test_everything_else_does_not(self, artifact, code):
        subject, _ = store(artifact, [])
        assert not subject.exists(code)
