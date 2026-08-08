"""End-to-end check of the generative model adapter against the live provider.

Run from the repository root:

    .venv/bin/python tests/check_model_adapter.py

It makes real calls and costs real tokens. The image it sends is generated in memory —
no sample document, and nothing is written anywhere.
"""

from __future__ import annotations

import struct
import zlib

from pydantic import BaseModel, Field

from deepclare.config import load_settings
from deepclare.models import Decoding, GenerativeModel, ModelError, ModelTier, PageImage
from deepclare.prompting import render_prompt


class WordReading(BaseModel):
    language: str
    letter_count: int = Field(ge=0)
    sure: bool


class SplitImage(BaseModel):
    left_colour: str
    right_colour: str
    distinct_colours: int = Field(ge=1)


def two_tone_png(width: int, height: int) -> bytes:
    """A width x height PNG, red on the left half and blue on the right."""
    rows = b""
    for _ in range(height):
        rows += b"\x00"  # per-scanline filter: none
        for x in range(width):
            rows += b"\xff\x00\x00" if x < width // 2 else b"\x00\x00\xff"

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def report(label: str, result) -> None:
    call = result.call
    print(f"--- {label}")
    print(f"  value          {result.value!r}")
    print(f"  tier           {call.tier}")
    print(f"  model_id       {call.model_id}")
    print(f"  model_version  {call.model_version}")
    print(f"  prompt         {call.prompt_name}@{call.prompt_version}")
    print(f"  decoding       {call.decoding.model_dump()}")
    print(f"  usage          {call.usage.model_dump()}")
    print(f"  page images    {call.page_image_count}")
    print(f"  response_id    {call.response_id}")
    print()


def main() -> int:
    settings = load_settings()
    print(f"prompts_dir      {settings.prompts_dir}")
    print(f"tiers            cheap={settings.genai_model_cheap} "
          f"standard={settings.genai_model_standard} strong={settings.genai_model_strong}")
    print()

    with GenerativeModel(settings) as model:
        text_prompt = render_prompt(
            settings.prompts_dir, "adapter_check_text", {"word": "bonjour"}
        )
        for tier in (ModelTier.CHEAP, ModelTier.STANDARD, ModelTier.STRONG):
            report(
                f"text / {tier}",
                model.generate(tier=tier, prompt=text_prompt, output=WordReading),
            )

        width, height = 64, 32
        vision_prompt = render_prompt(
            settings.prompts_dir,
            "adapter_check_vision",
            {"width": str(width), "height": str(height)},
        )
        png = two_tone_png(width, height)
        print(f"generated PNG    {len(png)} bytes, {width}x{height}\n")
        report(
            "vision / standard",
            model.generate_from_pages(
                tier=ModelTier.STANDARD,
                prompt=vision_prompt,
                pages=[PageImage(media_type="image/png", content=png)],
                output=SplitImage,
            ),
        )

        # A ceiling too small to hold any answer: the call must name the failure and stop,
        # not retry and not return a half-parsed object.
        try:
            model.generate(
                tier=ModelTier.STRONG,
                prompt=text_prompt,
                output=WordReading,
                decoding=Decoding(max_output_tokens=8),
            )
        except ModelError as exc:
            print(f"--- truncation is a named error\n  {type(exc).__name__}: {exc}\n")
        else:
            print("--- truncation check DID NOT RAISE\n")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
