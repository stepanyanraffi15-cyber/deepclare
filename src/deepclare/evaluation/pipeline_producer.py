"""Running the real pipeline over a corpus case, so the harness scores this system.

The harness takes production as a parameter — a callable from a case's inputs to
declaration XML — so that it can be exercised on already-emitted files without a provider
anywhere near it. This is the other implementation: the one that actually drafts.

It lives here rather than in `run/` because the dependency belongs this way round.
Evaluation knows about the pipeline; the pipeline must not know it is being evaluated.
Dossier 10 §3 M17: no evaluation path may be reachable from a production run, and no
production behaviour may vary on whether it is being measured.

**The ports are opened once and shared across every case.** The vector store is embedded
and exclusive-locked to a single process, so opening it per case would fail on the second
one — and re-opening it per case would also reload the index each time, which is the cost
this loop can least afford.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from deepclare.config import Settings
from deepclare.domain import DocumentRole
from deepclare.evaluation.cases import CaseInputs
from deepclare.evaluation.producers import DeclarationProducer, ProductionFailed
from deepclare.intake import SubmittedFile

logger = logging.getLogger(__name__)


@contextmanager
def drafting_producer(
    settings: Settings, *, classify_pages: bool = True, reconcile_lines: bool = True
) -> Iterator[DeclarationProducer]:
    """Yield a producer that drafts each case with the real pipeline.

    A context manager because the ports it holds own a process-exclusive vector store and
    an HTTP pool, and both must be released whether the loop finishes or fails.
    """
    from deepclare.run import RunInput, RunOptions, execute, open_ports

    # The defaults every case is drafted under, recorded once so the report can pin
    # them. A RunInput needs a file, so the options are taken from their own type.
    options = RunOptions()

    with open_ports(
        settings,
        features=options.classification_features,
        classify_pages=classify_pages,
        reconcile_lines=reconcile_lines,
    ) as ports:

        def produce(case: CaseInputs) -> str:
            files = _submitted_files(case)
            try:
                state = execute(RunInput(files=tuple(files), options=options), ports)
                return state.require_filed().xml
            except Exception as exc:
                # Named rather than swallowed: a case that could not be drafted is a
                # result the report has to show, not a gap it should quietly skip.
                raise ProductionFailed(
                    f"{case.name}: the pipeline did not produce a declaration: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

        yield produce


def _submitted_files(case: CaseInputs) -> list[SubmittedFile]:
    """The documents a broker would have had, in the roles they arrive under.

    The PDF invoice is preferred over the workbook when a case carries both: they are two
    renderings of one shipment, and the scanned path is the one real submissions use.
    """
    invoice = case.invoice_pdf or case.invoice_workbook
    if invoice is None:
        raise ProductionFailed(f"{case.name}: the case carries no invoice to read")

    files = [_read(invoice, DocumentRole.INVOICE)]
    if case.consignment_note_pdf is not None:
        files.append(_read(case.consignment_note_pdf, DocumentRole.CONSIGNMENT_NOTE))
    return files


def _read(path, role: DocumentRole) -> SubmittedFile:
    return SubmittedFile(
        file_name=path.name, content=path.read_bytes(), declared_role=role
    )
