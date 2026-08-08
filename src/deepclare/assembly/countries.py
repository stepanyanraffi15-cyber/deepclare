"""Countries, and the rule that a code and its name are never written apart.

Dossier 03 §4.5: the portal keys these fields on the **code** and renders the name from
it. A name written without its code imports successfully and the value is simply not there
afterwards — no rejection, no message, nothing. That is why every country here is built as
a pair or not at all, and why a country whose Armenian name is unknown produces no pair
rather than half of one.

Detection over free text follows dossier 11 §3.4: uppercased, word-boundary, aliases of at
least three characters, longest alias wins. A two-letter code is resolved only when it is
the entire field, because two-letter tokens are far too common inside an address to scan
for.
"""

from __future__ import annotations

from deepclare.assembly.tables import CountryEntry, ReferenceTables
from deepclare.assembly.trace import COMPUTED, Review, VERBATIM, derived
from deepclare.domain import CodedValue, Party, Traced


def coded_country(entry: CountryEntry, rule: str, confidence: float) -> CodedValue | None:
    """A country as a code and name pair, or nothing at all.

    An entry with no attested Armenian name yields nothing: the pair is the unit of
    filing, and writing the code alone would leave the portal rendering a name we could
    not check while writing the name alone loses the value silently.
    """
    if entry.name_hy is None:
        return None
    return CodedValue(
        code=derived(entry.code, rule, confidence),
        name=derived(entry.name_hy, rule, confidence),
    )


def line_origin(
    printed_line_origin: Traced[str] | None,
    invoice_origin: Traced[str] | None,
    tables: ReferenceTables,
    review: Review,
    line_id: str,
) -> CodedValue | None:
    """Box 34 — the line's own origin, else the invoice's overall origin."""
    for source, printed, rule, confidence in (
        ("this line", printed_line_origin, "origin printed on the invoice line", VERBATIM),
        (
            "the invoice",
            invoice_origin,
            "origin stated for the invoice as a whole",
            COMPUTED,
        ),
    ):
        if printed is None:
            continue
        entry = tables.detect_country(printed.value)
        if entry is None:
            review.omitted(
                "line origin country",
                f"{source.capitalize()} states an origin of {printed.value!r}, which "
                "matches no country this product knows, so box 34 was left out. Both "
                "halves go together: a name filed without its code is dropped on import "
                "with no message.",
                line_id=line_id,
                remedy="The country of origin, as its two-letter code.",
            )
            return None
        pair = coded_country(entry, rule, confidence)
        if pair is None:
            review.omitted(
                "line origin country",
                f"{source.capitalize()} states an origin of {printed.value!r}, read as "
                f"{entry.code}. No accepted filing gives the Armenian name for that code, "
                "and the code and the name are filed together or not at all, so box 34 "
                "was left out.",
                line_id=line_id,
                remedy=f"The Armenian customs name for {entry.code}.",
            )
            return None
        return pair

    review.omitted(
        "line origin country",
        "Neither the line nor the invoice states an origin, so box 34 was left out.",
        line_id=line_id,
        remedy="The country of origin for these goods.",
    )
    return None


def detect_in_party(
    party: Party | None, tables: ReferenceTables
) -> tuple[CountryEntry, str] | None:
    """The country a party's address names, else the one its own name names.

    The name is scanned as well as the address because foreign consignors routinely carry
    their country inside the company name and nowhere else.
    """
    if party is None:
        return None
    for where, field in (("address", party.address), ("name", party.name)):
        entry = tables.detect_country(field.value if field is not None else None)
        if entry is not None:
            return entry, where
    return None


def trade_country(
    seller: Party | None,
    consignment_sender: Party | None,
    invoice_origin: Traced[str] | None,
    tables: ReferenceTables,
) -> tuple[CountryEntry, str] | None:
    """Where the trade was done, from whichever field names a country first.

    Dossier 03 §5.2 fixes the order: the seller's address, then the seller's name, then
    the consignment note's sender address, then its name, then the invoice's origin.
    """
    for who, party in (("seller", seller), ("consignment-note sender", consignment_sender)):
        found = detect_in_party(party, tables)
        if found is not None:
            entry, where = found
            return entry, f"{who} {where}"
    entry = tables.detect_country(invoice_origin.value if invoice_origin else None)
    return None if entry is None else (entry, "invoice origin")
