"""The shape the model is asked to answer in.

Everything in this module reaches the provider. A Pydantic class docstring becomes the
schema's `description` and a `Field(description=...)` becomes the property's — both are
prompt text, and prompt text lives in `write_description.md`, which is reviewed together
with this file. The two reach the model as one artifact, and a rule stated in one and
contradicted by the other is how they silently drift apart. So nothing here carries prose
and the notes below are `#` comments, which stay in this file.

The two closed vocabularies are spelled as literals rather than as the domain
enumerations they map onto, for the same reason: an enum class carries its docstring into
the generated schema. `records.py` maps these strings onto the domain types.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class WriteDescription(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Property order is generation order. The description is written first and everything
    # after it is a judgement about goods the model has now committed to identifying:
    # the search term is the category it filed under, the kind follows from what the
    # product is, and the grounding self-report can only be made once there is text to
    # grade.
    description: str
    search_term: str
    product_kind: Literal["piece", "weight", "length", "area", "volume"]
    completeness: Literal["high", "medium", "low"]
