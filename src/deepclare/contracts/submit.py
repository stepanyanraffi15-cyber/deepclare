"""What a client sends to start a run.

Mirrors, rather than imports, the declarant-profile shapes M11 defines
(`deepclare.assembly.inputs`). A contract that imported them directly would break the
moment M11 renamed a field internally — the whole reason a contract is a separate,
additively-versioned type. `DocumentRole` is the one exception: it is M1 domain
vocabulary, not an M11 internal, and file 10 names M1 concepts as M2's legitimate input.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from deepclare.domain import DocumentRole


class SubmittedFileIn(BaseModel):
    """One uploaded file, as it travels over JSON.

    `content_base64` exists because raw bytes cannot ride JSON; M15 decodes it into the
    `bytes` a `SubmittedFile` actually carries. Decode failures are refused at the edge,
    named by file, rather than surfacing later as an unreadable document.
    """

    model_config = ConfigDict(frozen=True)

    file_name: str = Field(min_length=1)
    content_base64: str = Field(min_length=1)
    declared_role: DocumentRole | None = None


class GoodsLocationProfileIn(BaseModel):
    """Box 30 — where this importer's goods sit while they clear."""

    model_config = ConfigDict(frozen=True)

    information_type_code: str = "11"
    customs_office_code: str = "05100010"
    country_code: str = "AM"
    customs_zone_number: str | None = None
    confirmed: bool = False


class FillerProfileIn(BaseModel):
    """Box 54 — the person completing the declaration."""

    model_config = ConfigDict(frozen=True)

    surname: str = Field(min_length=1)
    given_name: str = Field(min_length=1)
    phone: str | None = None
    email: str | None = None


class ImporterProfileIn(BaseModel):
    """The importing company, for the runs where the documents do not name it."""

    model_config = ConfigDict(frozen=True)

    name: str | None = None
    tax_code: str | None = None
    street_house: str | None = None


class DeclarantProfileIn(BaseModel):
    """Everything about the declarant that no document carries."""

    model_config = ConfigDict(frozen=True)

    goods_location: GoodsLocationProfileIn | None = None
    filler: FillerProfileIn | None = None
    importer: ImporterProfileIn | None = None


class SubmitRunRequest(BaseModel):
    """One run's whole ask, over the wire.

    Structural acceptance — at least one file, exactly what `RunInput` itself requires —
    is checked again at M15's edge before a job is even queued, the same "refuse a
    structurally impossible submission at submission time" rule file 09 §6.4 records.
    """

    model_config = ConfigDict(frozen=True)

    files: tuple[SubmittedFileIn, ...] = Field(min_length=1)
    profile: DeclarantProfileIn = DeclarantProfileIn()
