---
name: read_invoice
version: 2
---

The {{page_count}} attached images are the pages, in order, of **one** commercial
invoice for an Armenian import customs declaration. Read them into the record described
below.

Everything you return is either copied off these pages or is null. Use nothing else: not
another document, not your knowledge of the product, the seller or the trade, not what a
value on this invoice "should" be.

## Transcribe, do not interpret

- **Verbatim.** Copy each value exactly as printed, in the language and script it is
  printed in. Never translate, never transliterate, never re-spell. Brand names, model
  numbers, part numbers and article codes are copied character for character; they are
  the only identifiers that survive across languages, and altering one destroys it.
- **Unformatted.** Do not reformat a date, do not convert a unit, do not rescale or round
  a number, do not expand an abbreviation, do not tidy up spacing or case. A date printed
  `12.03.2026` is returned as `12.03.2026`. Later stages normalise values and record what
  they changed; they can only do that if you hand them what was actually printed.
- **Never invented.** If a value is not printed, return null for it. Null means "not
  printed on this invoice", and later stages depend on that meaning. Do not infer a value
  from another field, do not compute one, do not complete a partial code, do not carry a
  value from one goods row onto another because the rows look similar, and do not fill a
  gap from a page header or a previous page unless that text plainly applies to the row.
- **Unsure is null.** An illegible or ambiguous value is null, not a best reading.

## Which rows are goods

A goods line is a row for a physical item being imported.

Rows charging for **freight, transport, delivery, shipping, carriage, logistics,
handling, storage, insurance, customs clearance, packing service** — or for any other
service rather than for an item — are **not goods**. This holds even when such a row sits
inside the goods table, is numbered like a goods row, and is included in the invoice's own
printed TOTAL.

Such a row must:

- never appear as a goods line, and
- never be counted inside the goods total.

Return those rows instead in `service_charges`, as printed, so that the difference between
the invoice's printed total and the declared goods value is auditable rather than silent.

## Order is identity

Return the goods lines in the order they are printed, top to bottom, first page first.
Never reorder, group, sort, split or merge them. A broker reconciles a filed declaration
line back to its invoice row by position, so the sequence is part of the data. Where the
invoice numbers its own rows, capture that printed number as well.

## Say where you read it, and how sure you are

Every value carries two things nobody can recover from it afterwards:

- `page` — the 1-based number of the attached image the value is printed on. The first
  attached image is page 1, whatever number is printed on the paper. If a value appears on
  more than one page, give the page you read it from.
- `confidence` — your honest probability, from 0 to 1, that what you typed is
  character-for-character what is printed. Grade **legibility only**: how clearly you
  could see it. Crisp printed text is near 1; faint, skewed, overlapped, handwritten or
  partly cut-off text is lower. Never grade whether the value looks plausible, sensible or
  consistent with the rest of the invoice — that is not what this number is for, and a
  correctly-read oddity must not be marked down.

Header values each carry their own page and confidence, because an invoice scatters them:
the seller block may be printed on page 1 and the total on page 4. A goods row carries one
page and one confidence for the whole row, because it is printed as one row and read as
one.

## Output contract

One invoice record. Every field is optional and defaults to null except each goods line's
`description`; a missing field never fails this read, because what is required is decided
downstream.

**Header.** Each of these is either null or an object carrying the value together with its
own `page` and `confidence`. The value key is `text` everywhere except `total_amount`,
where it is `number`, and the parties, which carry their three lines directly.

- `invoice_number` — the invoice's own number, as printed.
- `invoice_date` — as printed, in the invoice's own format.
- `currency` — the invoice currency, as printed (e.g. `USD`, `EUR`).
- `incoterms_code` — the delivery-terms code, as printed (e.g. `FCA`, `CIP`).
- `incoterms_place` — the place named after that code.
- `origin_country` — a country of origin the invoice states for the whole shipment.
- `seller` and `buyer` — each an object with `name`, `address`, `tax_code`, each as
  printed and each null when not printed, plus the one `page` and `confidence` of the
  printed block they were read from.
- `total_amount` — the printed total **for goods only**, in `number`. Where the invoice
  prints a goods subtotal that excludes service charges, copy that figure. Where the only
  printed total includes service charges, return null: return the service rows below
  instead and let a later step do the arithmetic. Never adjust, sum or reconcile a total
  yourself.
- `service_charges` — one entry per non-goods row described above, each with
  `description` and `amount` exactly as printed, plus its `page` and `confidence`. Empty
  list when the invoice has none.
- `goods_lines` — the goods lines, in printed order.

**Each goods line.** The row's own `page` and `confidence` cover every field on it; the
fields themselves are plain values.

- `printed_line_number` — the row number the invoice itself prints for this row; null
  when the invoice does not number its rows.
- `description` — the goods name or description as printed. **Required**: this is the one
  field a line cannot be returned without. Where the row's text is split across a name
  column and a specification column, return what is printed, unaltered.
- `quantity` — the printed quantity for this row.
- `unit` — the quantity's unit as printed (e.g. `PCS`, `KG`, `TONNE`, `M`).
- `gross_weight`, `net_weight` — the per-row weights. These are two different figures:
  read each from its own column, and never copy one into the other because only one is
  printed.
- `weight_unit` — the unit those weights are printed in.
- `unit_price`, `total_price` — as printed.
- `package_count` — the number of packages for this row.
- `package_type` — the kind of package, as printed (e.g. `BAGS`, `PALLETS`).
- `origin_country` — a country of origin printed for this row specifically.
- `trade_name` — the brand, mark or model for this row, copied verbatim, whether it is
  printed in its own column or inside the description. Null when none is printed; never
  guessed from the product.
- `units_per_package` — the number of items in **one** package, only when it is printed:
  `12 PCS/CTN` → 12, `KUTU 1000 AD` → 1000, `3900ML*4` → 4. Never derived by dividing.
- `package_weight_kg` — the weight of **one** package in kilograms, only when a packing
  column prints it: `25KG BAG` → 25.
- `dimensions` — the item's own size, as printed: `135*115 MM`, `40X60 CM`, `0.33L`,
  `A4`. This is the size of the article itself — not a shipment total, not a cubic
  volume, not a weight.
- `printed_customs_code` — a commodity code printed for this row, exactly as printed,
  digits and all, when a column names one (`HS`, `HS CODE`, `GTIP`, `TARIC`, `CTH`,
  `ТН ВЭД` or similar). A column headed `Code`, `SKU`, `Art. No` or `Item No` is the
  seller's own product code, not a customs code — leave this null. Never infer a code and
  never pad a short one out.
