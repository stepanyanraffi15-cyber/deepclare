"""Synthetic submission, entirely fictitious, generated for one-off end-to-end checks.

Writes two files:

    /tmp/invoice_synthetic.pdf   a commercial invoice, deliberately carrying a freight
                                 row that must NOT come back as a goods line
    /tmp/cmr_synthetic.pdf       the road consignment note for the same shipment, which
                                 carries the weights, the packages and the vehicles the
                                 invoice does not

Run it, then either check:

    .venv/bin/python tests/make_synthetic_invoice.py
    .venv/bin/python tests/check_reading_end_to_end.py
    python -m deepclare run /tmp/invoice_synthetic.pdf \\
        --consignment-note /tmp/cmr_synthetic.pdf --out out

No real trade document is stored in this repository. Every party, number and address below
is invented.
"""

import pypdfium2 as pdfium  # noqa: F401  (ensures the engine is installed)
from PIL import Image, ImageDraw, ImageFont

W, H = 1240, 1754  # A4 @ 150dpi
INVOICE_OUT = "/tmp/invoice_synthetic.pdf"
CMR_OUT = "/tmp/cmr_synthetic.pdf"


def f(sz, b=False):
    for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if b else
              "/System/Library/Fonts/Supplemental/Arial.ttf",
              "/System/Library/Fonts/Helvetica.ttc"):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def blank():
    img = Image.new("RGB", (W, H), "white")
    return img, ImageDraw.Draw(img)


def invoice_page():
    img, d = blank()
    d.text((60, 50), "NORDVEK PLASTICS LLC", font=f(30, True), fill="black")
    d.text((60, 92), "Fabrikkveien 14, 7010 Trondheim, Norway", font=f(18), fill="black")
    d.text((60, 116), "Org. no. NO 981 234 567 MVA", font=f(18), fill="black")
    d.text((60, 175), "COMMERCIAL INVOICE", font=f(26, True), fill="black")
    d.text((60, 215), "Invoice No: NV-2026-0431", font=f(18), fill="black")
    d.text((60, 240), "Date: 14.07.2026", font=f(18), fill="black")
    d.text((700, 215), "Buyer:", font=f(18, True), fill="black")
    d.text((700, 240), "ARARAT IMPORT LLC", font=f(18), fill="black")
    d.text((700, 264), "12 Tigran Mets Ave, Yerevan, Armenia", font=f(16), fill="black")
    d.text((700, 288), "TIN: 01234567", font=f(16), fill="black")
    d.text((60, 320), "Terms: CIP YEREVAN            Currency: EUR", font=f(18), fill="black")

    y = 380
    d.line((60, y - 10, 1180, y - 10), fill="black", width=2)
    for x, t in ((65, "No"), (120, "Description"), (560, "HS Code"), (690, "Qty"),
                 (790, "Unit"), (880, "Pkgs"), (960, "Net kg"), (1070, "Amount")):
        d.text((x, y), t, font=f(17, True), fill="black")
    d.line((60, y + 26, 1180, y + 26), fill="black", width=2)

    rows = [
        ("1", "Plastic storage box 40x60 cm, blue", "3923101000", "480", "PCS", "40", "624.0", "3 840.00"),
        ("2", "Polyethylene bottle 1 L, natural", "3923301000", "1200", "PCS", "24", "384.0", "2 160.00"),
        ("3", "PP woven sack 50 kg, printed", "3923210000", "5000", "PCS", "50", "750.0", "4 250.00"),
        ("4", "Freight charge Trondheim - Yerevan", "", "1", "LOT", "", "", "1 450.00"),
    ]
    y += 40
    for r in rows:
        for x, t in zip((65, 120, 560, 690, 790, 880, 960, 1070), r):
            d.text((x, y), t, font=f(16), fill="black")
        y += 34
    d.line((60, y + 4, 1180, y + 4), fill="black", width=1)
    d.text((880, y + 18), "TOTAL EUR", font=f(18, True), fill="black")
    d.text((1070, y + 18), "11 700.00", font=f(18, True), fill="black")
    d.text((60, y + 70), "Goods total (excl. freight): EUR 10 250.00", font=f(16), fill="black")
    d.text((60, y + 100), "Gross weight: 1 890 kg    Packages: 114 CARTONS", font=f(16), fill="black")
    d.text((60, y + 130), "Country of origin: NORWAY", font=f(16), fill="black")
    return img


def consignment_note_page():
    """The same shipment's CMR. It carries what the invoice does not: the gross weight,
    the package count and type, the vehicles, and the places of loading and delivery."""
    img, d = blank()
    d.rectangle((60, 50, 1180, 1500), outline="black", width=2)
    d.text((80, 62), "CMR", font=f(34, True), fill="black")
    d.text((300, 70), "INTERNATIONAL CONSIGNMENT NOTE", font=f(20, True), fill="black")
    d.text((300, 98), "LETTRE DE VOITURE INTERNATIONALE", font=f(16), fill="black")
    d.text((980, 70), "No. 8823714", font=f(18, True), fill="black")

    boxes = (
        (60, 140, 620, 300, "1  Sender / Expediteur",
         ("NORDVEK PLASTICS LLC", "Fabrikkveien 14", "7010 Trondheim, NORWAY")),
        (620, 140, 1180, 300, "16  Carrier / Transporteur",
         ("BALTIC ROAD CARGO UAB", "Savanoriu pr. 178", "03154 Vilnius, LITHUANIA")),
        (60, 300, 620, 460, "2  Consignee / Destinataire",
         ("ARARAT IMPORT LLC", "12 Tigran Mets Ave", "0005 Yerevan, ARMENIA")),
        (620, 300, 1180, 460, "3  Place of delivery",
         ("Yerevan, ARMENIA", "", "")),
        (60, 460, 620, 600, "4  Place and date of taking over the goods",
         ("Trondheim, NORWAY", "16.07.2026", "")),
        (620, 460, 1180, 600, "5  Documents attached",
         ("Invoice NV-2026-0431", "Packing list", "Certificate of origin")),
    )
    for left, top, right, bottom, title, lines in boxes:
        d.rectangle((left, top, right, bottom), outline="black", width=1)
        d.text((left + 14, top + 10), title, font=f(15, True), fill="black")
        for index, line in enumerate(lines):
            d.text((left + 14, top + 40 + index * 26), line, font=f(17), fill="black")

    d.rectangle((60, 600, 1180, 900), outline="black", width=1)
    for x, title in ((74, "6  Marks and Nos"), (400, "7  Number of packages"),
                     (700, "8  Method of packing"), (960, "11  Gross weight kg")):
        d.text((x, 612), title, font=f(15, True), fill="black")
    for x, value in ((74, "ARARAT/YER"), (400, "114"), (700, "CARTONS"), (960, "1 890")):
        d.text((x, 646), value, font=f(18), fill="black")
    d.text((74, 700), "9  Nature of the goods", font=f(15, True), fill="black")
    d.text((74, 734), "PLASTIC HOUSEHOLD ARTICLES AND SACKS IN CARTONS",
           font=f(18), fill="black")

    d.rectangle((60, 900, 1180, 1060), outline="black", width=1)
    d.text((74, 912), "25  Vehicle registration", font=f(15, True), fill="black")
    d.text((74, 946), "LT 8823 TK  /  LT 4419 PR", font=f(18), fill="black")
    d.text((620, 912), "21  Established in", font=f(15, True), fill="black")
    d.text((620, 946), "Trondheim, on 16.07.2026", font=f(18), fill="black")

    d.rectangle((60, 1060, 1180, 1300), outline="black", width=1)
    for x, title in ((74, "22  Signature of the sender"),
                     (450, "23  Signature of the carrier"),
                     (830, "24  Goods received")):
        d.text((x, 1072), title, font=f(15, True), fill="black")
    return img


if __name__ == "__main__":
    invoice_page().save(INVOICE_OUT, "PDF", resolution=150.0)
    print(f"wrote {INVOICE_OUT}")
    consignment_note_page().save(CMR_OUT, "PDF", resolution=150.0)
    print(f"wrote {CMR_OUT}")
