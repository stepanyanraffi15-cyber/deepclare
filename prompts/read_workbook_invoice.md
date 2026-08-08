---
name: read_workbook_invoice
version: 1
---

The text below is **one** commercial invoice for an Armenian import customs declaration,
supplied as a spreadsheet. It is a deterministic, verbatim rendering of that workbook's
own cells — not a summary, not an extract, and not anything a person wrote for you. Read
it as the source document.

Everything you return is either copied out of this text or is null. Use nothing else: not
another document, not your knowledge of the product, the seller or the trade, not what a
value on this invoice "should" be.

## How the workbook has been rendered

- One section per non-empty sheet, in workbook order, each opening with a line reading
  `=== Sheet: <name> ===`.
- One line per non-empty row; rows with nothing in them are omitted.
- Cells within a row are separated by tabs. **A blank cell between two filled cells is
  rendered as an empty field, so column position is preserved** — the third value on a
  line is in the third column, and it sits under the third value of the header line above
  it. Blank cells at the end of a row are dropped, so lines differ in length.
- A cell holding a date is rendered `YYYY-MM-DD`. A spreadsheet stores a date as a number
  and a display setting, so there is no printed form of it to preserve.

## Transcribe, do not interpret

- **Verbatim.** Copy each value exactly as it appears, in the language and script it
  appears in. Never translate, never transliterate, never re-spell. Brand names, model
  numbers, part numbers and article codes are copied character for character; they are the
  only identifiers that survive across languages, and altering one destroys it.
- **Unformatted.** Do not reformat a date, do not convert a unit, do not rescale or round
  a number, do not expand an abbreviation, do not tidy up spacing or case.
- **Never invented.** If a value is not in the text, return null for it. Null means "not
  stated in this workbook", and later stages depend on that meaning. Do not infer a value
  from another field, do not compute one, do not complete a partial code, and do not carry
  a value from one row onto another because the rows look similar.
- **Unsure is null.** An ambiguous value is null, not a best reading.

## Columns are not in a fixed place

Column headers vary from invoice to invoice. They may be abbreviated, written in another
language, or missing altogether. Work out which column holds which field from its header
text **and** from the values under it — never from a fixed position, and never from the
order the fields are listed in below.

## Which rows are goods

A goods line is a row for a physical item being imported.

Rows charging for **freight, transport, delivery, shipping, carriage, logistics,
handling, storage, insurance, customs clearance, packing service** — or for any other
service rather than for an item — are **not goods**. This holds even when such a row sits
inside the goods table, is numbered like a goods row, and is included in the workbook's
own printed TOTAL.

Such a row must never appear as a goods line and never be counted inside the goods total.
Return it in `service_charges` instead, as written, so that the difference between the
invoice's own total and the declared goods value is auditable rather than silent.

A row that totals or subtotals other rows is not a goods line either, and is not a service
charge. Leave it out of both.

## Order is identity

Return the goods lines in the order they appear, top to bottom, first sheet first. Never
reorder, group, sort, split or merge them. A broker reconciles a filed declaration line
back to its invoice row by position, so the sequence is part of the data. Where the
workbook numbers its own rows, capture that printed number as well.

## How sure you are

Every value carries a `confidence`: your honest probability, from 0 to 1, that this is the
value the workbook states for that field.

The text you are reading is exact, so copying is not what you are grading. What you are
grading is **identification** — that this cell, and not a neighbouring one, is the
invoice number; that this figure is the goods total and not a subtotal or a tax line; that
this block of lines is the seller and not the buyer. A value sitting under an unambiguous
label is near 1. A value you chose between two plausible cells, or read from an unlabelled
block, is lower. Never grade whether a value looks sensible: a correctly-read oddity is
not marked down.

## Output contract

One invoice record. Every field is optional and defaults to null except each goods line's
`description`; a missing field never fails this read, because what is required is decided
downstream.

**Header.** Each of these is either null or an object carrying the value together with its
own `confidence`. The value key is `text` everywhere except `total_amount`, where it is
`number`, and the parties, which carry their three lines directly.

- `invoice_number` — the invoice's own number, as written.
- `invoice_date` — as written.
- `currency` — the invoice currency (e.g. `USD`, `EUR`).
- `incoterms_code` — the delivery-terms code (e.g. `FCA`, `CIP`).
- `incoterms_place` — the place named after that code.
- `origin_country` — a country of origin stated for the whole shipment.
- `seller` and `buyer` — each an object with `name`, `address`, `tax_code`, each as
  written and each null when not stated, plus one `confidence` for the block.
- `total_amount` — the total **for goods only**, in `number`. Where the workbook states a
  goods subtotal that excludes service charges, copy that figure. Where the only total
  includes service charges, return null: return the service rows below instead and let a
  later step do the arithmetic. Never adjust, sum or reconcile a total yourself.
- `service_charges` — one entry per non-goods row described above, each with
  `description` and `amount` as written, plus its `confidence`. Empty list when there are
  none.
- `goods_lines` — the goods lines, in the order they appear.

**Each goods line.** One `confidence` covers the whole row; the fields themselves are
plain values.

- `printed_line_number` — the row number the workbook itself gives this row; null when
  rows are not numbered.
- `description` — the goods name or description as written. **Required**: this is the one
  field a line cannot be returned without. Where a row's text is split across a name
  column and a specification column, return what is written, unaltered.
- `quantity` — the quantity for this row.
- `unit` — the quantity's unit as written (e.g. `PCS`, `KG`, `TONNE`, `M`, `հատ`).
- `gross_weight`, `net_weight` — the per-row weights. These are two different figures in
  two different columns. Read each from its own column, and never copy one into the other
  because only one of them is stated.
- `weight_unit` — the unit those weights are stated in.
- `unit_price`, `total_price` — as written.
- `package_count` — the number of packages for this row.
- `package_type` — the kind of package (e.g. `BAGS`, `PALLETS`).
- `origin_country` — a country of origin stated for this row specifically.
- `trade_name` — the brand, mark or model for this row, copied verbatim, whether it sits
  in its own column or inside the description. Null when none is given; never guessed
  from the product.
- `units_per_package` — the number of items in **one** package, only when it is stated:
  `12 PCS/CTN` → 12, `KUTU 1000 AD` → 1000. Never derived by dividing.
- `package_weight_kg` — the weight of **one** package in kilograms, only when a packing
  column states it: `25KG BAG` → 25.
- `dimensions` — the item's own size, as written: `135*115 MM`, `40X60 CM`, `0.33L`, `A4`.
  This is the size of the article itself — not a shipment total, not a cubic volume, not a
  weight.
- `printed_customs_code` — a commodity code given for this row, exactly as written, digits
  and all, when a column names one (`HS`, `HS CODE`, `GTIP`, `TARIC`, `CTH`, `ТН ВЭД` or
  similar). A column headed `Code`, `SKU`, `Art. No` or `Item No` is the seller's own
  product code, not a customs code — leave this null. Never infer a code and never pad a
  short one out.

The workbook, rendered, follows. It has {{sheet_count}} sheet(s).

{{workbook_text}}
