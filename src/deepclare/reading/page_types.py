"""The page-type classifier: a batch of rendered pages in, one verdict per page out.

Intake declares this call as a port and never makes it — which model reads a page is not
intake's business — so the implementation lives here, beside the other vision call over
the same page images. It satisfies `PageTypeClassifier` structurally; nothing is
inherited and intake never learns that this class exists.

One call for the whole batch, images ahead of the instruction, the answer bound to a
typed schema. There is no page cap and no batching. On a long bundle that is a real
scaling hazard, and it is left visible rather than hidden behind a chunking rule: a page
split into its own chunk is judged without the pages around it, and a continuation page
is exactly the page that needs them.

**Nothing here repairs the answer.** A page the model did not answer for, answered for
twice, or numbered outside the batch comes back exactly as it arrived. The grouper
resolves all three the same way — the page stays on its source file's role hint, whose
default is invoice — so a padded or invented verdict would change nothing about where the
page lands while replacing a real signal with a fabricated one. Over-inclusion is the
policy that makes that safe: dropping a real invoice page loses goods from a customs
filing, and goods that never reach the declaration cannot be reviewed.

A provider or parse failure ends the stage. There is no retry and no re-prompt.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from deepclare.domain import PageClass
from deepclare.intake import PageVerdict, RenderedPage
from deepclare.models import GenerativeModel, ModelError, ModelTier, PageImage
from deepclare.prompting import render_prompt
from deepclare.reading.errors import ReadingError
from deepclare.reading.schemas import ClassifyPageType

PROMPT_NAME = "classify_page_type"

CLASSIFIER_TIER = ModelTier.CHEAP
"""Sorting pages emits labels and nothing else: no value is transcribed, no material or
legal distinction is drawn, and the grouper's over-inclusion policy bounds what a mistake
costs — a misjudged page lands on its file's role rather than nowhere."""


class VisionPageTypeClassifier:
    """Classifies rendered pages with a vision model.

    Construct one per run with the model client the rest of the run uses; it holds no
    state between calls.
    """

    def __init__(self, model: GenerativeModel, prompts_dir: Path) -> None:
        self._model = model
        self._prompts_dir = prompts_dir

    def classify(self, pages: Sequence[RenderedPage]) -> tuple[PageVerdict, ...]:
        """Return the model's verdicts, in the order it gave them.

        The result is not padded, deduplicated, reordered or range-checked. The port
        promises no completeness and the grouper is built to survive all three gaps.
        """
        if not pages:
            raise ValueError("page classification needs at least one rendered page")

        prompt = render_prompt(
            self._prompts_dir,
            PROMPT_NAME,
            {"page_count": str(len(pages)), "page_manifest": page_manifest(pages)},
        )
        try:
            result = self._model.generate_from_pages(
                tier=CLASSIFIER_TIER,
                prompt=prompt,
                pages=[
                    PageImage(media_type=page.media_type, content=page.image)
                    for page in pages
                ],
                output=ClassifyPageType,
            )
        except ModelError as exc:
            raise ReadingError(
                f"classifying the {len(pages)} page(s) of the submission failed: {exc}"
            ) from exc
        return verdicts_from_answer(result.value)


def page_manifest(pages: Sequence[RenderedPage]) -> str:
    """Describe the batch to the model: 1-based batch position, and the role hint.

    Positions count over the batch and not over any source file, because that is what a
    verdict's page number means and what the grouper indexes by. Two files whose first
    pages are both page 1 are positions 1 and 2 here.
    """
    entries = ",\n  ".join(
        json.dumps({"page": position, "hint": page.role_hint.value})
        for position, page in enumerate(pages, start=1)
    )
    return f"[\n  {entries}\n]"


def verdicts_from_answer(answer: ClassifyPageType) -> tuple[PageVerdict, ...]:
    """Map the provider's answer onto the port's type. Nothing is added or dropped."""
    return tuple(
        PageVerdict(page=verdict.page, page_type=PageClass(verdict.page_type))
        for verdict in answer.verdicts
    )
