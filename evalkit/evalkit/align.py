"""Align output goods lines to ground-truth goods lines before scoring fields.

Line count and order differ in practice — lines get merged, split, dropped, or
invented (a scan that reads 80 lines as 81; the group/ungroup feature). Comparing
by position would score the wrong pairs. So we find the best 1:1 assignment on a
line-similarity score (HS prefix + description overlap + quantity closeness), then
report the alignment itself as precision / recall / F1 — a top-level signal for
"did we produce the right lines at all", independent of per-field accuracy.

Assignment is greedy (highest-similarity pair first). Goods counts per declaration
are small, so greedy is effectively optimal here and keeps the package dependency
-free; swap in scipy's linear_sum_assignment if you ever need the guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass

from .codes import score_code
from .parse import Good
from .textmetrics import chrf

# Weights for the composite line-similarity used only for matching (not scoring).
_W_CODE = 0.5
_W_DESC = 0.4
_W_QTY = 0.1


def line_similarity(a: Good, b: Good) -> float:
    code = score_code(a.hs_code, b.hs_code)
    max_len = max(len(a.hs_code.strip()), len(b.hs_code.strip()), 1)
    code_sim = code.prefix_len / max_len
    desc_sim = chrf(a.description, b.description)
    qty_sim = _closeness(a.quantity, b.quantity)
    return _W_CODE * code_sim + _W_DESC * desc_sim + _W_QTY * qty_sim


def _closeness(x: float | None, y: float | None) -> float:
    if x is None or y is None:
        return 0.0
    hi = max(abs(x), abs(y))
    if hi == 0:
        return 1.0
    return 1.0 - min(abs(x - y) / hi, 1.0)


@dataclass(frozen=True)
class Alignment:
    pairs: tuple[tuple[int, int, float], ...]  # (mine_idx, gold_idx, similarity)
    unmatched_mine: tuple[int, ...]  # invented lines (false positives)
    unmatched_gold: tuple[int, ...]  # missed lines (false negatives)

    def precision(self) -> float:
        denom = len(self.pairs) + len(self.unmatched_mine)
        return len(self.pairs) / denom if denom else 1.0

    def recall(self) -> float:
        denom = len(self.pairs) + len(self.unmatched_gold)
        return len(self.pairs) / denom if denom else 1.0

    def f1(self) -> float:
        p, r = self.precision(), self.recall()
        return 2 * p * r / (p + r) if (p + r) else 0.0


def align(mine: list[Good], gold: list[Good], threshold: float = 0.3) -> Alignment:
    """Greedy best-first 1:1 matching above ``threshold`` similarity."""
    candidates: list[tuple[float, int, int]] = []
    for i, a in enumerate(mine):
        for j, b in enumerate(gold):
            candidates.append((line_similarity(a, b), i, j))
    candidates.sort(reverse=True)

    used_mine: set[int] = set()
    used_gold: set[int] = set()
    pairs: list[tuple[int, int, float]] = []
    for sim, i, j in candidates:
        if sim < threshold or i in used_mine or j in used_gold:
            continue
        used_mine.add(i)
        used_gold.add(j)
        pairs.append((i, j, sim))

    pairs.sort(key=lambda p: p[1])  # order by gold line for stable reporting
    unmatched_mine = tuple(i for i in range(len(mine)) if i not in used_mine)
    unmatched_gold = tuple(j for j in range(len(gold)) if j not in used_gold)
    return Alignment(tuple(pairs), unmatched_mine, unmatched_gold)
