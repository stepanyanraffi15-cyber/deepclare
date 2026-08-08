---
name: read_consignment_note
version: 2
---

The {{page_count}} attached images are the pages, in order, of **one** CMR international
road consignment note accompanying a shipment into Armenia. Read them into the record
described below. The numbers in brackets are the CMR form's own box numbers; use them to
find a field, and read whatever is actually printed there even if this form is laid out
differently.

Everything you return is either copied off these pages or is null. Use nothing else: not
the invoice, not another page, not your knowledge of the carrier or the route, not what a
value "should" be for a shipment like this.

## Transcribe, do not interpret

- **Verbatim.** Copy each value exactly as printed, in the language and script it is
  printed in. Never translate, never transliterate, never re-spell. A carrier's name, a
  place name and a registration plate are copied character for character.
- **Unformatted.** Do not reformat a date, do not convert a weight, do not rescale or
  round a number, do not expand an abbreviation, do not tidy up spacing or case.
- **Never invented.** If a box is empty or its content is not printed, return null. Null
  means "not on this note", and later stages depend on that meaning. Do not infer a value
  from another box, do not compute one, and do not complete a partial one.
- **Unsure is null.** These forms are commonly handwritten over a carbon copy and
  stamped across. An illegible or ambiguous value is null, not a best reading.

## What this note is not

It is not an invoice, and nothing on it becomes a goods line. Box 6–9 describe the
shipment as a whole: one goods wording, one package count, one package kind, one gross
weight. Return them as the single shipment-level values they are. Never split them per
item, never distribute a weight, and never pair a package count with a goods description
to make rows.

The package count in box 7 counts the packaging level the carrier handles — very often
pallets, where the invoice counted cartons. Copy the figure and the kind as printed and
leave the two counts alone; reconciling them is not this read's job.

## Vehicle plates

Box 25 carries the registration of each vehicle in the combination. Return **one entry
per distinct vehicle** — a truck and its trailer are two vehicles and two entries.

One plate is very often printed twice in two forms — spaced and unspaced, or restated
after a slash. That is one vehicle, not two, and it gets **one entry carrying one of the
two forms**: `12 Ab 345/12A345` gives the single entry `12 Ab 345`. Return the form that
is printed first and drop the restatement; an entry containing both forms is wrong in the
same way two entries would be.

Copy each plate as printed otherwise — do not restyle it, do not pad or strip it, never
put two genuinely different plates in one entry, and never invent a plate that is not
there.

## Say where you read it, and how sure you are

Every value carries two things nobody can recover from it afterwards:

- `page` — the 1-based number of the attached image the value is printed on. The first
  attached image is page 1, whatever number is printed on the paper.
- `confidence` — your honest probability, from 0 to 1, that what you typed is
  character-for-character what is printed. Grade **legibility only**: how clearly you
  could see it. Crisp printed text is near 1; handwriting, carbon copy, a stamp across
  the text, or a faint or cut-off box is lower. Never grade whether the value looks
  plausible or consistent with the rest of the note.

Each value carries its own page and confidence, and a party block carries one of each for
its three lines, because that block is read as one.

## Output contract

One consignment-note record. Every field is optional and defaults to null. A missing
field never fails this read; what is required is decided downstream.

Each field below is either null or an object carrying the value together with its own
`page` and `confidence`. The value key is `text`, except on `package_count` and
`gross_weight` where it is `number`, and on the parties, which carry their three lines
directly.

- `cmr_number` — the note's own number, as printed.
- `sender` [1], `consignee` [2], `carrier` — each an object with `name`, `address`,
  `tax_code`, each as printed and each null when not printed, plus the one `page` and
  `confidence` of the printed block.
- `place_of_loading` [4] — the place the goods were taken over, as printed.
- `place_of_delivery` [3] — as printed.
- `country_of_dispatch` — the country the goods were dispatched from, when the note
  states one separately from the place of loading.
- `date` — the note's date, as printed, in the note's own format.
- `vehicle_plates` [25] — a list, one entry per distinct vehicle, each with `text`,
  `page` and `confidence`. Empty list when no plate is printed.
- `goods_description` [6] — the note's own wording for the goods, as printed, in one
  entry however many lines it runs to.
- `package_count` [7] — the number of packages, in `number`.
- `package_type` [8] — the kind of package, as printed (e.g. `PALLETS`, `BIGBAGS`).
- `gross_weight` [11] — the shipment's gross weight, in `number`.
- `weight_unit` — the unit that weight is printed in.
- `attached_documents` [5] — a list, one entry per document the note says is attached,
  each as printed with its `page` and `confidence`. Empty list when none is listed.
