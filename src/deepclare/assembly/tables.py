"""The curated lookup tables, loaded from `reference_data/` as data.

Dossier 11 §4 lists "reference data trapped in code" as a defect of the design this
product replaces: a table that lives as a Python constant cannot be corrected without a
release. Every table below is a file, and this module is the only thing that reads them.

Two matching rules hold everywhere and are implemented once, here:

* **Aliases are matched uppercased.** The three unit vocabularies alone — Latin invoice
  text, Cyrillic nomenclature abbreviations, Armenian unit words — make case and script
  sensitivity a bug rather than a feature.
* **Free text is matched on word boundaries, longest alias first.** A country alias found
  inside a longer word is not that country, and `SOUTH KOREA` must beat `KOREA`.

Loading is strict. A missing file, a malformed row or a table that has lost its contents
raises at load time, naming the file, because a lookup table that silently reads as empty
turns every resolution into a miss and every miss into an omitted field.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from deepclare.assembly.errors import AssemblyError

# A word boundary that works for Armenian, Cyrillic and Latin alike. `\b` is defined
# against `\w`, which already covers all three under Python's Unicode rules, but an alias
# beginning or ending in punctuation ("P.R. CHINA") has no `\w` at that edge and `\b`
# would then refuse to match. Bounding on "not a word character" instead keeps those.
_BOUNDARY = r"(?<![^\W_])"
_BOUNDARY_AFTER = r"(?![^\W_])"


class UnitEntry(BaseModel):
    """One OKEI unit, its Armenian name, and every string that resolves to it."""

    model_config = ConfigDict(frozen=True)

    okei: str = Field(pattern=r"^[0-9]{3}$")
    name_hy: str = Field(min_length=1)
    aliases: tuple[str, ...] = Field(min_length=1)


class PackingEntry(BaseModel):
    """One UN/ECE packing code and the words that resolve to it."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(min_length=1)
    aliases: tuple[str, ...] = Field(min_length=1)


class CountryEntry(BaseModel):
    """One country: its ISO-2 code, its Armenian customs name, its printed aliases."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(pattern=r"^[A-Z]{2}$")
    name_hy: str | None = None
    """None where no accepted filing attests an Armenian name. The code still routes;
    the code+name pair is simply never written."""

    aliases: tuple[str, ...] = ()


class BorderOffice(BaseModel):
    """A land crossing: the office code filed and the name shown."""

    model_config = ConfigDict(frozen=True)

    office_code: str = Field(pattern=r"^[0-9]{8}$")
    office_name: str = Field(min_length=1)


class ReferenceTables(BaseModel):
    """Every curated table one run needs, resolved and indexed.

    Built by `load_tables`. The indexes are built once because unit resolution runs on
    every goods line and country detection scans several free-text fields per run.
    """

    model_config = ConfigDict(frozen=True)

    units: tuple[UnitEntry, ...]
    count_unit_codes: frozenset[str]
    mass_units_in_kilograms: dict[str, Decimal]
    kilogram_code: str
    pieces_code: str
    unit_by_alias: dict[str, str]
    unit_by_code: dict[str, UnitEntry]

    product_kind_units: dict[str, str]

    packing_entries: tuple[PackingEntry, ...]
    package_counting_words: frozenset[str]

    package_noun_by_code: dict[str, str]
    pack_math_default_noun: str
    package_segment_default_noun: str
    piece_noun: str
    per_package_noun: str

    border_office_by_country: dict[str, BorderOffice]
    countries: tuple[CountryEntry, ...]
    country_by_code: dict[str, CountryEntry]

    brand_stoplist: frozenset[str]
    container_keywords: tuple[str, ...]

    size_separators: tuple[str, ...]
    size_separator_replacement: str
    size_unit_by_token: dict[str, str]

    def unit(self, okei: str) -> UnitEntry:
        """The unit with this code, or a refusal naming it.

        Every code that reaches here came out of one of these tables, so a miss is a
        defect in the tables rather than in a document.
        """
        entry = self.unit_by_code.get(okei)
        if entry is None:
            raise AssemblyError(
                f"no unit {okei!r} in the curated unit table. Nothing may be filed in a "
                "unit this product cannot name, and the portal's own classifier is the "
                "only authority on which units exist."
            )
        return entry

    def resolve_unit(self, printed: str | None) -> str | None:
        """The OKEI code a printed unit string means, or None.

        A composite string resolves by its leading token, which is how the nomenclature's
        own `шт, м` arrives. Content-based units — kilograms of nitrogen, grams of
        fissile isotopes — resolve to nothing on purpose: they cannot be computed from
        commercial documents, and an unknown unit must map to nothing rather than to a
        wrong one.
        """
        if printed is None:
            return None
        text = _fold(printed)
        if not text:
            return None
        direct = self.unit_by_alias.get(text)
        if direct is not None:
            return direct
        leading = text.split(",", 1)[0].strip()
        return self.unit_by_alias.get(leading)

    def is_count_unit(self, okei: str) -> bool:
        """Whether a figure in this unit counts things rather than measuring them."""
        return okei in self.count_unit_codes

    def counts_in_its_own_unit(self, okei: str) -> bool:
        """A count unit that is not pieces — pairs, thousands of pieces.

        A line counted in one of these never yields a derived piece total. Deriving one
        from 100 pairs would contradict the very figure box 41 files.
        """
        return self.is_count_unit(okei) and okei != self.pieces_code

    def kilograms_per(self, okei: str) -> Decimal | None:
        """How many kilograms one of this unit is, or None if it is not a mass."""
        return self.mass_units_in_kilograms.get(okei)

    def counts_packages(self, printed: str | None) -> bool:
        """Whether a quantity column labelled this counts packages rather than items."""
        if printed is None:
            return False
        return _fold(printed) in self.package_counting_words

    def packing_code(self, printed: str | None) -> str | None:
        """The UN/ECE code a packing wording means, first hit in table order."""
        if printed is None:
            return None
        text = _fold(printed)
        if not text:
            return None
        for entry in self.packing_entries:
            if any(_contains_alias(text, alias) for alias in entry.aliases):
                return entry.code
        return None

    def package_noun(self, packing_code: str | None, *, in_pack_math: bool) -> str:
        """The Armenian noun that counts these packages in box 31 text."""
        if packing_code is not None:
            noun = self.package_noun_by_code.get(packing_code)
            if noun is not None:
                return noun
        return (
            self.pack_math_default_noun
            if in_pack_math
            else self.package_segment_default_noun
        )

    def country(self, code: str) -> CountryEntry | None:
        return self.country_by_code.get(code.strip().upper())

    def detect_country(self, text: str | None) -> CountryEntry | None:
        """The country a free-text field names, longest alias wins.

        An ISO-2 code is resolved only when it is the whole field. Two-letter tokens are
        too common inside addresses to scan for, and dossier 11 §3.4 sets the free-text
        minimum at three characters for exactly that reason.
        """
        if text is None:
            return None
        stripped = text.strip()
        if not stripped:
            return None
        exact = self.country_by_code.get(stripped.upper())
        if exact is not None:
            return exact
        folded = _fold(stripped)
        best: tuple[int, CountryEntry] | None = None
        for entry in self.countries:
            for alias in entry.aliases:
                if len(alias) < 3 or not _contains_alias(folded, alias):
                    continue
                if best is None or len(alias) > best[0]:
                    best = (len(alias), entry)
        return None if best is None else best[1]

    def names_a_container(self, text: str | None) -> bool:
        if text is None:
            return False
        folded = _fold(text)
        return any(_contains_alias(folded, word) for word in self.container_keywords)

    def is_brandable(self, token: str) -> bool:
        """Whether a Latin token could be a brand, or is one of the words that never is."""
        return token.strip().upper() not in self.brand_stoplist


def load_tables(directory: Path) -> ReferenceTables:
    """Read every curated table from one directory.

    The directory is passed in rather than found: nothing below the settings object knows
    a filesystem layout, and a test points this at whatever it likes.
    """
    units_file = _read(directory / "units.json")
    units = tuple(UnitEntry(**row) for row in units_file["units"])
    packing = tuple(PackingEntry(**row) for row in _read(directory / "packing_codes.json")["entries"])
    nouns = _read(directory / "package_nouns.json")
    counting = _read(directory / "package_counting_units.json")
    countries = tuple(
        CountryEntry(**row) for row in _read(directory / "countries.json")["countries"]
    )
    offices = {
        code: BorderOffice(**office)
        for code, office in _read(directory / "border_offices.json")[
            "by_dispatch_country"
        ].items()
    }
    sizes = _read(directory / "size_units.json")

    unit_by_alias: dict[str, str] = {}
    for entry in units:
        for alias in entry.aliases:
            folded = _fold(alias)
            existing = unit_by_alias.get(folded)
            if existing is not None and existing != entry.okei:
                raise AssemblyError(
                    f"the unit alias {alias!r} resolves to both {existing} and "
                    f"{entry.okei} in {directory / 'units.json'}. An ambiguous alias "
                    "would file a figure under whichever row happened to load last."
                )
            unit_by_alias[folded] = entry.okei

    # Dossier 11 §D10.6: the effective package-counting vocabulary is the listed words
    # UNION every alias the packing table resolves — bags, drums and pallets count
    # packages as surely as cartons do.
    package_words = {_fold(word) for word in counting["words"]}
    package_words.update(_fold(alias) for entry in packing for alias in entry.aliases)

    tables = ReferenceTables(
        units=units,
        count_unit_codes=frozenset(units_file["count_units"]),
        mass_units_in_kilograms={
            code: Decimal(factor)
            for code, factor in units_file["mass_units_in_kilograms"].items()
        },
        kilogram_code=units_file["kilogram"],
        pieces_code=units_file["pieces"],
        unit_by_alias=unit_by_alias,
        unit_by_code={entry.okei: entry for entry in units},
        product_kind_units=_read(directory / "product_kind_units.json")["by_kind"],
        packing_entries=packing,
        package_counting_words=frozenset(package_words),
        package_noun_by_code=nouns["by_code"],
        pack_math_default_noun=nouns["default_in_pack_math"],
        package_segment_default_noun=nouns["default_for_package_segment"],
        piece_noun=nouns["piece_noun"],
        per_package_noun=nouns["per_package_noun"],
        border_office_by_country=offices,
        countries=countries,
        country_by_code={entry.code: entry for entry in countries},
        brand_stoplist=frozenset(
            token.upper() for token in _read(directory / "brand_stoplist.json")["tokens"]
        ),
        container_keywords=tuple(
            _fold(word) for word in _read(directory / "container_keywords.json")["keywords"]
        ),
        size_separators=tuple(sizes["separators"]),
        size_separator_replacement=sizes["separator_replacement"],
        size_unit_by_token={
            token.upper(): armenian for token, armenian in sizes["by_token"].items()
        },
    )
    _check_the_tables_agree(tables, directory)
    return tables


def _check_the_tables_agree(tables: ReferenceTables, directory: Path) -> None:
    """Cross-table invariants, checked once rather than discovered on a filing."""
    for code in tables.count_unit_codes | set(tables.mass_units_in_kilograms):
        if code not in tables.unit_by_code:
            raise AssemblyError(
                f"{directory / 'units.json'} classifies {code!r} without listing it as a "
                "unit, so a figure could be judged a count or a mass in a unit nothing "
                "can name."
            )
    for named, role in ((tables.kilogram_code, "kilogram"), (tables.pieces_code, "pieces")):
        if named not in tables.unit_by_code:
            raise AssemblyError(
                f"{directory / 'units.json'} names {named!r} as {role} and does not list "
                "it. Every unit this product can reach for must be one it can name."
            )
    for kind, okei in tables.product_kind_units.items():
        if okei not in tables.unit_by_code:
            raise AssemblyError(
                f"product kind {kind!r} maps to unit {okei!r}, which "
                f"{directory / 'units.json'} does not list."
            )
    for code in tables.package_noun_by_code:
        if code not in {entry.code for entry in tables.packing_entries}:
            raise AssemblyError(
                f"package noun table names packing code {code!r}, which the packing "
                "table cannot produce. The two are keyed on the same codes."
            )


def _read(path: Path) -> dict:
    """One table file, or a refusal naming it."""
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AssemblyError(
            f"no reference table at {path}. The curated tables are tracked in git under "
            "reference_data/; a run without them resolves nothing and omits every field "
            "they feed."
        ) from exc
    except json.JSONDecodeError as exc:
        raise AssemblyError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise AssemblyError(f"{path} must hold an object, not a {type(loaded).__name__}")
    return loaded


def _fold(text: str) -> str:
    """The form aliases are matched in: uppercase, superscripts folded, no trailing dot.

    Dossier 05 §6.1 names all three: the tables must be script-insensitive, `М²` and `М2`
    are the same unit, and `ШТ.` is `ШТ`.
    """
    folded = text.strip().upper().replace("²", "2").replace("³", "3")
    return folded.rstrip(".").strip()


def _contains_alias(folded_text: str, alias: str) -> bool:
    """Whether an alias appears in already-folded text as a whole word."""
    pattern = _BOUNDARY + re.escape(_fold(alias)) + _BOUNDARY_AFTER
    return re.search(pattern, folded_text) is not None
