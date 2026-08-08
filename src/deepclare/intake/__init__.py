"""M5 Intake and Page Grouping — from uploaded files to logical documents.

In: submitted file bytes and whatever roles the client declared.
Out: logical documents, each an ordered page set with a role, every page carrying a
rendered image and whatever text was embedded in it — both *unverified candidate
evidence* — plus blocking structural errors with stable codes.

**Must not know about:** what a declaration is, what any field means beyond the
submission-level structural rules, which model will read a page, commodity codes, reuse,
or reference data. Everything in here is either a structural rule about a submission or a
mechanical transformation of bytes.

Two hard rules govern the module:

1. **Intake never decides that an embedded text layer is usable.** Text-layer presence,
   text-layer length and raster resolution are uncorrelated with extractability — in the
   measured corpus the sharpest scan carried the worst text layer — so a rule preferring
   embedded text takes the corrupt path on the densest document. Nothing here branches on
   any of the three. Comparing routes belongs to the stage that can measure both.

2. **Over-inclusion is the deliberate policy.** An `other`, missing, out-of-range or
   duplicate page verdict falls back to the source file's role hint, whose default is
   invoice, and no page is ever dropped. Losing a real invoice or consignment-note page
   loses goods from a customs filing, which is worse than carrying a stray page into a
   reader.

The stages, in order: `check_submission` (names and declared roles only) →
`route_documents` (three buckets, format classed from the bytes) → `rasterize_documents`
over `page_bearing_documents()` (every page at 200 DPI, in document order) → a page-type
classifier the caller injects → `group_pages`, which takes the routed submission back
alongside the pages.

It takes it back for a reason. A workbook and an XML have no pages, so they are never
rasterized and never classified; handed only a page list, grouping could not mention them
and they would vanish from a run that accepted them. So grouping checks that the batch
accounts for every page-bearing document and passes `page_less_documents()` through
whole. Everything that entered leaves exactly once, and a page-less invoice — which is
read directly rather than grouped — is refused here by name rather than mistaken for a
submission with no invoice page.
"""

from deepclare.intake.classifier import PageTypeClassifier, PageVerdict
from deepclare.intake.errors import (
    IntakeError,
    IntakeErrorCode,
    SubmissionProblem,
    SubmissionRejected,
)
from deepclare.intake.formats import FileFormat, detect_format, is_page_bearing
from deepclare.intake.gate import SUPPORTED_EXTENSIONS, check_submission
from deepclare.intake.grouping import (
    GroupedPage,
    GroupedSubmission,
    LogicalDocument,
    assign_page_role,
    group_pages,
)
from deepclare.intake.rasterizer import (
    PAGE_MEDIA_TYPE,
    RENDER_DPI,
    RenderedPage,
    rasterize_document,
    rasterize_documents,
)
from deepclare.intake.roles import infer_role_from_filename, role_of
from deepclare.intake.router import RoutedDocument, RoutedSubmission, route_documents
from deepclare.intake.submission import SubmittedFile

__all__ = [
    "PAGE_MEDIA_TYPE",
    "RENDER_DPI",
    "SUPPORTED_EXTENSIONS",
    "FileFormat",
    "GroupedPage",
    "GroupedSubmission",
    "IntakeError",
    "IntakeErrorCode",
    "LogicalDocument",
    "PageTypeClassifier",
    "PageVerdict",
    "RenderedPage",
    "RoutedDocument",
    "RoutedSubmission",
    "SubmissionProblem",
    "SubmissionRejected",
    "SubmittedFile",
    "assign_page_role",
    "check_submission",
    "detect_format",
    "group_pages",
    "infer_role_from_filename",
    "is_page_bearing",
    "rasterize_document",
    "rasterize_documents",
    "role_of",
    "route_documents",
]
