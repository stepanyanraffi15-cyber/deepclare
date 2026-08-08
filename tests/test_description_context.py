"""The per-line context: the script a line is written in, and what its siblings say.

Both are deterministic and neither costs a model call. Nothing here touches the network.
"""

from __future__ import annotations

from decimal import Decimal

from deepclare.description import (
    MAX_SIBLINGS,
    build_line_contexts,
    detect_source_language,
)
from deepclare.domain import (
    InvoiceGoodsLine,
    InvoiceRecord,
    LineEnrichment,
    Provenance,
    SourceLanguage,
    Traced,
    ValueOrigin,
)

EXTRACTED = Provenance(origin=ValueOrigin.EXTRACTED, source_document_id="invoice.pdf")


def traced(value: str) -> Traced[str]:
    return Traced[str](value=value, provenance=EXTRACTED)


def line(line_id: str, description: str, **fields: object) -> InvoiceGoodsLine:
    return InvoiceGoodsLine(
        line_id=line_id, description=traced(description), **fields
    )


def invoice(*lines: InvoiceGoodsLine) -> InvoiceRecord:
    return InvoiceRecord(source_document_id="invoice.pdf", goods_lines=lines)


def test_each_script_is_recognised_from_one_character() -> None:
    assert detect_source_language("ԳԻՊՍ") is SourceLanguage.ARMENIAN
    assert detect_source_language("ЦЕМЕНТ М500") is SourceLanguage.RUSSIAN
    assert detect_source_language("کابل برق") is SourceLanguage.FARSI_ARABIC
    assert detect_source_language("RAY TAŞIYICI") is SourceLanguage.TURKISH
    assert detect_source_language("CABLE NYY-J 3X2.5MM2") is SourceLanguage.ENGLISH_LATIN


def test_turkish_is_decided_only_by_its_own_diacritics() -> None:
    """ö, ü and ç are too common in other Latin languages to be decisive."""
    assert detect_source_language("SCHÜTZ MÖBEL FRANÇAIS") is (
        SourceLanguage.ENGLISH_LATIN
    )
    for diacritic in "İıŞşĞğ":
        assert detect_source_language(f"PART {diacritic}") is SourceLanguage.TURKISH


def test_precedence_decides_not_position() -> None:
    """A Latin brand inside Armenian text is ordinary; the reverse is not."""
    assert detect_source_language("ՄԱԼՈՒԽ NYY-J") is SourceLanguage.ARMENIAN
    assert detect_source_language("NYY-J ՄԱԼՈՒԽ") is SourceLanguage.ARMENIAN
    assert detect_source_language("КАБЕЛЬ ԳԻՊՍ") is SourceLanguage.ARMENIAN
    assert detect_source_language("KABLO КАБЕЛЬ") is SourceLanguage.RUSSIAN


def test_an_empty_name_is_latin_by_default() -> None:
    assert detect_source_language("") is SourceLanguage.ENGLISH_LATIN


def test_one_context_per_line_in_printed_order() -> None:
    contexts = build_line_contexts(
        invoice(line("1", "GYPS"), line("2", "CEMENT"), line("3", "CABLE"))
    )
    assert [context.line_id for context in contexts] == ["1", "2", "3"]
    assert [context.goods_name for context in contexts] == ["GYPS", "CEMENT", "CABLE"]


def test_the_line_carries_its_own_language_not_the_invoice_s() -> None:
    contexts = build_line_contexts(invoice(line("1", "GYPS"), line("2", "RAY TAŞIYICI")))
    assert contexts[0].source_language is SourceLanguage.ENGLISH_LATIN
    assert contexts[1].source_language is SourceLanguage.TURKISH


def test_the_siblings_are_the_other_lines_in_printed_order() -> None:
    contexts = build_line_contexts(
        invoice(line("1", "A"), line("2", "B"), line("3", "C"))
    )
    assert contexts[1].sibling_names == ("A", "C")
    assert contexts[0].sibling_names == ("B", "C")


def test_a_single_line_invoice_has_no_siblings() -> None:
    (context,) = build_line_contexts(invoice(line("1", "GYPS")))
    assert context.sibling_names == ()


def test_the_nearest_siblings_survive_the_budget() -> None:
    """An invoice groups a family together, so the neighbours are the ones that say
    what a line is."""
    lines = [line(str(n), f"ITEM {n}") for n in range(1, 41)]
    contexts = build_line_contexts(invoice(*lines), max_siblings=4)
    assert contexts[19].sibling_names == ("ITEM 18", "ITEM 19", "ITEM 21", "ITEM 22")
    assert contexts[0].sibling_names == ("ITEM 2", "ITEM 3", "ITEM 4", "ITEM 5")


def test_the_default_budget_is_ten_siblings() -> None:
    lines = [line(str(n), f"ITEM {n}") for n in range(1, 41)]
    contexts = build_line_contexts(invoice(*lines))
    assert len(contexts[19].sibling_names) == MAX_SIBLINGS


def test_a_long_sibling_name_is_cut_and_the_cut_is_visible() -> None:
    long_name = "TERMINAL BLOCK " * 10
    contexts = build_line_contexts(
        invoice(line("1", "GYPS"), line("2", long_name)), sibling_excerpt_chars=20
    )
    (sibling,) = contexts[0].sibling_names
    assert sibling == "TERMINAL BLOCK TERMI…"
    assert len(sibling.rstrip("…")) == 20


def test_evidence_reaches_the_line_it_names() -> None:
    contexts = build_line_contexts(
        invoice(line("1", "GYPS"), line("2", "CABLE")),
        [
            LineEnrichment(
                line_id="2",
                grounding_facts=(traced("Use: electrical circuit protection"),),
                material=traced("copper"),
            )
        ],
    )
    assert contexts[0].grounding_facts == ()
    assert contexts[0].material is None
    assert contexts[1].grounding_facts == ("Use: electrical circuit protection",)
    assert contexts[1].material == "copper"


def test_an_enrichment_for_a_line_that_does_not_exist_is_dropped() -> None:
    contexts = build_line_contexts(
        invoice(line("1", "GYPS")),
        [LineEnrichment(line_id="7", material=traced("steel"))],
    )
    assert contexts[0].material is None


def test_two_enrichments_for_one_line_leave_the_last_one_standing() -> None:
    contexts = build_line_contexts(
        invoice(line("1", "GYPS")),
        [
            LineEnrichment(line_id="1", material=traced("steel")),
            LineEnrichment(line_id="1", material=traced("plastic")),
        ],
    )
    assert contexts[0].material == "plastic"


def test_the_context_carries_the_hints_and_withholds_the_figures() -> None:
    """Quantity, package counts, dimensions and the printed code are omitted rather
    than forbidden: a figure the model cannot see is one it cannot duplicate."""
    context, = build_line_contexts(
        invoice(
            line(
                "1",
                "CABLE NYY-J 3X2.5MM2",
                unit=traced("M"),
                unit_price=Traced[Decimal](value=Decimal("1.20"), provenance=EXTRACTED),
                trade_name=traced("NYY-J"),
                quantity=Traced[Decimal](value=Decimal("300"), provenance=EXTRACTED),
                package_count=Traced[Decimal](value=Decimal("6"), provenance=EXTRACTED),
                dimensions=traced("3X2.5MM2"),
                printed_customs_code=traced("8544491000"),
            )
        )
    )
    assert context.unit == "M"
    assert context.unit_price == Decimal("1.20")
    assert context.trade_name == "NYY-J"
    carried = set(context.model_dump())
    assert not carried & {
        "quantity",
        "package_count",
        "dimensions",
        "printed_customs_code",
        "gross_weight",
        "net_weight",
    }
