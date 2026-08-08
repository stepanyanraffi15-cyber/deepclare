"""How a value is written down — the layer between a domain value and element text.

Dossier 03 §6 fixes all of it and none of it matches what an XML library does by default:

* period decimal separator, no thousands separator, no sign, no currency symbol, no
  scientific notation;
* no trailing zeros — zero is `0` and never `0.00`;
* integral values written without a decimal point;
* fixed-width codes are strings, left-zero-padded, and parsing one as a number destroys
  it;
* dates ISO `YYYY-MM-DD`, no time and no zone.

Every function here refuses rather than coerces. A value that cannot be written under
these rules is a defect upstream, and quietly reshaping it would put a wrong number on a
legal document.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from deepclare.filing.errors import UnrepresentableValue


def decimal_text(value: Decimal) -> str:
    """Write a number the way the contract wants it read.

    `Decimal.normalize` alone is not enough: it turns 100 into `1E+2`, which is exactly
    the scientific notation the contract forbids. Re-quantising the integral case back to
    one is the whole reason this is not a one-liner.
    """
    if not value.is_finite():
        raise UnrepresentableValue(f"{value!r} is not a finite number")
    if value < 0:
        raise UnrepresentableValue(f"the filed format carries no negative numbers: {value}")

    trimmed = value.normalize()
    if trimmed == 0:
        return "0"
    if trimmed.as_tuple().exponent > 0:
        trimmed = trimmed.quantize(Decimal(1))
    return format(trimmed, "f")


def integer_text(value: int) -> str:
    """Write a count. Bare digits, no separator, no sign."""
    if value < 0:
        raise UnrepresentableValue(f"the filed format carries no negative counts: {value}")
    return str(value)


def date_text(value: date) -> str:
    """ISO `YYYY-MM-DD`. The corpus is 100% conformant on this and carries no times."""
    return value.isoformat()


def boolean_text(value: bool) -> str:
    """Lowercase `true` / `false`, as the container indicator is filed."""
    return "true" if value else "false"


def code_text(value: str) -> str:
    """Pass a fixed-width code through untouched, having checked it is one.

    The check is that it survived as a string. `055` and `000` are values, not numbers;
    anything that has been through an integer on its way here arrives with its padding
    gone and cannot be recovered, so an empty or space-bearing code is a defect rather
    than something to tidy up.
    """
    if not value:
        raise UnrepresentableValue("a code value is empty")
    if value != value.strip():
        raise UnrepresentableValue(f"a code value carries surrounding whitespace: {value!r}")
    return value


def truncated_text(value: str, limit: int) -> tuple[str, bool]:
    """Cut a text leaf to a hard cap, reporting whether it had to.

    Only one leaf in the document is capped this way. Dossier 07 §2.1 case R2: an
    over-long street-and-house line rejects the entire file's format, with a message that
    names no field, *after* the portal has already populated the form from it.
    """
    text = value.strip()
    if len(text) <= limit:
        return text, False
    # Right-stripped after the cut so a truncation that lands on a space does not leave
    # trailing whitespace inside the element.
    return text[:limit].rstrip(), True
