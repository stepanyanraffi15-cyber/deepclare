"""The evaluation harness: run the corpus, score it, and say what produced the number.

This package sits *above* the module decomposition rather than inside it. It is allowed
to import anything, and nothing imports it — a dependency from a domain module into the
harness would mean the product knows it is being measured.

Three things it will not do:

**It does not score.** `evalkit/` is a finished, stdlib-only scorer with its own
interface, and every metric below is computed from what it returns. A second
implementation of chrF or of line alignment here would be a second opinion about what
"correct" means, and the two would drift.

**It does not produce declarations.** How a case becomes XML is a parameter — a callable
taking the case's input paths and returning declaration XML. The pipeline is one such
callable; reading a file that a previous run emitted is another; there will be others.
Wiring the pipeline in here would make the harness un-runnable until the pipeline exists,
and un-runnable against anything else afterwards.

**It does not report a number without its identity.** Model ids, prompt versions and
hashes, nomenclature vintage, embedding model and width, and retrieval depth are pinned
into every report. The specification records a whole prior measurement lost because a
tuning result was written in prose while three different values of the constant it
justified shipped in the same system; an accuracy figure with no manifest is that
failure repeating.
"""

from __future__ import annotations

from deepclare.evaluation.cases import CaseInputs, CaseSelection, discover_cases, select
from deepclare.evaluation.corpus_facts import (
    CODES_ABSENT_FROM_NOMENCLATURE,
    CODES_ABSENT_PROVENANCE,
    SYNTHETIC_LABEL_CAVEAT,
)
from deepclare.evaluation.harness import score_corpus
from deepclare.evaluation.manifest import Production, RunManifest, build_manifest
from deepclare.evaluation.producers import (
    DeclarationProducer,
    ProductionFailed,
    emitted_file,
)
from deepclare.evaluation.report import (
    CaseFailure,
    CaseOutcome,
    CodeAgreement,
    EvaluationReport,
    LineOutcome,
)
from deepclare.evaluation.render import render_report

__all__ = [
    "CODES_ABSENT_FROM_NOMENCLATURE",
    "CODES_ABSENT_PROVENANCE",
    "SYNTHETIC_LABEL_CAVEAT",
    "CaseFailure",
    "CaseInputs",
    "CaseOutcome",
    "CaseSelection",
    "CodeAgreement",
    "DeclarationProducer",
    "EvaluationReport",
    "LineOutcome",
    "Production",
    "ProductionFailed",
    "RunManifest",
    "build_manifest",
    "discover_cases",
    "emitted_file",
    "render_report",
    "score_corpus",
    "select",
]
