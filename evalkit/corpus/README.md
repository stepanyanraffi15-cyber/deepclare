# Synthetic customs corpus

A synthetic benchmark for the customs-declaration pipeline: for each case, the
**input documents** a broker would receive, and the **expected declaration** the
pipeline should produce. Score outputs against it with [`evalkit`](../README.md).

**Fully synthetic** — fictional companies, tax IDs, invoice numbers, and
recombined product baskets with jittered quantities/prices. No real party or
shipment data. The invoice/CMR PDFs are image-only (scan-degraded), matching real
scanned inputs.

## Case layout

Cases are grouped by product family (one folder per seed):

```
<family>/case-NNN/
  invoice.pdf        # commercial invoice — Product column (+ Model column when distinct)
  invoice.xlsx       # the same invoice as a workbook (for Excel-invoice flows)
  cmr.pdf            # CMR consignment note, with stamps/signatures over boxes 22–24
  ground_truth.xml   # expected ESADout_CU declaration — the portal-importable target output
  ground_truth.json  # per-line atoms {brand, trade_name, material} — makes the rubric exact
  ir.json            # the case spec all artifacts were rendered from (human-readable)
```

The three input artifacts and the ground truth are projections of one spec
(`ir.json`), so invoice total = XML sum = CMR gross weight by construction.

## Scoring

Run your pipeline on each case's `invoice.pdf`/`cmr.pdf`, save its output as
`<family>/case-NNN/declaration.xml`, then:

```bash
python -m evalkit corpus corpus/        # recurses every family; F1, numeric, HS, chrF, rubric
```

Non-zero exit if any case misses its thresholds.

## Coverage

**387 cases.**

| Family | Goods | Style |
|---|---|---|
| **`oneToOne`** | **71 real declarations (≥4 goods)** | **each real filing → one case: its true basket + real quantities (±10% jitter), fake parties, translated invoice names — the most realistic** |
| `new_folder2` | construction chemicals | generic + model (two-column) |
| `new_folder3` | household detergents | brand + number |
| `new_folder6` | electrical gear | model /BRAND/ |
| `big_invoice` | stationery (6 sub-invoice families) | unbranded, names off the xlsx |
| `big_invoice_showers` | shower drains | unbranded, names off the scanned PDF |
| `history` | ~1,900 goods across 55 HS-chapter families | recombined from the ground-truth history DB (synthetic baskets) |

**`oneToOne`** is the primary, most realistic family — no recombination, so every case
is a coherent real shipment (a furniture importer, a fiber-optic supplier, …) with its
actual goods and quantities; only the parties are invented and the descriptions
translated to English invoice text. The others span 2–20 goods lines, single/multi-origin
baskets, duplicate codes, unbranded goods, KG and pieces units, and 41 HS chapters.
