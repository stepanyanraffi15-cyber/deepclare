"""The gate that makes the corpus safe to publish.

Two checks, run before any case is written:
  * **leak scan** — no real party name / tax ID / address from the seed may appear
    in the synthetic output. This is what lets us derive from private data and
    still open-source the result.
  * **consistency** — the case must be internally coherent (totals add up, gross ≥
    net), so a rendered artifact never contradicts its own ground truth.

Both return a list of problems; empty == clean.
"""

from __future__ import annotations

import re

from .ir import Case


def leak_scan(text: str, forbidden_terms: set[str]) -> list[str]:
    """Real terms that survived into ``text`` — matched as whole tokens, not raw substrings.

    Word-bounded so a name isn't flagged inside a longer word (e.g. the person name ՎԱՀԱՆ
    inside ՎԱՀԱՆԱԿ, "panel") — \\w is Unicode-aware, so it covers Armenian + Latin + digits.
    """
    haystack = text.lower()
    hits = []
    for term in forbidden_terms:
        t = term.strip().lower()
        if len(t) >= 3 and re.search(rf"(?<!\w){re.escape(t)}(?!\w)", haystack):
            hits.append(term)
    return sorted(set(hits))


def consistency(case: Case) -> list[str]:
    problems: list[str] = []
    if not case.goods:
        problems.append("case has no goods")
    for i, g in enumerate(case.goods, 1):
        if g.gross_weight < g.net_weight:
            problems.append(f"line {i}: gross < net")
        if g.quantity <= 0:
            problems.append(f"line {i}: non-positive quantity")
        if g.package_count < 1:
            problems.append(f"line {i}: package_count < 1")
        if not g.hs_code:
            problems.append(f"line {i}: missing HS code")
    stated = round(sum(g.invoiced_cost for g in case.goods), 2)
    if abs(stated - case.total_cost) > 0.01:
        problems.append(f"total cost {case.total_cost} != sum of lines {stated}")
    return problems
