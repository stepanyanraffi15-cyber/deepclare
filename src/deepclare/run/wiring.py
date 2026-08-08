"""The composition root: settings in, ports out, and every resource closed after.

This is the only module in the package that knows a provider exists, and it is not part
of the chain — it builds what the chain is handed and then gets out of the way. It reads
no environment of its own either: the settings object arrives as an argument, having been
read once at the process edge, so a caller with a different settings object gets a
different run and nothing global changes.

**The embedded vector store takes an exclusive lock on its directory.** One process, one
client, and a second one opened anywhere in the same run fails with a lock error rather
than degrading. That is why the client is created here, once, and closed on the way out —
and why this is a context manager rather than a factory returning an object nobody owns.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from deepclare.assembly.tables import load_tables
from deepclare.classification.classifier import Classifier
from deepclare.classification.existence import ExistenceGate
from deepclare.classification.features import ClassificationFeatures
from deepclare.config import Settings
from deepclare.consistency.reconcile import Reconciler
from deepclare.description.writer import DescriptionWriter
from deepclare.embedding import GeminiEmbedder
from deepclare.intake.router import RoutedDocument
from deepclare.models import GenerativeModel
from deepclare.reading.page_types import VisionPageTypeClassifier
from deepclare.reading.records import InvoiceReading
from deepclare.reading.spreadsheet import read_workbook_invoice
from deepclare.reading.vision import DocumentReader
from deepclare.reference.store import NomenclatureStore
from deepclare.run.ports import Ports

logger = logging.getLogger(__name__)


class WorkbookReader:
    """The spreadsheet path, bound to the model and the prompt directory it needs.

    M6 exposes it as a function of three arguments because that is what it is; the chain
    is handed an object with one method because a stage must not know that a model exists.
    Binding the two together is exactly what a composition root is for.

    The workbook read produces more than the record — which numeric cells would not parse,
    which sheet lost its column labelling — and none of that reaches the review report yet.
    It is logged rather than dropped.
    """

    def __init__(self, model: GenerativeModel, prompts_dir: Path) -> None:
        self._model = model
        self._prompts_dir = prompts_dir

    def read_invoice(self, document: RoutedDocument) -> InvoiceReading:
        read = read_workbook_invoice(document, self._model, self._prompts_dir)
        logger.info(
            "workbook read: goods from %s, %d sheet(s), %d column(s) with unreadable "
            "numbers%s",
            read.goods_source,
            len(read.sheets),
            len(read.unread_numbers),
            "" if read.labelling_failure is None else f", {read.labelling_failure}",
        )
        return read.reading


@contextmanager
def open_ports(
    settings: Settings,
    *,
    features: ClassificationFeatures | None = None,
    classify_pages: bool = True,
    reconcile_lines: bool = True,
) -> Iterator[Ports]:
    """Build every capability a run needs, and release them all afterwards.

    The two flags turn optional stages off by withholding the port rather than by passing
    a switch into the chain: a stage that cannot be reached because its capability is
    absent is a stronger statement than a stage that checks a boolean, and it is what
    makes "the run is a pure function of its input and its ports" true.
    """
    from qdrant_client import QdrantClient

    tables = load_tables(settings.reference_tables_dir)
    embedder = GeminiEmbedder(settings)
    client = QdrantClient(path=str(settings.qdrant_path))
    model = GenerativeModel(settings)
    try:
        store = NomenclatureStore(
            artifact_dir=settings.reference_dir,
            qdrant_client=client,
            collection=settings.qdrant_collection,
            embedder=embedder,
        )
        logger.info(
            "nomenclature vintage %s, embeddings %s at %d dimensions",
            store.vintage,
            *store.embedding_pairing,
        )
        yield Ports(
            reader=DocumentReader(model, settings.prompts_dir),
            classifier=Classifier(
                store=store,
                model=model,
                prompts_dir=settings.prompts_dir,
                features=features or ClassificationFeatures(),
            ),
            description_writer=DescriptionWriter(model, settings.prompts_dir),
            tables=tables,
            page_classifier=(
                VisionPageTypeClassifier(model, settings.prompts_dir)
                if classify_pages
                else None
            ),
            workbook_reader=WorkbookReader(model, settings.prompts_dir),
            # No evidence enricher exists in this build. The port is declared and the
            # branch is real; nothing implements it yet, and the run says so rather than
            # pretending the supporting documents were read.
            evidence_enricher=None,
            reconciler=(
                Reconciler(
                    existence_gate=ExistenceGate(store),
                    model=model,
                    prompts_dir=settings.prompts_dir,
                )
                if reconcile_lines
                else None
            ),
        )
    finally:
        model.close()
        embedder.close()
        client.close()
