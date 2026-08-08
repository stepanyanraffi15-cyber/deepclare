"""The conformance check, judged on documents built to break one rule each.

Every case here is a defect the check has to catch before the file leaves, because the
external system reports none of them in a way anyone can act on.
"""

from __future__ import annotations

from filing_fixtures import declaration, traced

from deepclare.domain.declaration import Organization, PostalAddress
from deepclare.filing import contract as c
from deepclare.filing.conformance import RuleStatus, check
from deepclare.filing.document import Element, serialize
from deepclare.filing.writer import write_declaration


def outcome(result: object, rule: str):
    return next(item for item in result.outcomes if item.rule == rule)


def judge(root: Element):
    return check(root, serialize(root))


def swap(root: Element, container_name: str, first: str, second: str) -> Element:
    """Return the tree with two children of one container exchanged."""
    if root.name == container_name:
        names = [child.name for child in root.children]
        left, right = names.index(first), names.index(second)
        children = list(root.children)
        children[left], children[right] = children[right], children[left]
        return root.model_copy(update={"children": tuple(children)})
    return root.model_copy(
        update={
            "children": tuple(swap(child, container_name, first, second) for child in root.children)
        }
    )


def replace_text(root: Element, element_name: str, text: str) -> Element:
    if root.name == element_name:
        return root.model_copy(update={"text": text})
    return root.model_copy(
        update={"children": tuple(replace_text(child, element_name, text) for child in root.children)}
    )


def drop(root: Element, element_name: str) -> Element:
    children = tuple(
        drop(child, element_name) for child in root.children if child.name != element_name
    )
    return root.model_copy(update={"children": children})


BASE = write_declaration(declaration()).tree


def test_a_clean_document_passes_every_decidable_rule() -> None:
    result = judge(BASE)
    assert result.conforms
    assert not result.filable  # names and namespaces are still unconfirmed


def test_packaging_children_in_the_wrong_order_are_caught() -> None:
    broken = swap(BASE, c.GOODS_PACKAGING, c.PACKAGE_QUANTITY, c.PACKAGE_TYPE_CODE)
    order = outcome(judge(broken), "child-order")
    assert order.status is RuleStatus.FAIL
    assert order.findings[0].path.endswith(c.PACKAGE_QUANTITY)


def test_a_goods_child_out_of_sequence_is_caught() -> None:
    broken = swap(BASE, c.GOODS_ITEM, c.GROSS_WEIGHT, c.COMMODITY_CODE)
    assert outcome(judge(broken), "child-order").status is RuleStatus.FAIL


def test_a_placeholder_in_a_typed_leaf_is_caught() -> None:
    broken = replace_text(BASE, c.COMMODITY_CODE, c.ABSENT_ORGANIZATION_NAME)
    confinement = outcome(judge(broken), "placeholder-confinement")
    assert confinement.status is RuleStatus.FAIL
    assert confinement.findings[0].value == "-"


def test_a_placeholder_in_the_permitted_organization_name_is_not_a_violation() -> None:
    permitted = replace_text(BASE, c.ORGANIZATION_NAME, c.ABSENT_ORGANIZATION_NAME)
    assert outcome(judge(permitted), "placeholder-confinement").status is RuleStatus.PASS


def test_an_empty_element_is_checked_rather_than_exempted() -> None:
    broken = replace_text(BASE, c.GOODS_DESCRIPTION, "   ")
    empties = outcome(judge(broken), "no-empty-elements")
    assert empties.status is RuleStatus.FAIL
    assert empties.findings[0].path.endswith(c.GOODS_DESCRIPTION)


def test_a_decimal_with_trailing_zeros_is_caught() -> None:
    broken = replace_text(BASE, c.GROSS_WEIGHT, "10.00")
    facets = outcome(judge(broken), "leaf-facets")
    assert facets.status is RuleStatus.FAIL
    assert facets.findings[0].value == "10.00"


def test_a_thousands_separator_is_caught() -> None:
    broken = replace_text(BASE, c.INVOICED_COST, "1,250.5")
    assert outcome(judge(broken), "leaf-facets").status is RuleStatus.FAIL


def test_a_commodity_code_of_the_wrong_digit_count_is_caught() -> None:
    broken = replace_text(BASE, c.COMMODITY_CODE, "3923290000")
    widths = outcome(judge(broken), "fixed-width-codes")
    assert widths.status is RuleStatus.FAIL
    assert widths.findings[0].value == "3923290000"


def test_a_unit_code_that_lost_its_zero_padding_is_caught() -> None:
    broken = replace_text(BASE, c.MEASURE_UNIT_CODE, "55")
    assert outcome(judge(broken), "fixed-width-codes").status is RuleStatus.FAIL


def test_the_preference_marker_written_as_digits_is_caught() -> None:
    broken = replace_text(BASE, c.PREFERENCE_TAX, "00")
    marker = outcome(judge(broken), "preference-marker")
    assert marker.status is RuleStatus.FAIL
    assert "not [48, 48]" in marker.findings[0].detail


def test_a_country_name_written_without_its_code_is_caught() -> None:
    broken = drop(BASE, c.ORIGIN_COUNTRY_CODE)
    pairing = outcome(judge(broken), "code-name-pairing")
    assert pairing.status is RuleStatus.FAIL
    assert pairing.findings[0].path.endswith(c.ORIGIN_COUNTRY_NAME)


def test_the_shipment_origin_name_is_not_treated_as_half_a_pair() -> None:
    # Box 16 has no code half at all. Keying the pair on the element name alone would
    # report a violation on every document ever written.
    assert outcome(judge(BASE), "code-name-pairing").status is RuleStatus.PASS


def test_a_goods_line_without_a_quantity_block_is_caught() -> None:
    broken = drop(BASE, c.SUPPLEMENTARY_QUANTITY)
    hang = outcome(judge(broken), "goods-quantity-present")
    assert hang.status is RuleStatus.FAIL
    assert "hangs" in hang.findings[0].detail


def test_a_goods_count_that_disagrees_with_the_blocks_is_caught() -> None:
    broken = replace_text(BASE, c.TOTAL_GOODS_NUMBER, "3")
    assert outcome(judge(broken), "goods-numbering").status is RuleStatus.FAIL


def test_an_element_the_portal_owns_is_caught_if_it_is_ever_written() -> None:
    broken = BASE.model_copy(
        update={"children": BASE.children + (Element(name="RegNumberDoc", text="x"),)}
    )
    assert outcome(judge(broken), "never-emitted").status is RuleStatus.FAIL


def test_a_leaf_with_no_declared_facet_is_reported_rather_than_skipped() -> None:
    broken = BASE.model_copy(
        update={"children": BASE.children + (Element(name="SomethingNew", text="7"),)}
    )
    facets = outcome(judge(broken), "leaf-facets")
    assert facets.status is RuleStatus.FAIL
    assert "no facet" in facets.findings[0].detail


def test_nothing_to_check_fails_rather_than_passing_quietly() -> None:
    empty = Element(name=c.ROOT, children=(Element(name=c.TOTAL_GOODS_NUMBER, text="0"),))
    result = judge(empty)
    assert outcome(result, "goods-quantity-present").status is RuleStatus.FAIL
    assert outcome(result, "fixed-width-codes").status is RuleStatus.FAIL
    assert outcome(result, "preference-marker").status is RuleStatus.FAIL


def test_the_rate_element_is_resolved_by_parent_and_not_by_name() -> None:
    inside_preferences = c.facet_for(c.PREFERENCES, c.PREFERENCE_RATE)
    assert inside_preferences is not None
    assert inside_preferences.fixed == c.NO_PREFERENCE
    assert c.facet_for("SomePaymentBlock", c.PREFERENCE_RATE) is None


def test_a_minified_document_fails_the_serialization_shape() -> None:
    xml = serialize(BASE).replace("\n", "")
    assert check(BASE, xml).failures


def test_the_unwritten_shipment_cost_elements_stay_visible_as_unconfirmed() -> None:
    costs = outcome(judge(BASE), "shipment-cost-elements")
    assert costs.status is RuleStatus.UNCONFIRMED
    assert "TotalCustCost" in costs.detail


def test_an_over_long_description_is_reported_without_being_failed() -> None:
    broken = replace_text(BASE, c.GOODS_DESCRIPTION, "Ա" * 300)
    result = judge(broken)
    assert outcome(result, "advisory-lengths").status is RuleStatus.UNCONFIRMED
    assert result.conforms


def test_an_over_long_street_address_is_a_hard_failure() -> None:
    # The writer truncates, so this can only arise from a tree built by hand. It is
    # checked anyway: one over-long leaf rejects the whole file, naming no field.
    with_address = write_declaration(
        declaration(
            importer=Organization(
                name=traced("ԱՐԱՐԱՏ ՍՊԸ"),
                tax_code=traced("01234567"),
                address=PostalAddress(street_house=traced("ԵՐԵՎԱՆ")),
            )
        )
    ).tree
    broken = replace_text(with_address, c.STREET_HOUSE, "Ա" * 60)
    facets = outcome(judge(broken), "leaf-facets")
    assert facets.status is RuleStatus.FAIL
    assert "rejects the whole file" in facets.findings[0].detail


def test_the_report_names_every_rule_and_its_findings() -> None:
    text = judge(swap(BASE, c.GOODS_PACKAGING, c.PACKAGE_QUANTITY, c.PACKAGE_TYPE_CODE)).report()
    assert "child-order" in text
    assert "out of sequence" in text
