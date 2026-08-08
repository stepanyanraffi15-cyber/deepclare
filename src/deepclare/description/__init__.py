"""M8 Description Composition — the Armenian text a customs officer reads.

In: one extracted goods line, its deterministic per-line context (the script it is
written in, the trade its sibling lines establish, the facts supporting documents state),
and nothing else.

Out, per line: the goods description in Armenian; a short Armenian generic-noun term the
commodity-code lookup searches with; the product kind, which is what the goods physically
are rather than what the invoice's unit column says; and a grounding self-report.

**Must not know about the commodity code.** This module runs before code assignment and
its output is an input to it. A dependency on a code would invert the graph, so there is
none — not a code passed in and ignored, not one read from anywhere.

**Must not know about the filed document.** Not its element names, not its per-element
length limit, not how long text is split across sibling elements. A target length could
be passed in as a plain number; the splitting and truncation rules belong to the filing
adapter. This module also does not compose the size and quantity segments that are
appended to its text: those need resolved package and quantity figures and belong to
assembly.

**Must not know about tenancy, jobs or persistence**, and there is no search of anyone's
prior filings anywhere in it.

Three rules govern what it writes:

1. **Stated only.** The manufacturer, an article or standard designation and a
   composition percentage appear only where a source document states them, copied
   verbatim. Omitting one because the documents are silent is always correct; inventing
   one never is. A figure the documents do not carry is refused rather than filed.

2. **No figure is the model's own.** Every number in the filed text is computed
   arithmetic from elsewhere. The quantities, package counts and dimensions are withheld
   from the call rather than forbidden in the prompt, because a prohibition backed by
   omission cannot be violated.

3. **A failure produces nothing, never a stand-in.** There is no retry, no repair and no
   fallback to a generic Armenian noun; a missing description is work left for a human,
   and a stand-in filed as though it were a description is the failure this product
   exists to avoid.
"""

from deepclare.description.context import (
    MAX_SIBLINGS,
    SIBLING_EXCERPT_CHARS,
    LineContext,
    build_line_contexts,
    detect_source_language,
)
from deepclare.description.errors import DescriptionError
from deepclare.description.records import (
    STAGE,
    DescriptionCompleteness,
    LineDescription,
    ProductKind,
    description_from_answer,
)
from deepclare.description.schemas import WriteDescription
from deepclare.description.writer import WRITER_TIER, DescriptionWriter

__all__ = [
    "MAX_SIBLINGS",
    "SIBLING_EXCERPT_CHARS",
    "STAGE",
    "WRITER_TIER",
    "DescriptionCompleteness",
    "DescriptionError",
    "DescriptionWriter",
    "LineContext",
    "LineDescription",
    "ProductKind",
    "WriteDescription",
    "build_line_contexts",
    "description_from_answer",
    "detect_source_language",
]
