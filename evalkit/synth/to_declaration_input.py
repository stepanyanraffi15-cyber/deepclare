"""Render the ground truth via the REAL pipeline renderer, so it's portal-valid.

A hand-rolled minimal XML (see render_xml.py) is fine for scoring but is NOT an
importable declaration — the portal rejects it ("file type doesn't match content")
because it lacks the prolog, the namespaced root, and the schemaLocation. The
pipeline's own `declaration.render` emits exactly the importable ESADout_CU form the
portal accepts, so we build a `DeclarationInput` from a synthetic `Case` and drive it.

Dev-only: this imports the agent (`mootq_agent`), so it works when generating in this
repo (run with `src` on PYTHONPATH). Where the agent is absent, the CLI falls back to
the minimal renderer — the committed corpus already holds the real XML either way.
"""

from __future__ import annotations

from mootq_agent.pipeline.classify.models import CommodityClassification
from mootq_agent.pipeline.declaration.models import (
    Address,
    DeclarantProfile,
    DeclarationInput,
    DeclarationLine,
    FilledPerson,
    GoodsLocationProfile,
)
from mootq_agent.pipeline.declaration.render import render
from mootq_agent.pipeline.naming.models import GoodsNaming
from mootq_agent.pipeline.scan.schemas import GoodsLine, InvoiceData, Party

from .ir import Case

_FILLER = FilledPerson(surname="Բրոքեր", name="Փորձնական")  # obviously-synthetic

# The seed pool holds the declaration's unit CODE; the renderer derives the code back from a
# scan-style unit STRING, so map code -> a string that round-trips to it.
_CODE_TO_UNIT = {"166": "KG", "796": "PCS", "112": "L", "006": "M", "055": "M2", "113": "M3"}


def build_declaration_input(case: Case) -> DeclarationInput:
    scan_goods: list[GoodsLine] = []
    lines: list[DeclarationLine] = []
    for i, g in enumerate(case.goods, 1):
        scan_line = GoodsLine(
            line_number=i,
            description=g.source_name,
            quantity=g.quantity,
            unit=_CODE_TO_UNIT.get(g.unit, "KG"),
            gross_weight=g.gross_weight,
            net_weight=g.net_weight,
            weight_unit="KG",
            unit_price=g.unit_price,
            total_price=g.invoiced_cost,
            package_count=g.package_count,
            package_type=g.package_type,
            origin_country=g.origin,
            trade_name=g.trade_name,
            hs_code=g.hs_code,
        )
        scan_goods.append(scan_line)
        lines.append(
            DeclarationLine(
                scan_line=scan_line,
                naming=GoodsNaming(
                    id=str(i),
                    source_name=g.source_name,
                    description=g.armenian_desc,  # our ground-truth wording, filed verbatim
                    search_term=g.trade_name or g.source_name,
                    measure_unit=None,
                ),
                classification=CommodityClassification(
                    id=str(i),
                    tnved_code=g.hs_code,
                    confidence=1.0,
                    candidates=[],
                    rationale="synthetic",
                    needs_review=False,
                ),
            )
        )

    invoice = InvoiceData(
        invoice_number=case.invoice_no,
        invoice_date=case.date,
        currency=case.currency,
        incoterms=case.incoterms,
        origin_country=case.dispatch_country,
        seller=Party(name=case.seller.name, address=case.seller.address),
        buyer=Party(name=case.buyer.name, address=case.buyer.address, tax_code=case.buyer.tax_id),
        goods=scan_goods,
        total_amount=case.total_cost,
    )
    declarant = DeclarantProfile(
        organization_name=case.buyer.name,
        unn=case.buyer.tax_id or "00000000",
        address=Address(street_house=case.buyer.address, city="Երևան"),
        goods_location=GoodsLocationProfile(),
    )
    return DeclarationInput(invoice=invoice, lines=lines, declarant=declarant, filler=_FILLER)


def render_ground_truth(case: Case) -> str:
    """The portal-importable ESADout_CU declaration for this case."""
    return render(build_declaration_input(case)).xml.decode("utf-8")
