"""The element tree and the serializer: absence, and the physical shape of the file."""

from __future__ import annotations

from deepclare.filing.document import Element, container, leaf, serialize, walk


def test_an_absent_value_produces_no_element_at_all() -> None:
    assert leaf("GoodsDescription", None) is None


def test_an_empty_or_blank_value_produces_no_element_either() -> None:
    assert leaf("GoodsDescription", "") is None
    assert leaf("GoodsDescription", "   ") is None


def test_a_container_whose_children_are_all_absent_is_itself_absent() -> None:
    assert container("Address", [None, None]) is None


def test_a_container_keeps_only_the_children_that_exist() -> None:
    block = container("Address", [None, leaf("CountryCode", "AM"), None])
    assert block is not None
    assert [child.name for child in block.children] == ["CountryCode"]


def test_the_prolog_is_double_quoted_uppercase_and_the_root_shares_its_line() -> None:
    xml = serialize(Element(name="ESADout_CU", children=(Element(name="A", text="1"),)))
    first = xml.split("\n")[0]
    assert first == '<?xml version="1.0" encoding="UTF-8"?><ESADout_CU>'


def test_indentation_is_two_spaces_per_level_and_one_element_per_line() -> None:
    tree = Element(
        name="Root",
        children=(
            Element(name="Outer", children=(Element(name="Inner", text="x"),)),
        ),
    )
    assert serialize(tree).split("\n")[1:4] == [
        "  <Outer>",
        "    <Inner>x</Inner>",
        "  </Outer>",
    ]


def test_nothing_is_ever_written_self_closing() -> None:
    xml = serialize(Element(name="Root", children=(Element(name="Leaf", text=""),)))
    assert "/>" not in xml


def test_markup_characters_in_text_are_escaped() -> None:
    xml = serialize(Element(name="Root", text="A & B < C"))
    assert "A &amp; B &lt; C" in xml


def test_walk_reports_path_parent_and_depth() -> None:
    tree = Element(
        name="Root", children=(Element(name="Outer", children=(Element(name="In", text="x"),)),)
    )
    seen = [(item.path, item.parent_name, item.depth) for item in walk(tree)]
    assert seen == [
        ("Root", None, 1),
        ("Root/Outer", "Root", 2),
        ("Root/Outer/In", "Outer", 3),
    ]
