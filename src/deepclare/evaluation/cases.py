"""Finding the cases in a corpus directory and choosing which of them to run.

A case is a directory holding the ground-truth declaration. Everything else it carries —
the invoice as a PDF, the same invoice as a workbook, the consignment note, the per-line
attribute atoms — is optional, because a corpus is allowed to grow shapes this build has
not seen and a missing file must be visible rather than fatal.

Selection is a prefix of the sorted case list, not a sample. Seventy-one full pipeline
runs is a lot of tokens and the common use is a quick read, so the subset has to be cheap
to name and identical between runs. It is also biased by construction, which is why the
selection rule is recorded on the report rather than left for a reader to assume.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

GROUND_TRUTH_XML = "ground_truth.xml"
GROUND_TRUTH_ATOMS = "ground_truth.json"
INVOICE_PDF = "invoice.pdf"
INVOICE_WORKBOOK = "invoice.xlsx"
CONSIGNMENT_NOTE_PDF = "cmr.pdf"


class CorpusError(RuntimeError):
    """The corpus directory is missing, empty, or not laid out as cases."""


class CaseInputs(BaseModel):
    """One case: the documents a producer is given, and the truth it is scored against.

    Paths rather than bytes, because a producer may want to hand a file to a rasterizer,
    a workbook reader, or nothing at all, and the harness has no business deciding which.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    """Path of the case relative to the corpus root — `oneToOne/case-001`. Cases are
    nested by product family, so the leaf directory name alone is not unique."""

    directory: Path
    ground_truth_xml: Path
    ground_truth_atoms: Path | None = None
    invoice_pdf: Path | None = None
    invoice_workbook: Path | None = None
    consignment_note_pdf: Path | None = None

    def atoms(self) -> list[dict] | None:
        """The per-line brand / trade name / material atoms, if the case carries them.

        With them the description rubric is exact; without them it falls back to
        detection from the reference text and asserts less. Absence is not an error.
        """
        if self.ground_truth_atoms is None:
            return None
        data = json.loads(self.ground_truth_atoms.read_text(encoding="utf-8"))
        goods = data.get("goods") if isinstance(data, dict) else data
        return goods if isinstance(goods, list) else None


class CaseSelection(BaseModel):
    """The cases this run will score, and the rule that chose them."""

    model_config = ConfigDict(frozen=True)

    cases: tuple[CaseInputs, ...]
    available: int
    rule: str


def discover_cases(corpus_dir: Path) -> list[CaseInputs]:
    """Every directory under `corpus_dir` holding a ground-truth declaration.

    Recursive, because the corpus groups cases by product family.
    """
    root = Path(corpus_dir)
    if not root.is_dir():
        raise CorpusError(f"no such corpus directory: {root}")

    directories = sorted({path.parent for path in root.rglob(GROUND_TRUTH_XML)})
    if not directories:
        raise CorpusError(
            f"{root} holds no case: nothing under it is a directory containing "
            f"{GROUND_TRUTH_XML}."
        )

    return [_case(root, directory) for directory in directories]


def select(cases: list[CaseInputs], limit: int | None) -> CaseSelection:
    """The first `limit` cases in name order, or all of them when `limit` is None."""
    if limit is None:
        return CaseSelection(
            cases=tuple(cases), available=len(cases), rule="every case in the corpus"
        )
    if limit < 1:
        raise CorpusError(f"a case limit must be at least 1, got {limit}")

    chosen = cases[:limit]
    rule = (
        f"the first {len(chosen)} of {len(cases)} cases in name order — a prefix, "
        "not a random sample, so it is reproducible and it is biased"
    )
    return CaseSelection(cases=tuple(chosen), available=len(cases), rule=rule)


def _case(root: Path, directory: Path) -> CaseInputs:
    def present(filename: str) -> Path | None:
        path = directory / filename
        return path if path.exists() else None

    return CaseInputs(
        name=str(directory.relative_to(root)),
        directory=directory,
        ground_truth_xml=directory / GROUND_TRUTH_XML,
        ground_truth_atoms=present(GROUND_TRUTH_ATOMS),
        invoice_pdf=present(INVOICE_PDF),
        invoice_workbook=present(INVOICE_WORKBOOK),
        consignment_note_pdf=present(CONSIGNMENT_NOTE_PDF),
    )
