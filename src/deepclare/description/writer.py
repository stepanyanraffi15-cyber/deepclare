"""The description writer: one goods line in, the Armenian text that gets filed out.

One call per line, and one line per call. A goods line is described from its own evidence
and from the trade its siblings establish; nothing about the shipment's other lines'
*outcomes* reaches it, so the lines are independent and reordering them changes nothing.

The call is made without the commodity code, because the code does not exist yet — this
runs before code assignment and what it writes is an input to it. It is also made without
the quantities, without the package counts and without the printed dimensions, which are
withheld rather than forbidden (see `context.py`): a figure a model cannot see is a
figure it cannot duplicate into text where deterministic arithmetic will append the real
one.

There is no retry and no repair. The first provider failure, malformed answer or
unusable answer becomes a `DescriptionError` and the line has no description — which is
work left for a human, not a wrong legal statement made by a machine.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from deepclare.description.context import LineContext
from deepclare.description.errors import DescriptionError
from deepclare.description.records import LineDescription, description_from_answer
from deepclare.description.schemas import WriteDescription
from deepclare.models import GenerativeModel, ModelError, ModelTier
from deepclare.prompting import render_prompt

WRITER_TIER = ModelTier.STANDARD
"""Writing the filed text is the heaviest language job in the run: it crosses languages,
applies a legal content rule, and produces the one string a customs officer reads. It is
not a label-emitting call and is not tiered as one."""

_UNKNOWN = "unknown"
"""A scalar the documents do not state. Absence is stated to a model, never omitted: an
absent key and an empty one are different signals, and only one of them is a fact."""

_NOTHING = "(none)"
"""A block with no entries."""


class DescriptionWriter:
    """Writes the Armenian goods description for one line at a time.

    Construct one per run with the same model client the rest of the run uses; it holds
    no state between calls.
    """

    def __init__(self, model: GenerativeModel, prompts_dir: Path) -> None:
        self._model = model
        self._prompts_dir = prompts_dir

    def write(self, context: LineContext) -> LineDescription:
        """Write one line's description, or raise `DescriptionError`."""
        prompt = render_prompt(
            self._prompts_dir, "write_description", _prompt_values(context)
        )
        try:
            result = self._model.generate(
                tier=WRITER_TIER, prompt=prompt, output=WriteDescription
            )
        except ModelError as exc:
            raise DescriptionError(
                f"line {context.line_id}: writing a description for "
                f"{context.goods_name!r} failed: {exc}"
            ) from exc
        return description_from_answer(result.value, context, result.call)


def _prompt_values(context: LineContext) -> dict[str, str]:
    """The line, rendered as the strings the prompt file names.

    Every one of them is a value or a stated absence. The labels around them, and what
    each absence means, are in the prompt file.
    """
    return {
        "goods_name": context.goods_name,
        "source_language": context.source_language.value,
        "unit_of_measure": context.unit or _UNKNOWN,
        "unit_price": _UNKNOWN if context.unit_price is None else str(context.unit_price),
        "trade_name": context.trade_name or _UNKNOWN,
        "material": context.material or _UNKNOWN,
        "known_facts": _bullets(context.grounding_facts),
        "sibling_lines": _bullets(context.sibling_names),
    }


def _bullets(entries: Iterable[str]) -> str:
    lines = [f"- {entry}" for entry in entries if entry.strip()]
    return "\n".join(lines) if lines else _NOTHING
