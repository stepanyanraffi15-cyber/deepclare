"""The shapes the models are asked to answer in.

Everything in this module reaches the provider. A Pydantic class docstring becomes the
schema's `description` and a `Field(description=...)` becomes the property's — both are
prompt text, and prompt text lives in the prompt files, which are reviewed together with
this module. So nothing here carries prose and the notes below are `#` comments, which
stay in this file.

That rule dissolves a defect the specification records: in the system it describes, the
verifier's prompt and the verifier's output schema instruct opposite behaviour on the
same condition — the schema says reject when unsure, the prompt says accept even when
unsure — and both reach the model. With the schema carrying no prose there is only one
place the doctrine can be stated, so the two halves cannot disagree.

Property order is generation order, and in two places it is a forcing device: the model
must write what the goods fundamentally *are* before it may name a code.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Probability = Annotated[float, Field(ge=0.0, le=1.0)]


class ShortlistChapters(BaseModel):
    model_config = ConfigDict(frozen=True)

    # The identity statement is written first so that the material-or-function decision
    # is made explicitly rather than inferred backwards from a chapter the model already
    # committed to.
    identity: str
    chapters: list[str]
    reasoning: str


class PickHeading(BaseModel):
    model_config = ConfigDict(frozen=True)

    headings: list[str]
    search_text: str
    reasoning: str


class PreferSubheading(BaseModel):
    model_config = ConfigDict(frozen=True)

    subheadings: list[str]
    reasoning: str


class PickCode(BaseModel):
    model_config = ConfigDict(frozen=True)

    # `identification` before the decision, for the same reason as the chapter call. The
    # material verdicts come before the abstain flag because on a material split they are
    # what decides it.
    identification: str
    material_decisive: bool
    material_assumed: str
    abstain: bool
    chosen_code: str
    llm_confidence: Probability
    rationale: str
    missing_evidence: str
    legal_basis: str


class VerifyCode(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: str
    correct: bool
