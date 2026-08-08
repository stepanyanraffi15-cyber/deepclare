"""The mandatory mask, applied before anything reaches a sink.

Dossier 08 §16.3 makes this the one part of the capture policy that has no off switch,
and records why: the measured system applied no redaction, no scrubber, no allowlist and
no field mask anywhere before logging, and separately carried a username in a warning
payload and an importing company's tax code in trace metadata. The prompts this product
sends contain extracted invoice contents.

**The mask is driven by the field-semantics model, not by pattern-guessing.** The domain
vocabulary already says which fields hold identity — a party's name, its address, its tax
code, a filler's surname and telephone — and this module keys off those field names.
Two mechanisms, in that order of authority:

1. **Field mask.** Any leaf whose field name is in `IDENTITY_FIELDS` is replaced by a
   class marker. Containers are not listed: a party is masked by masking every leaf
   under it, which keeps the shape of the record readable while removing its content.
2. **Value removal in free text.** `identities_in` harvests the actual identity strings
   out of the records a run produced; the redactor then removes those exact strings from
   every captured prompt and response. This is what makes a rendered prompt safe, since
   a prompt is one long string with no field names left in it.

A small pattern backstop catches email addresses, IBANs and international phone numbers
that no field named. It deliberately does **not** scrub long digit runs: a commodity code
is eleven digits and a trace that masks commodity codes cannot explain a classification.
Tax identifiers are removed by value, from the field that declared itself a tax code.

A bare `name` is always masked, including the country and customs-office names that are
not identity. That costs nothing recoverable: in this domain every such name travels
beside its code, and the codes are never masked.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

MINIMUM_MASKED_LENGTH = 3
"""Shorter identity strings are not removed from free text. A two-character company name
appears inside ordinary words and removing it everywhere would shred the trace."""


class IdentityClass(StrEnum):
    """The classes dossier 08 §16.3 names. A trace must contain none of them."""

    PERSON_NAME = "person_name"
    ORGANIZATION_NAME = "organization_name"
    POSTAL_ADDRESS = "postal_address"
    TAX_IDENTIFIER = "tax_identifier"
    CONTACT = "contact"
    BANK_DETAIL = "bank_detail"


IDENTITY_FIELDS: dict[str, IdentityClass] = {
    # people
    "surname": IdentityClass.PERSON_NAME,
    "person_surname": IdentityClass.PERSON_NAME,
    "given_name": IdentityClass.PERSON_NAME,
    "first_name": IdentityClass.PERSON_NAME,
    "last_name": IdentityClass.PERSON_NAME,
    "person_name": IdentityClass.PERSON_NAME,
    "signatory": IdentityClass.PERSON_NAME,
    # organizations
    "name": IdentityClass.ORGANIZATION_NAME,
    "company_name": IdentityClass.ORGANIZATION_NAME,
    "organization_name": IdentityClass.ORGANIZATION_NAME,
    "party_name": IdentityClass.ORGANIZATION_NAME,
    "consignor_name": IdentityClass.ORGANIZATION_NAME,
    "consignee_name": IdentityClass.ORGANIZATION_NAME,
    # addresses
    "address": IdentityClass.POSTAL_ADDRESS,
    "postal_address": IdentityClass.POSTAL_ADDRESS,
    "street": IdentityClass.POSTAL_ADDRESS,
    "street_house": IdentityClass.POSTAL_ADDRESS,
    "street_address": IdentityClass.POSTAL_ADDRESS,
    "city": IdentityClass.POSTAL_ADDRESS,
    "postcode": IdentityClass.POSTAL_ADDRESS,
    "post_code": IdentityClass.POSTAL_ADDRESS,
    "zip_code": IdentityClass.POSTAL_ADDRESS,
    # tax and registration identifiers
    "tax_code": IdentityClass.TAX_IDENTIFIER,
    "tax_id": IdentityClass.TAX_IDENTIFIER,
    "taxpayer_id": IdentityClass.TAX_IDENTIFIER,
    "tin": IdentityClass.TAX_IDENTIFIER,
    "vat": IdentityClass.TAX_IDENTIFIER,
    "vat_code": IdentityClass.TAX_IDENTIFIER,
    "vat_number": IdentityClass.TAX_IDENTIFIER,
    "registration_number": IdentityClass.TAX_IDENTIFIER,
    "company_number": IdentityClass.TAX_IDENTIFIER,
    # contact details
    "phone": IdentityClass.CONTACT,
    "telephone": IdentityClass.CONTACT,
    "phone_number": IdentityClass.CONTACT,
    "fax": IdentityClass.CONTACT,
    "email": IdentityClass.CONTACT,
    "e_mail": IdentityClass.CONTACT,
    "email_address": IdentityClass.CONTACT,
    "contact": IdentityClass.CONTACT,
    "contact_person": IdentityClass.CONTACT,
    # bank details
    "bank": IdentityClass.BANK_DETAIL,
    "bank_name": IdentityClass.BANK_DETAIL,
    "bank_account": IdentityClass.BANK_DETAIL,
    "account": IdentityClass.BANK_DETAIL,
    "account_number": IdentityClass.BANK_DETAIL,
    "correspondent_account": IdentityClass.BANK_DETAIL,
    "iban": IdentityClass.BANK_DETAIL,
    "swift": IdentityClass.BANK_DETAIL,
    "bic": IdentityClass.BANK_DETAIL,
}

_TRACED_VALUE_KEY = "value"
"""Every traced value in this system dumps as `{value, provenance, confidence}`. Masking
an identity-bearing traced field replaces its `value` and keeps the provenance, because
which document and page a name was read from is not itself identity."""

_PATTERN_BACKSTOP: tuple[tuple[re.Pattern[str], IdentityClass], ...] = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), IdentityClass.CONTACT),
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), IdentityClass.BANK_DETAIL),
    (re.compile(r"\+\d[\d\s().-]{6,}\d"), IdentityClass.CONTACT),
)


def mask_for(klass: IdentityClass) -> str:
    return f"[redacted:{klass.value}]"


class IdentityValue(BaseModel):
    """One identity string a run actually handled, and what kind it is."""

    model_config = ConfigDict(frozen=True)

    klass: IdentityClass
    text: str


def identities_in(value: object) -> tuple[IdentityValue, ...]:
    """Harvest every identity string out of a record, by field name.

    Takes any Pydantic model, mapping or sequence the run produced — an invoice reading,
    a consignment note, a declaration — and returns what a redactor must remove from free
    text. Order is stable and duplicates are dropped.
    """
    found: dict[tuple[IdentityClass, str], None] = {}
    _harvest(value, None, found)
    return tuple(IdentityValue(klass=klass, text=text) for klass, text in found)


def _harvest(
    value: object,
    field_name: str | None,
    found: dict[tuple[IdentityClass, str], None],
) -> None:
    klass = IDENTITY_FIELDS.get(field_name) if field_name else None

    if isinstance(value, BaseModel):
        _harvest(value.model_dump(), field_name, found)
        return
    if isinstance(value, Mapping):
        if klass is not None and _TRACED_VALUE_KEY in value:
            _harvest(value[_TRACED_VALUE_KEY], field_name, found)
            return
        for key, item in value.items():
            _harvest(item, str(key), found)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _harvest(item, field_name, found)
        return
    if klass is not None and isinstance(value, str) and value.strip():
        found[(klass, value.strip())] = None


class Redactor:
    """Masks structured records and free text before either reaches a sink.

    Construct it with the identity strings a run handled — `identities_in(invoice)` and
    `identities_in(note)` — so that a rendered prompt can be scrubbed by value. With no
    identities it still applies the field mask and the pattern backstop; it is never a
    pass-through.
    """

    def __init__(self, identities: Iterable[IdentityValue] = ()) -> None:
        by_length = sorted(
            {(i.klass, i.text) for i in identities if len(i.text) >= MINIMUM_MASKED_LENGTH},
            key=lambda pair: (-len(pair[1]), pair[1]),
        )
        self._replacements = tuple(
            (re.compile(re.escape(text), re.IGNORECASE), mask_for(klass))
            for klass, text in by_length
        )

    def mask(self, value: object) -> Any:
        """A JSON-safe copy with every identity-bearing field replaced.

        Returns only types a sink can serialize: strings, numbers, booleans, `None`,
        lists and dictionaries. Anything else is rendered with `str`, which also means a
        `Decimal` or a `datetime` in a captured state cannot break the write.
        """
        return self._mask(value, None)

    def mask_text(self, text: str) -> str:
        """Remove every known identity string, then the pattern backstop."""
        masked = text
        for pattern, replacement in self._replacements:
            masked = pattern.sub(replacement, masked)
        for pattern, klass in _PATTERN_BACKSTOP:
            masked = pattern.sub(mask_for(klass), masked)
        return masked

    def _mask(self, value: object, field_name: str | None) -> Any:
        klass = IDENTITY_FIELDS.get(field_name) if field_name else None

        if isinstance(value, BaseModel):
            return self._mask(value.model_dump(), field_name)
        if isinstance(value, Mapping):
            if klass is not None and _TRACED_VALUE_KEY in value:
                return {
                    key: mask_for(klass)
                    if key == _TRACED_VALUE_KEY
                    else self._mask(item, str(key))
                    for key, item in value.items()
                }
            return {str(key): self._mask(item, str(key)) for key, item in value.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            return [self._mask(item, field_name) for item in value]
        if klass is not None and value is not None:
            return mask_for(klass)
        if isinstance(value, str):
            return self.mask_text(value)
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, Decimal):
            return str(value)
        return str(value)


def identity_leaks(value: object, identities: Sequence[IdentityValue]) -> tuple[str, ...]:
    """Every identity string still present in `value`, for a test to assert is empty.

    Dossier 08 §16.3 asks for a test proving that no identity class reaches a log or a
    trace. This is the predicate that test asserts on; it is not used on the run path.
    """
    haystack = _flatten(value).casefold()
    return tuple(
        identity.text
        for identity in identities
        if len(identity.text) >= MINIMUM_MASKED_LENGTH
        and identity.text.casefold() in haystack
    )


def _flatten(value: object) -> str:
    if isinstance(value, BaseModel):
        return _flatten(value.model_dump())
    if isinstance(value, Mapping):
        return " ".join(f"{key} {_flatten(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return " ".join(_flatten(item) for item in value)
    if hasattr(value, "__dict__") and not isinstance(value, type):
        # A plain object — a whole run trace, for instance. Without this the check
        # flattens to an object repr and passes without having read anything.
        return _flatten(vars(value))
    return str(value)
