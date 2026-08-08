"""Surface-form text metrics for free-text descriptions.

`chrf` (character n-gram F-score) is the workhorse: it is language-agnostic and
robust for morphologically rich languages like Armenian, where word-level BLEU
over-penalises inflection. `token_f1` and `normalized_exact` are cheaper
companions. All are pure functions in [0, 1], deterministic, stdlib only —
suitable for a per-commit regression gate.

These measure *surface overlap*, not meaning. Semantic equivalence (paraphrase)
is the job of the optional embedding tier (`semantic.py`); required-attribute
presence is the job of `rubric.py`. Use all three — none alone is "quality".
"""

from __future__ import annotations

from collections import Counter


def normalize_ws(text: str) -> str:
    """Lowercase and collapse runs of whitespace to single spaces."""
    return " ".join(text.split()).lower()


def normalized_exact(hyp: str, ref: str) -> bool:
    return normalize_ws(hyp) == normalize_ws(ref)


def _char_ngrams(text: str, n: int) -> Counter[str]:
    # chrF ignores whitespace differences by collapsing them first.
    s = normalize_ws(text).replace(" ", "")
    if len(s) < n:
        return Counter()
    return Counter(s[i : i + n] for i in range(len(s) - n + 1))


def chrf(hyp: str, ref: str, max_n: int = 6, beta: float = 2.0) -> float:
    """Character n-gram F-beta score, averaged over n = 1..max_n.

    Returns 1.0 when both sides are empty and 0.0 when exactly one is. beta=2
    weights recall over precision (the customs default: an omitted attribute
    hurts more than an extra word).
    """
    h_norm, r_norm = normalize_ws(hyp), normalize_ws(ref)
    if not h_norm and not r_norm:
        return 1.0
    if not h_norm or not r_norm:
        return 0.0

    precisions: list[float] = []
    recalls: list[float] = []
    for n in range(1, max_n + 1):
        h = _char_ngrams(hyp, n)
        r = _char_ngrams(ref, n)
        h_total, r_total = sum(h.values()), sum(r.values())
        if h_total == 0 or r_total == 0:
            continue
        overlap = sum((h & r).values())
        precisions.append(overlap / h_total)
        recalls.append(overlap / r_total)

    if not precisions:
        return 0.0
    p = sum(precisions) / len(precisions)
    r = sum(recalls) / len(recalls)
    if p == 0 and r == 0:
        return 0.0
    b2 = beta * beta
    return (1 + b2) * p * r / (b2 * p + r)


def token_f1(hyp: str, ref: str) -> float:
    """Multiset token overlap F1 over whitespace tokens."""
    h = Counter(normalize_ws(hyp).split())
    r = Counter(normalize_ws(ref).split())
    if not h and not r:
        return 1.0
    if not h or not r:
        return 0.0
    overlap = sum((h & r).values())
    if overlap == 0:
        return 0.0
    p = overlap / sum(h.values())
    rec = overlap / sum(r.values())
    return 2 * p * rec / (p + rec)
