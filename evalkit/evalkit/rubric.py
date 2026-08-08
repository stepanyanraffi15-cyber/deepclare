"""Attribute rubric: does a description carry the attributes it legally must?

A customs description is "good" less by string similarity than by whether it
states the required, checkable attributes — the brand/trade name and the
material — without inventing ones that were not on the invoice. This turns a
fuzzy question into booleans:

    brand_retained · trade_name_present · material_stated · no_hallucinated_brand

Two modes:
  * With **known atoms** (from a synthetic case's ground_truth.json — the brand /
    trade_name / material we generated the line from) the checks are *exact*.
  * Without atoms (comparing against a raw filed declaration) they degrade
    gracefully: the expected brand is detected from the reference description,
    and material is checked against a small stem list. A check with nothing to
    assert returns ``None`` (not counted), never a false failure.

Self-contained detectors (a trimmed copy of the pipeline's heuristics) so the
package has no cross-repo imports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Latin tokens that are units / formats / acronyms, never a brand.
_NON_BRAND = {
    "LED", "PVC", "PET", "PP", "PE", "UV", "IP", "USB", "LED", "A4", "A3",
    "KG", "PCS", "PC", "SET", "MM", "CM", "ML", "GR", "G", "L", "M", "M2", "M3",
}
_LATIN = re.compile(r"[A-Za-z][A-Za-z0-9\-]*")

# A few Armenian material stems (extend per corpus). Used only in the no-atoms path.
_MATERIAL_STEMS = ("ՓԱՅՏ", "ՄԵՏԱՂ", "ՊՈՂՊԱՏ", "ԱՊԱԿԻ", "ՊԼԱՍՏ", "ԿԱՈՒՉ", "ԹՈՒՂԹ", "ԲԱՄԲԱԿ")


def _collapse_alnum(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Zա-ֆԱ-Ֆ]+", "", text).lower()


def detect_brand(description: str) -> str | None:
    """First Latin token that looks like a brand (not a unit / not a bare number)."""
    for match in _LATIN.finditer(description):
        token = match.group(0)
        if token.upper() in _NON_BRAND:
            continue
        if token.isdigit():
            continue
        return token
    return None


def contains(description: str, token: str | None) -> bool:
    if not token:
        return False
    return _collapse_alnum(token) in _collapse_alnum(description)


@dataclass(frozen=True)
class RubricResult:
    brand_retained: bool | None
    trade_name_present: bool | None
    material_stated: bool | None
    no_hallucinated_brand: bool | None

    def as_dict(self) -> dict[str, bool | None]:
        return {
            "brand_retained": self.brand_retained,
            "trade_name_present": self.trade_name_present,
            "material_stated": self.material_stated,
            "no_hallucinated_brand": self.no_hallucinated_brand,
        }


def score_rubric(
    hyp: str,
    ref: str = "",
    *,
    brand: str | None = None,
    trade_name: str | None = None,
    material: str | None = None,
) -> RubricResult:
    """Score ``hyp`` against known atoms; fall back to ``ref`` when atoms are absent."""
    expected_brand = brand if brand is not None else detect_brand(ref)
    expected_material = material  # no reliable detection from ref alone

    brand_retained = contains(hyp, expected_brand) if expected_brand else None
    trade_name_present = contains(hyp, trade_name) if trade_name else None

    if expected_material:
        material_stated: bool | None = contains(hyp, expected_material)
    elif ref:
        # No known material: only assert if the reference itself stated one.
        stems = [s for s in _MATERIAL_STEMS if s in ref.upper()]
        material_stated = any(s in hyp.upper() for s in stems) if stems else None
    else:
        material_stated = None

    found = detect_brand(hyp)
    if found is None:
        no_hallucinated = None if expected_brand is None else True
    else:
        allowed = contains(ref, found) or (expected_brand and contains(found, expected_brand))
        no_hallucinated = bool(allowed)

    return RubricResult(brand_retained, trade_name_present, material_stated, no_hallucinated)
