"""Commodity-code (HS / ԱՏԳ / TN VED) comparison — hierarchical, not just exact.

A code that agrees to 6 digits but differs on the national suffix is a near-miss,
not a failure, and the digit at which two codes diverge tells you *where*
classification broke (wrong chapter vs. wrong national tail). So we report exact
match plus agreement at each hierarchy level.

Levels: 2 = chapter, 4 = heading, 6 = subheading (the international HS boundary),
8 / 10 = national. Codes are compared digits-only, left-aligned.
"""

from __future__ import annotations

from dataclasses import dataclass

LEVELS: tuple[int, ...] = (2, 4, 6, 8, 10)


def digits(code: str) -> str:
    return "".join(ch for ch in code if ch.isdigit())


@dataclass(frozen=True)
class CodeScore:
    exact: bool
    prefix_len: int  # leading digits that agree
    levels: dict[int, bool]  # {2: True, 4: True, 6: False, ...}

    def at(self, level: int) -> bool:
        return self.levels.get(level, False)


def score_code(hyp: str, ref: str) -> CodeScore:
    h, r = digits(hyp), digits(ref)
    prefix = 0
    for a, b in zip(h, r):
        if a != b:
            break
        prefix += 1
    exact = bool(h) and h == r
    levels = {lvl: (len(h) >= lvl and len(r) >= lvl and prefix >= lvl) for lvl in LEVELS}
    return CodeScore(exact=exact, prefix_len=prefix, levels=levels)
