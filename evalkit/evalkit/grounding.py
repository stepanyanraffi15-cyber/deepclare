"""Source-grounding: is a ground-truth value even *available* in the scanned input?

A field the pipeline gets wrong is only the pipeline's failure if the information to
produce it was present in the invoice/CMR. Customs brokers routinely add facts the
documents don't carry — an origin country confirmed by phone, a net weight the invoice
omitted — so a declaration can legitimately hold values no scan could recover. Scoring
those as misses punishes the assistant for not being the broker.

So: when a value in the ground truth is absent from the source scan text, the miss is
**excused** (external), not counted against the pipeline. With no source text supplied,
nothing is excused — every field is treated as attributable (the strict default).
"""

from __future__ import annotations

import re

from .rubric import _collapse_alnum

_NUM = re.compile(r"\d[\d\s.,]*\d|\d")


def source_numbers(source_text: str) -> set[float]:
    """Every numeric token in the source, normalised to floats (comma or dot decimals)."""
    out: set[float] = set()
    for m in _NUM.finditer(source_text):
        raw = m.group(0).replace(" ", "")
        # a trailing group of 3 after a separator is a thousands group, not decimals
        cleaned = raw.replace(",", ".")
        if cleaned.count(".") > 1:
            cleaned = cleaned.replace(".", "")
        try:
            out.add(round(float(cleaned), 3))
        except ValueError:
            continue
    return out


def number_grounded(value: float, nums: set[float], eps: float = 0.01) -> bool:
    return any(abs(value - n) <= max(eps, 1e-4 * max(abs(value), abs(n))) for n in nums)


def text_grounded(value: str, source_collapsed: str) -> bool:
    v = _collapse_alnum(value)
    return bool(v) and v in source_collapsed


class Source:
    """Pre-parsed source scan text for cheap repeated grounding checks."""

    def __init__(self, text: str | None) -> None:
        self.present = text is not None
        self.numbers = source_numbers(text) if text else set()
        self.collapsed = _collapse_alnum(text) if text else ""

    def has_number(self, value: float | None) -> bool:
        # No source → treat as grounded (attributable): we can't prove it was external.
        if not self.present or value is None:
            return True
        return number_grounded(value, self.numbers)

    def has_text(self, value: str | None) -> bool:
        if not self.present or not value:
            return True
        return text_grounded(value, self.collapsed)
