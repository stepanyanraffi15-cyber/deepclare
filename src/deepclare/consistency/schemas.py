"""The shapes the two models are asked to answer in.

Everything in this module reaches the provider. A Pydantic class docstring becomes the
schema's `description` and a `Field(description=...)` becomes the property's — both are
prompt text, and prompt text lives in `critique_lines.md` and `conform_lines.md`, which
are reviewed together with this file. So nothing here carries prose and the notes below
are `#` comments, which stay in this file.

Two absences are the point rather than an oversight:

* **No quantity, weight, package count or price on either shape.** This module never sets
  a quantity figure, and a field a model is not given cannot be filled in.
* **No supplementary unit on the rewrite shape.** The tariff's own unit for a code is a
  fact of the nomenclature, and this module may not read the nomenclature for anything
  but the existence check. A stated unit would be a generated tariff fact, which is the
  one kind of value this product refuses to file.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class CritiqueIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Field order is reading order: name the line, then the field, then the problem, and
    # only then a value — so a suggestion is written after the problem it answers.
    line_id: str
    field: Literal["description", "code", "supplementary_unit"]
    problem: str
    suggested_value: str


class CritiqueLines(BaseModel):
    model_config = ConfigDict(frozen=True)

    issues: list[CritiqueIssue]
    shipment_notes: list[str]


class ConformedLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    line_id: str
    description: str
    code: str


class ConformLines(BaseModel):
    model_config = ConfigDict(frozen=True)

    lines: list[ConformedLine]
