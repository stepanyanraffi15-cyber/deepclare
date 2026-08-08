"""Procedural, obviously-fake stamps and signatures for scanned CMR realism.

Their purpose is to be visual noise overlapping document text — the occlusion a
real scanned CMR has and the scanner must survive — NOT to imitate any real seal.
Parties are fictional, so the stamp text is fictional too: safe to open-source.

Both return standalone SVG strings (no dependencies). Composite them over the CMR
boxes when rendering; rasterising the page afterwards gives the "scanned" look.
"""

from __future__ import annotations

import math
import random


def stamp_svg(text: str, rng: random.Random, size: int = 160) -> str:
    """A circular rubber-stamp: two rings, arced company text, a star, worn gaps."""
    cx = cy = size / 2
    r_out, r_in = size * 0.44, size * 0.34
    color = rng.choice(["#1c3f8f", "#8f1c1c", "#1c6b3a"])
    rot = rng.uniform(-18, 18)
    letters = text.upper()[:22]
    span, start = 220, 160  # degrees along the top arc
    chars = []
    for i, ch in enumerate(letters):
        ang = math.radians(start + (span * i / max(len(letters) - 1, 1)))
        x = cx + r_in * 1.02 * math.cos(ang)
        y = cy + r_in * 1.02 * math.sin(ang)
        deg = math.degrees(ang) + 90
        chars.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size*0.075:.0f}" '
            f'transform="rotate({deg:.1f} {x:.1f} {y:.1f})" text-anchor="middle">{ch}</text>'
        )
    # a few worn gaps as short white arcs over the outer ring
    gaps = "".join(
        f'<circle cx="{cx + r_out*math.cos(a):.1f}" cy="{cy + r_out*math.sin(a):.1f}" '
        f'r="{size*0.03:.0f}" fill="white"/>'
        for a in (rng.uniform(0, 2 * math.pi) for _ in range(rng.randint(2, 4)))
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}" opacity="0.72">'
        f'<g transform="rotate({rot:.1f} {cx} {cy})" fill="{color}" stroke="{color}" '
        f'font-family="Arial, sans-serif" font-weight="bold">'
        f'<circle cx="{cx}" cy="{cy}" r="{r_out:.1f}" fill="none" stroke-width="{size*0.02:.0f}"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r_in:.1f}" fill="none" stroke-width="{size*0.012:.0f}"/>'
        f'<text x="{cx}" y="{cy+size*0.05:.0f}" font-size="{size*0.12:.0f}" text-anchor="middle" '
        f'stroke="none">★</text>{"".join(chars)}{gaps}</g></svg>'
    )


def signature_svg(rng: random.Random, width: int = 180, height: int = 70) -> str:
    """A seeded Bézier squiggle — a plausible handwritten signature."""
    n = rng.randint(3, 5)
    x0, y0 = 8, height * 0.6
    d = [f"M {x0} {y0:.0f}"]
    x = x0
    for _ in range(n):
        x += (width - 16) / n
        c1x, c1y = x - rng.uniform(10, 30), rng.uniform(4, height - 4)
        c2x, c2y = x - rng.uniform(0, 20), rng.uniform(4, height - 4)
        ey = rng.uniform(height * 0.3, height * 0.75)
        d.append(f"C {c1x:.0f} {c1y:.0f} {c2x:.0f} {c2y:.0f} {x:.0f} {ey:.0f}")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<path d="{" ".join(d)}" fill="none" stroke="#0b1a4a" stroke-width="2" '
        f'stroke-linecap="round"/></svg>'
    )
