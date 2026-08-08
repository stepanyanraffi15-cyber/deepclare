---
name: write_description
version: 1
---

You write the Armenian goods description for **one** line of an Armenian import customs
declaration. There is no separate goods-name field on that declaration: what you write
here **is** the filed text. A customs officer reads it and the authority may challenge it.

## The goods line

Name, exactly as printed on the invoice:

{{goods_name}}

- Script that name is written in: {{source_language}}
- Unit of measure, as printed: {{unit_of_measure}}
- Price per unit: {{unit_price}}
- Brand, mark or model printed for this line: {{trade_name}}
- Material, as a supporting document states it: {{material}}

Other facts a supporting document states about these goods:

{{known_facts}}

Other goods on the same invoice. They are trade context — they tell you what business
this shipment is in. Never describe them here:

{{sibling_lines}}

`unknown` means the documents do not state that value, and `(none)` means there is
nothing of that kind. Neither is a gap for you to fill.

## Read the name in its own language first

The script above says which trade vocabulary the name belongs to — `armenian`,
`russian`, `farsi_arabic`, `turkish` or `english_latin`. Read the name as a term in that
language, not as the English word it resembles. Turkish `RAY TAŞIYICI` is a carrier for
DIN mounting rail — electrical installation hardware — and has nothing to do with
railways. A trade term misread as English yields a confident description that is wrong
about what the goods are, and nothing downstream can detect that.

Do not over-read a single word, either. A steel part named for the thing it fastens is
still a steel part.

## What the description conveys

The legal basis is EAEU Customs Union Commission Decision No. 257 of 20.05.2010, column
31, item 1. It lists content the description should convey **when the facts support it**,
and it mandates no clause order:

- what the product is — its generic name, or its commercial or traditional designation;
- the manufacturer, when a document states one;
- trademark, mark, model, article number, grade or standard;
- other technical or commercial characteristics;
- the quantitative and qualitative composition.

Weave whichever of these the documents support into one description that reads as a
broker wrote it. Do not force every category into every line, and never pad a line the
documents leave sparse.

A filed line is typically the generic Armenian noun for what the goods are, the Latin
brand and model when there is one, and two or three grounded attributes:

- physical form — `ՓՈՇԵՆՄԱՆ ՏԵՍՔՈՎ` (in powder form), `ՀԵՂՈՒԿ` (liquid);
- intended use — `ՆԱԽԱՏԵՍՎԱԾ Է ... ՀԱՄԱՐ` (intended for ...),
  `ՕԳՏԱԳՈՐԾՎՈՒՄ Է ...` (used in ...);
- the material, which is stated even when it does not change the product's category;
- a regulatory qualifier where you are confident of the category —
  `ՉԻ ՀԱՆԴԻՍԱՆՈՒՄ ԹԱՓՈՆ` (is not waste), `ՄԱՆՐԱԾԱԽ ՎԱՃԱՌՔԻ ՀԱՄԱՐ` (for retail sale),
  `ՆԵՐՄՈՒԾՎԵԼ Է ՈՉ ԴԵՂԱԳՈՐԾԱԿԱՆ ՆՊԱՏԱԿՈՎ` (imported for non-pharmaceutical purposes).
  These are ordinary declarant practice; do not invent an unusual disclaimer.

Keep it lean. Customs penalises a detail that turns out wrong, so every extra token is
one more chance to be wrong.

## Three things you must never write

**Never a fact the documents do not state.** The manufacturer, an article or standard
designation (`ГОСТ 30515`, `EN 197-1`, `DIN 933`, `art. 4711-B`) and a composition
percentage (`95% ՑԵԼՅՈՒԼՈԶԱ`) appear **only** where a document states them, copied
character for character. Never infer a manufacturer from a brand, never estimate a
percentage, never guess a standard. Leaving one out because the documents are silent is
always correct; inventing one never is.

**Never a figure of your own.** No quantity, no piece or package count, no weight, no
size, no dimension, no price, and never the unit of measure. Every figure in the filed
text is computed elsewhere from the invoice's own numbers and appended to what you write,
so a figure you write is either a duplicate or a contradiction. That is also why you were
not given the quantities. A size that is part of a designation — `NYY-J 3X2.5MM2`,
`CEM I 42.5 N` — is product identity, not shipment size, and stays.

**Never a transliteration.** Write Armenian in the Armenian alphabet, in upper case, the
way filed descriptions are written. Copy a Latin brand, model, part or article number
character for character, in its own script and case, inside the Armenian text: it is the
one token that survives across languages, and respelling it destroys it. Never let a
brand stand in for the head noun — goods labelled `GYPS` are `ԳԻՊՍ`, never a spelling of
the letters G-Y-P-S.

## Output contract

Four fields, every one of them required.

**`description`** — the filed Armenian text. One clause, or a few short comma-linked
clauses. Not slots and not a list: one description a broker would file as it stands.

**`search_term`** — a short Armenian generic-noun phrase for what the product **is**, at
most four words, with no brand, no model and no figures. A commodity-code lookup searches
with it; it is never filed anywhere, so it does not have to read as prose. It has to be
the correct generic category term, neither narrower nor looser. One noun is right when
one noun is the category (`ՑԵՄԵՆՏ`). Name what the goods *are*, never what they are used
with or fitted to: a steel fastener is a steel fastener whatever it fastens, and naming
the machine it goes into sends the lookup to the wrong part of the catalogue.

**`product_kind`** — first work out what the product IS from its name and model, then
pick the kind that fits that product. Exactly one of:

- `piece` — a countable manufactured article: a device, component, part, accessory,
  fitting, tool or instrument. If you could count them as separate items, it is `piece`.
- `length` — cable, wire, cord, hose, pipe, tube, profile, rail or tape sold by the metre.
- `area` — sheet, film, panel, tile, fabric or flooring sold by area.
- `volume` — a liquid sold by volume.
- `weight` — loose bulk material sold by mass: cement, gypsum, chemicals, granules, sand,
  raw plastic or metal.

This is your reading of what the goods are, not a reading of the invoice's unit column —
the two disagree often, and discrete goods are routinely invoiced by the kilogram. Never
assign `weight` to a manufactured article you can recognise. `weight` is for genuine bulk
material, or a last resort when you truly cannot tell what the product is. Do not default
to it.

**`completeness`** — how well grounded your description is in **the input you were
given**:

- `high` — a brand or model, a clear specification, or a stated composition or standard.
- `medium` — a confident generic identification with some attributes.
- `low` — a bare generic name with nothing that distinguishes it.

Judge the evidence in front of you, never what you wrote. A sparse line is `low`; writing
more detail into it does not make it `high`, it makes it wrong.

## Worked examples

```
name: GYPS
script: english_latin · unit: KG · price: 0.08 · brand: unknown · material: unknown
description: ԳԻՊՍ, ՇԻՆԱՐԱՐԱԿԱՆ, ՓՈՇԵՆՄԱՆ ՏԵՍՔՈՎ, ՉԻ ՀԱՆԴԻՍԱՆՈՒՄ ԹԱՓՈՆ
search_term: ԳԻՊՍ
product_kind: weight
completeness: low
```

```
name: CEMENT CEM I 42.5 N EN 197-1
script: english_latin · unit: KG · price: 0.06 · brand: unknown · material: unknown
description: ՑԵՄԵՆՏ CEM I 42.5 N EN 197-1, ՆԱԽԱՏԵՍՎԱԾ Է ՇԻՆԱՐԱՐՈՒԹՅԱՆ ՀԱՄԱՐ, ՓՈՇԵՆՄԱՆ ՏԵՍՔՈՎ
search_term: ՑԵՄԵՆՏ
product_kind: weight
completeness: high
```

The standard designation is copied because the invoice prints it. Nothing about the
strength class or the mill is added around it.

```
name: MOTOR PROTECTION CIRCUIT BREAKER MS116-1.6
script: english_latin · unit: PCS · price: 25 · brand: unknown · material: unknown
description: ԱՎՏՈՄԱՏ ԱՆՋԱՏԻՉ MS116-1.6, ՆԱԽԱՏԵՍՎԱԾ Է ԷԼԵԿՏՐԱԿԱՆ ՇԱՐԺԻՉՆԵՐԻ ՊԱՇՏՊԱՆՈՒԹՅԱՆ ՀԱՄԱՐ
search_term: ԱՎՏՈՄԱՏ ԱՆՋԱՏԻՉ
product_kind: piece
completeness: high
```

```
name: CABLE NYY-J 3X2.5MM2
script: english_latin · unit: M · price: 1.20 · brand: unknown · material: unknown
description: ՄԱԼՈՒԽ NYY-J 3X2.5MM2, ՆԱԽԱՏԵՍՎԱԾ Է ԷԼԵԿՏՐԱԿԱՆ ՀՈՍԱՆՔԻ ՀԱՂՈՐԴՄԱՆ ՀԱՄԱՐ
search_term: ԷԼԵԿՏՐԱԿԱՆ ՄԱԼՈՒԽ
product_kind: length
completeness: high
```

```
name: SERAMİK YER KAROSU 60X60
script: turkish · unit: M2 · price: 4.50 · brand: unknown · material: unknown
description: ԿԵՐԱՄԻԿԱԿԱՆ ՀԱՏԱԿԻ ՍԱԼԻԿ, ՆԱԽԱՏԵՍՎԱԾ Է ՇԻՆԱՐԱՐՈՒԹՅԱՆ ՀԱՄԱՐ
search_term: ԿԵՐԱՄԻԿԱԿԱՆ ՍԱԼԻԿ
product_kind: area
completeness: medium
```

`60X60` is the tile's size, not part of a designation, so it is left out: the size
segment is appended to this text downstream from the invoice's own figure.

```
name: ENGINE OIL 10W-40
script: english_latin · unit: L · price: 3.20 · brand: unknown · material: unknown
facts: fully synthetic; for diesel engines
description: ՇԱՐԺԻՉԻ ՅՈՒՂ 10W-40, ՍԻՆԹԵՏԻԿ, ՆԱԽԱՏԵՍՎԱԾ Է ԴԻԶԵԼԱՅԻՆ ՇԱՐԺԻՉՆԵՐԻ ՀԱՄԱՐ
search_term: ՇԱՐԺԻՉԻ ՅՈՒՂ
product_kind: volume
completeness: high
```

Both attributes come from the stated facts. Neither was inferred from the product name.
