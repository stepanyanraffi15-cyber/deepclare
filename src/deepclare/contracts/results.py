"""What a finished run hands back.

`ReviewReport` (M13) is reused directly rather than mirrored — unlike `RunState`, it is
already M13's designated client-facing projection ("assemble the human-facing account of
a run", dossier file 10 §3 M13), composed entirely of JSON-safe types. Duplicating its
six nested shapes here would be exactly the drifting second copy this package exists to
prevent, for no client benefit. `RunState` itself never crosses this boundary — it
carries an XML `Element` tree and rendered page images, which are M14's business and are
not serializable in the first place.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from deepclare.review.report import ReviewReport


class RunSummary(BaseModel):
    """The counts `format_summary()` prints, structured instead of rendered."""

    model_config = ConfigDict(frozen=True)

    goods_line_count: int
    codes_assigned: int
    codes_abstained: int
    conforms: bool
    """No rule the filing adapter can decide is violated."""
    filable: bool
    """Conforms, and nothing about the contract itself remains unconfirmed. Today this
    is always false — 18 element names and the container child order are unconfirmed
    against a real accepted filing — and a client must say so rather than imply the
    document is ready to import."""
    notes: tuple[str, ...] = ()


class RunResult(BaseModel):
    """A completed run, over the wire. Read-only: no field here is written back through
    this contract. Editing a completed declaration is not yet a pipeline capability —
    see the artifact's build-order note — so this v1 does not offer it."""

    model_config = ConfigDict(frozen=True)

    declaration_xml: str
    review_report: ReviewReport
    summary: RunSummary
