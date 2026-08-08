"""Synthetic two-page bundle, entirely fictitious: page 1 a commercial invoice, page 2 a
CMR road consignment note, scanned into one file.

That is the case the page classifier exists for — one uploaded PDF holding two documents,
where reading them as one lets a consignee off the note land on the invoice. Both parties,
numbers and goods are invented; no real trade document is stored in this repository.

    .venv/bin/python tests/make_synthetic_bundle.py
"""

from PIL import Image, ImageDraw, ImageFont

W, H = 1240, 1754  # A4 at 150 dpi
OUT = "/tmp/bundle_synthetic.pdf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def blank() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (W, H), "white")
    return image, ImageDraw.Draw(image)


def invoice_page() -> Image.Image:
    image, d = blank()
    d.text((60, 50), "HELLAS CERAMICA S.A.", font=font(30, True), fill="black")
    d.text((60, 92), "Odos Marathonos 88, 19005 Attiki, Greece", font=font(18), fill="black")
    d.text((60, 116), "VAT EL 998 776 554", font=font(18), fill="black")

    d.text((60, 175), "COMMERCIAL INVOICE", font=font(26, True), fill="black")
    d.text((60, 215), "Invoice No: HC-2026-1187", font=font(18), fill="black")
    d.text((60, 240), "Date: 03.06.2026", font=font(18), fill="black")
    d.text((700, 215), "Buyer:", font=font(18, True), fill="black")
    d.text((700, 240), "SEVAN TRADING LLC", font=font(18), fill="black")
    d.text((700, 264), "5 Komitas Ave, Yerevan, Armenia", font=font(16), fill="black")
    d.text((700, 288), "TIN: 07766554", font=font(16), fill="black")
    d.text((60, 320), "Terms: CPT YEREVAN            Currency: EUR", font=font(18), fill="black")

    y = 380
    d.line((60, y - 10, 1180, y - 10), fill="black", width=2)
    for x, title in (
        (65, "No"),
        (120, "Description"),
        (600, "Qty"),
        (700, "Unit"),
        (800, "Pkgs"),
        (900, "Net kg"),
        (1040, "Amount"),
    ):
        d.text((x, y), title, font=font(17, True), fill="black")
    d.line((60, y + 26, 1180, y + 26), fill="black", width=2)

    rows = (
        ("1", "Glazed ceramic floor tile 60x60 cm, beige", "1 800", "M2", "90", "27 000", "14 400.00"),
        ("2", "Ceramic wall tile 25x40 cm, white gloss", "960", "M2", "48", "11 520", "6 240.00"),
        ("3", "Tile adhesive, cement based, 25 kg bag", "400", "BAG", "20", "10 000", "2 800.00"),
        ("4", "Road freight Attiki - Yerevan", "1", "LOT", "", "", "3 100.00"),
    )
    y += 40
    for row in rows:
        for x, cell in zip((65, 120, 600, 700, 800, 900, 1040), row):
            d.text((x, y), cell, font=font(16), fill="black")
        y += 34

    d.line((60, y + 4, 1180, y + 4), fill="black", width=1)
    d.text((800, y + 18), "TOTAL EUR", font=font(18, True), fill="black")
    d.text((1040, y + 18), "26 540.00", font=font(18, True), fill="black")
    d.text((60, y + 70), "Goods total (excl. freight): EUR 23 440.00", font=font(16), fill="black")
    d.text((60, y + 100), "Country of origin: GREECE", font=font(16), fill="black")
    return image


def consignment_note_page() -> Image.Image:
    image, d = blank()
    d.rectangle((60, 50, 1180, 1500), outline="black", width=2)
    d.text((80, 62), "CMR", font=font(34, True), fill="black")
    d.text((300, 70), "INTERNATIONAL CONSIGNMENT NOTE", font=font(20, True), fill="black")
    d.text((300, 98), "LETTRE DE VOITURE INTERNATIONALE", font=font(16), fill="black")
    d.text((980, 70), "No. 4471902", font=font(18, True), fill="black")

    boxes = (
        (60, 140, 620, 300, "1  Sender / Expediteur",
         ("HELLAS CERAMICA S.A.", "Odos Marathonos 88", "19005 Attiki, GREECE")),
        (620, 140, 1180, 300, "16  Carrier / Transporteur",
         ("BALKAN LOGISTIK EOOD", "Bul. Cherni Vrah 41", "1407 Sofia, BULGARIA")),
        (60, 300, 620, 460, "2  Consignee / Destinataire",
         ("SEVAN TRADING LLC", "5 Komitas Ave", "0051 Yerevan, ARMENIA")),
        (620, 300, 1180, 460, "3  Place of delivery",
         ("Yerevan, ARMENIA", "", "")),
        (60, 460, 620, 600, "4  Place and date of taking over the goods",
         ("Attiki, GREECE", "05.06.2026", "")),
        (620, 460, 1180, 600, "5  Documents attached",
         ("Invoice HC-2026-1187", "Packing list", "Certificate of origin")),
    )
    for left, top, right, bottom, title, lines in boxes:
        d.rectangle((left, top, right, bottom), outline="black", width=1)
        d.text((left + 14, top + 10), title, font=font(15, True), fill="black")
        for index, line in enumerate(lines):
            d.text((left + 14, top + 40 + index * 26), line, font=font(17), fill="black")

    d.rectangle((60, 600, 1180, 900), outline="black", width=1)
    for x, title in ((74, "6  Marks and Nos"), (400, "7  Number of packages"),
                     (700, "8  Method of packing"), (960, "11  Gross weight kg")):
        d.text((x, 612), title, font=font(15, True), fill="black")
    for x, value in ((74, "SEVAN/YER"), (400, "158"), (700, "PALLETS"), (960, "49 320")):
        d.text((x, 646), value, font=font(18), fill="black")
    d.text((74, 700), "9  Nature of the goods", font=font(15, True), fill="black")
    d.text((74, 734), "CERAMIC TILES AND TILE ADHESIVE ON WOODEN PALLETS",
           font=font(18), fill="black")

    d.rectangle((60, 900, 1180, 1060), outline="black", width=1)
    d.text((74, 912), "25  Vehicle registration", font=font(15, True), fill="black")
    d.text((74, 946), "CB 4471 KM  /  CB 9903 EX", font=font(18), fill="black")
    d.text((620, 912), "21  Established in", font=font(15, True), fill="black")
    d.text((620, 946), "Attiki, on 05.06.2026", font=font(18), fill="black")

    d.rectangle((60, 1060, 1180, 1300), outline="black", width=1)
    for x, title in ((74, "22  Signature of the sender"),
                     (450, "23  Signature of the carrier"),
                     (830, "24  Goods received")):
        d.text((x, 1072), title, font=font(15, True), fill="black")
    return image


pages = [invoice_page(), consignment_note_page()]
pages[0].save(OUT, "PDF", save_all=True, append_images=pages[1:], resolution=150.0)
print(f"wrote {OUT} ({len(pages)} pages: invoice, consignment note)")
