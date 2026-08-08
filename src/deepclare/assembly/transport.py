"""Dossier 03 §4.6 — transport consistency.

One transport-means record per distinct vehicle, and the mode code read off how many there
are: two plates or more is a tractor with a trailer, one plate is a solo truck, and no
consignment note at all defaults to road. All three are guesses — the corpus splits the
road codes by rig and nothing in the documents states the rig directly.

The two blocks a declaration carries, departure/arrival and border, are **identical**. That
is not a simplification: 13 of 13 corpus files write them the same and no counter-example
exists.

One number in here is contested and the contest is recorded rather than hidden. Under mode
31 the accepted filings state twice as many vehicles as they carry vehicle records, while
the system this replaces stated the plate count one-for-one — a combination that appears in
**zero** accepted filings. Dossier 03's own precedence rule says the filings are the ground
truth where they disagree with anything else, so the filings decide it here.
"""

from __future__ import annotations

from deepclare.assembly.countries import detect_in_party
from deepclare.assembly.tables import ReferenceTables
from deepclare.assembly.trace import COMPUTED, DEFAULTED, Review, derived
from deepclare.domain import (
    ConsignmentNote,
    Traced,
    TransportBlock,
    TransportMeansRecord,
)

SOLO_TRUCK = "30"
TRACTOR_AND_TRAILER = "31"
ROAD_DEFAULT = TRACTOR_AND_TRAILER
"""What is filed with no consignment note to read a rig from. Road is the only mode this
product has ever seen, and 31 is the corpus mode."""


def resolve_transport(
    note: ConsignmentNote | None, tables: ReferenceTables, review: Review
) -> TransportBlock:
    """The one transport block, which both legs of the journey then share."""
    plates = tuple(note.vehicle_plates) if note is not None else ()
    nationality = _carrier_nationality(note, tables)
    vehicles = tuple(
        TransportMeansRecord(identifier=plate, nationality_country_code=nationality)
        for plate in plates
    )

    mode, rule, confidence = _mode(plates)
    if not plates:
        review.guess(
            "transport mode",
            "No vehicle plate was read"
            + (
                ", so the road tractor-and-trailer code was filed as the default."
                if note is not None
                else " because there is no consignment note, so the road "
                "tractor-and-trailer code was filed as the default."
            ),
            remedy="The vehicle plates from the consignment note.",
        )
    else:
        review.guess(
            "transport mode",
            f"{len(plates)} distinct plate(s) were read, which reads as "
            + (
                "a tractor with a trailer."
                if mode == TRACTOR_AND_TRAILER
                else "a solo truck."
            )
            + " The rig is inferred from the number of plates; no document states it.",
        )

    return TransportBlock(
        mode_code=derived(mode, rule, confidence),
        vehicles=vehicles,
        vehicle_quantity=derived(
            _vehicle_quantity(mode, len(vehicles)),
            "vehicle count as the accepted filings state it: doubled under mode 31",
            COMPUTED,
        )
        if vehicles
        else None,
    )


def _mode(plates: tuple[Traced[str], ...]) -> tuple[str, str, float]:
    if len(plates) >= 2:
        return (
            TRACTOR_AND_TRAILER,
            "two or more distinct plates read as a tractor with a trailer",
            COMPUTED,
        )
    if len(plates) == 1:
        return SOLO_TRUCK, "one plate read as a solo truck", COMPUTED
    return ROAD_DEFAULT, "road default, no consignment note to read a rig from", DEFAULTED


def _vehicle_quantity(mode: str, records: int) -> int:
    """How many vehicles the declaration states, against how many it lists.

    Under mode 31 the accepted filings state two per record — a tractor and its trailer
    share one plate on the note. Under mode 30 the two agree.
    """
    return records * 2 if mode == TRACTOR_AND_TRAILER else records


def _carrier_nationality(
    note: ConsignmentNote | None, tables: ReferenceTables
) -> Traced[str] | None:
    """The carrier's country, detected from its address or its name."""
    if note is None:
        return None
    detected = detect_in_party(note.carrier, tables)
    if detected is None:
        return None
    entry, where = detected
    return derived(
        entry.code, f"carrier nationality detected from the carrier {where}", COMPUTED
    )
