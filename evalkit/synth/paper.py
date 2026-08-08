"""Pillow toolkit for rendering *scanned-looking* documents.

Chosen because the real inputs are scanned image PDFs (no reliable text layer):
we draw onto a paper-tinted canvas, then degrade (skew + noise + blur) and save as
an image-only PDF — which is what a scanned invoice actually is. Pure Pillow, so it
installs with one `pip install pillow` and no system libraries.

Provides: a `Canvas` (fonts + text/line/box/table helpers), a procedural rubber
`stamp`, a `signature` squiggle, and `degrade`. All deterministic given an rng.
"""

from __future__ import annotations

import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

_FONT_PATHS = {
    False: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ],
    True: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ],
}
PAPER = (250, 249, 245)
INK = (28, 30, 38)

A4 = (1240, 1754)  # A4 at ~150 dpi


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in _FONT_PATHS[bold]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


class Canvas:
    """A paper page you draw on, then `.finish(rng)` into a degraded RGB image."""

    def __init__(self, size: tuple[int, int] = A4) -> None:
        self.img = Image.new("RGB", size, PAPER)
        self.d = ImageDraw.Draw(self.img)

    def text(self, xy, s, size=20, bold=False, fill=INK) -> None:
        self.d.text(xy, s, font=font(size, bold), fill=fill)

    def right(self, x, y, s, size=20, bold=False, fill=INK) -> None:
        w = self.d.textlength(s, font=font(size, bold))
        self.d.text((x - w, y), s, font=font(size, bold), fill=fill)

    def wrap(self, text: str, max_width: float, size: int = 18, bold: bool = False) -> list[str]:
        """Word-wrap `text` to `max_width` px — so long product names show in full."""
        f = font(size, bold)
        if not text:
            return [""]
        lines, cur = [], ""
        for word in text.split():
            trial = f"{cur} {word}".strip()
            if not cur or self.d.textlength(trial, font=f) <= max_width:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def line(self, xy, width=2, fill=(120, 124, 134)) -> None:
        self.d.line(xy, fill=fill, width=width)

    def box(self, xy, width=2, fill=(120, 124, 134)) -> None:
        self.d.rectangle(xy, outline=fill, width=width)

    def paste(self, sub: Image.Image, xy) -> None:
        self.img.paste(sub, xy, sub if sub.mode == "RGBA" else None)

    def finish(self, rng: random.Random) -> Image.Image:
        return degrade(self.img, rng)


def stamp(text: str, rng: random.Random, size: int = 210) -> Image.Image:
    """A translucent circular rubber-stamp with a fictional name — OCR-occlusion noise."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    color = rng.choice([(28, 63, 143, 205), (143, 28, 28, 205), (28, 107, 58, 205)])
    m = int(size * 0.08)
    d.ellipse([m, m, size - m, size - m], outline=color, width=int(size * 0.02))
    inner = int(size * 0.17)
    d.ellipse([inner, inner, size - inner, size - inner], outline=color, width=int(size * 0.012))
    words = text.upper().split()
    lines = [" ".join(words[:2]), " ".join(words[2:])] if len(words) > 2 else [text.upper()]
    lines = [ln for ln in lines if ln]
    fnt = font(int(size * 0.085), bold=True)
    y = size / 2 - len(lines) * size * 0.06
    for ln in lines:
        w = d.textlength(ln, font=fnt)
        d.text((size / 2 - w / 2, y), ln, font=fnt, fill=color)
        y += size * 0.11
    d.text((size / 2 - size * 0.03, size * 0.60), "★", font=font(int(size * 0.11), bold=True), fill=color)
    return im.rotate(rng.uniform(-16, 16), expand=True, resample=Image.BICUBIC)


def signature(rng: random.Random, width: int = 200, height: int = 78) -> Image.Image:
    """A seeded ink squiggle — a plausible handwritten signature."""
    im = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts, x = [], 10
    steps = rng.randint(28, 40)
    for i in range(steps):
        x = 10 + (width - 20) * i / steps
        y = height / 2 + rng.uniform(-height * 0.32, height * 0.32) * (1 if i % 2 else -1)
        pts.append((x, y))
    d.line(pts, fill=(11, 26, 74, 235), width=3, joint="curve")
    return im


def degrade(img: Image.Image, rng: random.Random) -> Image.Image:
    """Make a crisp render look scanned: slight skew, sensor noise, soft focus."""
    img = img.rotate(rng.uniform(-1.4, 1.4), expand=False, fillcolor=PAPER, resample=Image.BICUBIC)
    noise = Image.effect_noise(img.size, rng.uniform(10, 20)).convert("RGB")
    img = Image.blend(img, noise, 0.06)
    return img.filter(ImageFilter.GaussianBlur(0.5))
