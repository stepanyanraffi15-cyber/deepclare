"""The page-type classifier's two deterministic halves: what goes to the model, and
what comes back.

Neither touches the network. The call between them is exercised by hand against a real
model in `tests/check_page_classification.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deepclare.domain import DocumentRole, PageClass
from deepclare.intake import PageTypeClassifier, RenderedPage
from deepclare.reading import (
    ClassifyPageType,
    VisionPageTypeClassifier,
    page_manifest,
    verdicts_from_answer,
)
from deepclare.reading.schemas import ClassifiedPage

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def page(
    document_id: str = "doc1",
    page_number: int = 1,
    hint: DocumentRole = DocumentRole.INVOICE,
) -> RenderedPage:
    return RenderedPage(
        source_document_id=document_id,
        source_page_number=page_number,
        role_hint=hint,
        image=b"\x89PNG\r\n\x1a\n",
        width_px=1654,
        height_px=2339,
        dpi=200,
    )


def answer(*verdicts: tuple[int, str]) -> ClassifyPageType:
    return ClassifyPageType(
        verdicts=[
            ClassifiedPage(page=number, page_type=label) for number, label in verdicts
        ]
    )


# --- the manifest, which is what the prompt's placeholder had no producer for ----


def test_the_manifest_numbers_positions_over_the_batch_not_the_source_file() -> None:
    """Two files whose first pages are both page 1 are positions 1 and 2 here."""
    manifest = json.loads(
        page_manifest(
            [page("doc1", 1), page("doc2", 1, DocumentRole.CONSIGNMENT_NOTE)]
        )
    )
    assert [entry["page"] for entry in manifest] == [1, 2]


def test_the_manifest_carries_each_page_s_role_hint() -> None:
    manifest = json.loads(
        page_manifest(
            [
                page("doc1", 1),
                page("doc1", 2),
                page("doc2", 1, DocumentRole.CATALOG_SPEC),
            ]
        )
    )
    assert [entry["hint"] for entry in manifest] == [
        "invoice",
        "invoice",
        "catalog_spec",
    ]


def test_the_manifest_has_one_entry_per_attached_page() -> None:
    pages = [page("doc1", n) for n in (1, 2, 3, 4)]
    assert len(json.loads(page_manifest(pages))) == len(pages)


def test_the_rendered_prompt_carries_the_manifest_and_the_count() -> None:
    from deepclare.prompting import render_prompt

    pages = [page("doc1", 1), page("doc2", 1, DocumentRole.CONSIGNMENT_NOTE)]
    prompt = render_prompt(
        PROMPTS_DIR,
        "classify_page_type",
        {"page_count": str(len(pages)), "page_manifest": page_manifest(pages)},
    )
    assert "{{" not in prompt.text
    assert '"hint": "consignment_note"' in prompt.text
    assert "2 page images are attached" in prompt.text


# --- the answer mapping, which must not improve on what the model said -----------


def test_every_label_maps_onto_the_domain_vocabulary() -> None:
    mapped = verdicts_from_answer(
        answer((1, "invoice"), (2, "consignment_note"), (3, "other"))
    )
    assert [v.page_type for v in mapped] == [
        PageClass.INVOICE,
        PageClass.CONSIGNMENT_NOTE,
        PageClass.OTHER,
    ]


def test_a_missing_verdict_is_not_invented() -> None:
    """The grouper leaves an unanswered page on its hint; padding here would replace a
    real signal with a fabricated one and change nothing about where the page lands."""
    assert [v.page for v in verdicts_from_answer(answer((1, "invoice")))] == [1]


def test_a_repeated_page_is_passed_through_rather_than_deduplicated() -> None:
    mapped = verdicts_from_answer(answer((1, "invoice"), (1, "consignment_note")))
    assert [(v.page, v.page_type) for v in mapped] == [
        (1, PageClass.INVOICE),
        (1, PageClass.CONSIGNMENT_NOTE),
    ]


def test_a_page_numbered_outside_the_batch_is_passed_through() -> None:
    """Range is the grouper's to judge; it knows the batch size and this does not."""
    assert [v.page for v in verdicts_from_answer(answer((9, "invoice")))] == [9]


def test_answer_order_is_preserved() -> None:
    mapped = verdicts_from_answer(answer((3, "other"), (1, "invoice"), (2, "invoice")))
    assert [v.page for v in mapped] == [3, 1, 2]


def test_an_empty_answer_yields_no_verdicts() -> None:
    assert verdicts_from_answer(ClassifyPageType(verdicts=[])) == ()


# --- the shape the provider is asked to answer in --------------------------------


def test_the_answer_schema_carries_no_prose() -> None:
    """A description in a bound schema is prompt text, and prompt text lives in the
    prompt files."""
    schema = json.dumps(ClassifyPageType.model_json_schema())
    assert "description" not in schema


def test_the_answer_schema_admits_exactly_the_three_labels() -> None:
    labels = ClassifyPageType.model_json_schema()["$defs"]["ClassifiedPage"][
        "properties"
    ]["page_type"]["enum"]
    assert sorted(labels) == sorted(c.value for c in PageClass)


# --- the port ---------------------------------------------------------------------


def test_the_implementation_satisfies_the_port_intake_declares() -> None:
    # Neither argument is touched: construction only stores them.
    classifier = VisionPageTypeClassifier(model=None, prompts_dir=PROMPTS_DIR)  # type: ignore[arg-type]
    assert isinstance(classifier, PageTypeClassifier)


def test_classifying_an_empty_batch_is_a_caller_error() -> None:
    classifier = VisionPageTypeClassifier(model=None, prompts_dir=PROMPTS_DIR)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        classifier.classify([])
