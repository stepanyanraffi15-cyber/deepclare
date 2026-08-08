"""M13: the ordering rule, the item-to-value join, the flags, and the defect checks.

Nothing here touches the network, and nothing here needs a producing module to exist:
the review surface is defined against the domain vocabulary alone.
"""

from __future__ import annotations

from deepclare.domain import (
    Confidence,
    DocumentRegion,
    Provenance,
    ReviewItem,
    ReviewKind,
    Traced,
    ValueOrigin,
)
from deepclare.review import (
    CONSEQUENCE_ORDER,
    ReviewFlags,
    build_report,
    render_report,
    reported,
)

EXTRACTED = Provenance(
    origin=ValueOrigin.EXTRACTED,
    source_document_id="invoice.pdf",
    region=DocumentRegion(page_number=1),
    stage="reading",
)
DERIVED = Provenance(origin=ValueOrigin.DERIVED, rule="distributed by quantity share",
                     stage="assembly")
GENERATED = Provenance(origin=ValueOrigin.GENERATED, prompt_name="write_description",
                       stage="description")
SUPPLIED = Provenance(origin=ValueOrigin.SUPPLIED, supplied_by="declarant profile")
CONSTANT = Provenance(origin=ValueOrigin.CONSTANT)


def item(
    kind: ReviewKind, concept: str, line_id: str | None = None, remedy: str | None = None
) -> ReviewItem:
    return ReviewItem(
        kind=kind, concept=concept, detail="what happened", line_id=line_id,
        remedy=remedy,
    )


def value(
    concept: str,
    provenance: Provenance = EXTRACTED,
    confidence: Confidence = Confidence(extraction=0.9),
    line_id: str | None = None,
    shown: str = "x",
):
    return reported(
        concept,
        Traced[str](value=shown, provenance=provenance, confidence=confidence),
        line_id,
    )


def concepts_in_order(report, line_id: str | None = None) -> list[str]:
    group = next(group for group in report.groups if group.line_id == line_id)
    return [entry.item.concept for entry in group.entries]


def test_kinds_are_ordered_by_consequence_to_the_filed_document() -> None:
    """Wrong is worse than missing: a stand-in outranks an absence outranks a guess."""
    assert CONSEQUENCE_ORDER == (
        ReviewKind.PLACEHOLDER,
        ReviewKind.OMITTED,
        ReviewKind.NEEDS_REVIEW,
        ReviewKind.GUESS,
    )
    report = build_report([
        item(ReviewKind.GUESS, "d"),
        item(ReviewKind.NEEDS_REVIEW, "c"),
        item(ReviewKind.OMITTED, "b"),
        item(ReviewKind.PLACEHOLDER, "a"),
    ])
    assert concepts_in_order(report) == ["a", "b", "c", "d"]


def test_within_one_kind_the_weakest_confidence_is_read_first() -> None:
    report = build_report(
        [item(ReviewKind.GUESS, "strong"), item(ReviewKind.GUESS, "weak")],
        [
            value("strong", confidence=Confidence(extraction=0.95)),
            value("weak", confidence=Confidence(extraction=0.95, derivation=0.2)),
        ],
    )
    assert concepts_in_order(report) == ["weak", "strong"]


def test_an_unassessed_value_sorts_after_the_assessed_ones() -> None:
    """Nothing known is not the same as known to be poor."""
    report = build_report(
        [item(ReviewKind.GUESS, "unassessed"), item(ReviewKind.GUESS, "assessed")],
        [
            value("unassessed", provenance=SUPPLIED, confidence=Confidence()),
            value("assessed", confidence=Confidence(extraction=0.4)),
        ],
    )
    assert concepts_in_order(report) == ["assessed", "unassessed"]


def test_the_shipment_is_read_before_any_line_whatever_it_carries() -> None:
    """A shipment-level value is wrong for every line at once."""
    report = build_report([
        item(ReviewKind.PLACEHOLDER, "line concept", line_id="1"),
        item(ReviewKind.GUESS, "shipment concept"),
    ])
    assert [group.line_id for group in report.groups] == [None, "1"]


def test_lines_are_ordered_by_their_worst_item_then_by_line_number() -> None:
    report = build_report([
        item(ReviewKind.GUESS, "a", line_id="2"),
        item(ReviewKind.GUESS, "a", line_id="10"),
        item(ReviewKind.OMITTED, "a", line_id="7"),
    ])
    assert [group.line_id for group in report.groups] == ["7", "2", "10"]


def test_a_line_with_values_but_no_items_comes_last() -> None:
    report = build_report(
        [item(ReviewKind.GUESS, "a", line_id="9")],
        [value("b", line_id="1")],
    )
    assert [group.line_id for group in report.groups] == ["9", "1"]


def test_an_item_joins_the_value_it_concerns_on_concept_and_line() -> None:
    report = build_report(
        [item(ReviewKind.GUESS, "line gross weight", line_id="1")],
        [
            value("line gross weight", line_id="1", shown="4600"),
            value("line gross weight", line_id="2", shown="1200"),
        ],
    )
    joined = report.groups[0].entries[0].value
    assert joined is not None
    assert (joined.shown, joined.line_id) == ("4600", "1")


def test_an_item_with_no_reported_value_carries_none() -> None:
    """The normal case for an omission: the point is that there is no value."""
    report = build_report([item(ReviewKind.OMITTED, "commodity code", line_id="1")])
    assert report.groups[0].entries[0].value is None


def test_a_producer_that_assessed_nothing_is_named_rather_than_covered_for() -> None:
    report = build_report([], [value("code", confidence=Confidence(validity=0.8))])
    assert len(report.defects) == 1
    defect = report.defects[0]
    assert defect.producing_stage == "reading"
    assert "extraction confidence" in defect.problem
    # And the value is still shown, with the confidence exactly as it arrived.
    shown = report.groups[0].values[0]
    assert shown.confidence == Confidence(validity=0.8)


def test_each_origin_is_judged_against_what_it_promises() -> None:
    report = build_report([], [
        value("read", provenance=EXTRACTED, confidence=Confidence(extraction=0.5)),
        value("computed", provenance=DERIVED, confidence=Confidence(derivation=0.5)),
        value("written", provenance=GENERATED, confidence=Confidence(derivation=0.5)),
        value("profile", provenance=SUPPLIED, confidence=Confidence()),
        value("fixed", provenance=CONSTANT, confidence=Confidence()),
    ])
    assert report.defects == ()

    unassessed = build_report([], [
        value("computed", provenance=DERIVED, confidence=Confidence(extraction=0.9)),
        value("written", provenance=GENERATED, confidence=Confidence()),
    ])
    assert [defect.concept for defect in unassessed.defects] == ["computed", "written"]
    assert all("derivation confidence" in d.problem for d in unassessed.defects)


def test_an_element_name_where_a_concept_belongs_is_a_leak() -> None:
    report = build_report(
        [item(ReviewKind.GUESS, "GoodsTNVEDCode")],
        [value("GoodsItem/GoodsTNVEDCode")],
    )
    assert [defect.concept for defect in report.defects] == [
        "GoodsItem/GoodsTNVEDCode",
        "GoodsTNVEDCode",
    ]
    assert all("element name" in defect.problem for defect in report.defects)
    # The item is still in the report: the operator still has to act on it.
    assert concepts_in_order(report) == ["GoodsTNVEDCode"]


def test_ordinary_domain_wording_is_not_accused() -> None:
    """A false accusation in a report a human trusts is worse than a missed leak."""
    for concept in ("line gross weight", "commodity code", "currency", "CMR", "kg"):
        report = build_report([item(ReviewKind.GUESS, concept)])
        assert report.defects == (), concept


def test_the_flags_summarise_the_line_without_recomputing_it() -> None:
    report = build_report(
        [
            item(ReviewKind.OMITTED, "commodity code", line_id="1",
                 remedy="the fastener type"),
            item(ReviewKind.GUESS, "line gross weight", line_id="1"),
        ],
        [
            value("line gross weight", provenance=DERIVED,
                  confidence=Confidence(derivation=0.5), line_id="1"),
            value("invoice number", line_id="1"),
        ],
    )
    flags = report.groups[0].flags
    assert flags.needs_review is True
    assert flags.most_consequential is ReviewKind.OMITTED
    assert flags.inferred == ("line gross weight",), "read values are not inferred"
    assert [(a.concept, a.rationale, a.remedy) for a in flags.abstentions] == [
        ("commodity code", "what happened", "the fastener type")
    ]


def test_a_line_nobody_raised_anything_about_says_so() -> None:
    report = build_report([], [value("invoice number", line_id="3")])
    flags = report.groups[0].flags
    assert (flags.needs_review, flags.most_consequential, flags.abstentions) == (
        False, None, ()
    )


def test_no_flag_claims_a_value_came_from_a_prior_filing() -> None:
    """The predecessor's one exposed provenance distinction. This product has no reuse
    path, so a flag asserting one would assert something that cannot happen."""
    assert not [name for name in ReviewFlags.model_fields if "reus" in name]


def test_every_kind_is_tallied_including_the_ones_that_did_not_happen() -> None:
    report = build_report([item(ReviewKind.GUESS, "a"), item(ReviewKind.GUESS, "b")])
    assert [(t.kind, t.count) for t in report.tallies] == [
        (ReviewKind.PLACEHOLDER, 0),
        (ReviewKind.OMITTED, 0),
        (ReviewKind.NEEDS_REVIEW, 0),
        (ReviewKind.GUESS, 2),
    ]
    assert report.total_items == 2


def test_an_empty_run_produces_an_empty_report_not_an_error() -> None:
    report = build_report([])
    assert report.groups == () and report.defects == () and report.total_items == 0
    assert "Nothing was raised" in render_report(report)


def test_the_rendered_report_states_its_own_ordering_and_all_three_confidences() -> None:
    report = build_report(
        [item(ReviewKind.GUESS, "line gross weight", line_id="1")],
        [value("line gross weight", provenance=DERIVED,
               confidence=Confidence(derivation=0.55), line_id="1")],
    )
    text = render_report(report)
    assert "wrong is worse than missing" in text
    assert "extraction — · derivation 0.55 · validity —" in text
    assert "distributed by quantity share" in text
    assert max(len(line) for line in text.splitlines()) <= 92
