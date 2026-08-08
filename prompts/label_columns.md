---
name: label_columns
version: 1
---

Below is the header row of a goods table taken from the sheet named `{{sheet_name}}` of a
commercial invoice supplied as a spreadsheet, together with the first few data rows from
directly beneath it. Say **which goods field each column holds**.

You are not asked for any value in this table, and you are not being shown enough of it to
give one. Label the columns; deterministic code reads the cells.

## How to read the payload

Both blocks are tab-separated and have exactly **{{column_count}}** columns, in order,
left to right. Column indexes are **0-based**: the leftmost column is 0.

An empty cell is written as the literal `(blank)`, in the header and in the sample rows
alike. A header of `(blank)` means the column has no heading at all — judge it from the
values underneath it. All {{column_count}} columns are shown even where every cell in one
of them is blank.

## How to decide

Use the header text **and** the sample values together. A header may be abbreviated,
written in another language, or missing entirely; the values under it are often the
stronger signal. Never decide by position — a goods table can put its columns in any
order, and the order below is not the order of the field list in this instruction.

Two pairs of columns are confused far more often than the rest. Read them carefully.

**Net weight against gross weight.** These are usually two *separate, adjacent* columns,
in **either** order, headed in any language:

- `net_weight` — `NET WEIGHT` · `NET WT` · `NET` · `NETTO` · `НЕТТО` · `Զուտ քաշ` ·
  `Զուտ կշիռ`
- `gross_weight` — `GROSS WEIGHT` · `GROSS WT` · `GROSS` · `BRUTTO` · `БРУТТО` ·
  `Համախառն քաշ` · `Բրուտտո`

Classify each column independently, by its **own** header text. Finding one of them does
**not** mean the other column is absent, and it does not mean the two columns hold the
same value. Two adjacent weight columns with different headers are two different fields.

**A customs code against the seller's own product code.** A column headed `Code`, `Kod`,
`SKU`, `Art. No`, `Article`, `Item No`, `Ref` or similar holds the seller's own product
code, which is not a customs code — label it `ignore`. Label it `printed_customs_code`
only when the header itself names a customs nomenclature: `HS`, `HS CODE`, `HS-CODE`,
`GTIP`, `TARIC`, `CTH`, `CN`, `ТН ВЭД`, `ԱՏԳ ԱԱ` or similar.

## When you cannot tell

`ignore` is the answer, and it is always available. Label a column `ignore` when it holds
something none of the fields below names — a running total, a note, a serial number, an
internal reference, a currency symbol, an empty column — and whenever the header text and
the values give you no support for a field. **Never guess a field for a column you cannot
place.** A column labelled `ignore` is simply not read; a column labelled wrongly puts a
figure on a customs declaration under the wrong heading.

## The fields

Exactly one of these labels per column:

| Label | The column holds |
|---|---|
| `printed_line_number` | The invoice's own row number: 1, 2, 3… |
| `description` | The goods name or description |
| `quantity` | How many, or how much, of this item |
| `unit` | The unit that quantity is in — `PCS`, `KG`, `M`, `հատ`, `շт` |
| `gross_weight` | Weight including packaging |
| `net_weight` | Weight of the goods alone |
| `weight_unit` | The unit the weights are in |
| `unit_price` | Price of one unit |
| `total_price` | Price for the whole row |
| `package_count` | How many packages, cartons, pallets or bags |
| `package_type` | What kind of package — `BAGS`, `CARTONS`, `PALLETS` |
| `origin_country` | Country of origin for this row |
| `trade_name` | Brand, mark or model |
| `units_per_package` | Items inside **one** package |
| `package_weight_kg` | Weight of **one** package |
| `dimensions` | The article's own size — `40X60 CM`, `0.33 L`, `A4` |
| `printed_customs_code` | A commodity code, under a customs heading only |
| `ignore` | None of the above |

## Output contract

One entry per column, covering **every** column index from 0 to {{column_count}} minus 1,
including the ones you label `ignore`. Each entry is the 0-based `column` index and one
`label` from the eighteen above, spelled exactly as it is written there. Return no other
key, and return no cell value anywhere.

HEADER ROW:
{{header_row}}

SAMPLE DATA ROWS:
{{sample_rows}}
