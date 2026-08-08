# evalkit

A small, self-contained verifier for **customs-declaration output**. It compares a
produced `ESADout_CU` declaration (XML) against a ground-truth declaration and
returns **numbers** — so "did this change help or hurt?" stops being an
eyeball judgement and becomes a scorecard you can gate CI on.

- **Stdlib-only core.** No dependencies to install; copy the `evalkit/` folder
  into any repo and it runs. Optional semantic / LLM-judge tiers plug in behind
  interfaces without the core taking a dependency.
- **Right metric per field type.** Numbers must be exact; codes are compared
  hierarchically; descriptions are scored for surface overlap *and* required
  attributes rather than demanded to match verbatim.

## Install / run

```bash
# from the evalkit/ folder — no install needed:
python -m evalkit pair path/to/output.xml path/to/ground_truth.xml
python -m evalkit corpus path/to/corpus/            # scores every case folder

# or install it:
pip install -e .            # then: evalkit pair a.xml b.xml
python -m unittest discover -s tests -v             # run the test suite
```

Exit code is non-zero when any case fails its thresholds, so `evalkit corpus …`
drops straight into CI.

## What it measures

| Field type | Fields | Metric |
|---|---|---|
| **Line set** | goods lines | optimal-ish 1:1 alignment → **precision / recall / F1** (invented vs. missed lines) |
| **Numeric** | quantity, net/gross weight, invoiced cost, package count | **exact** within tolerance; abs-error kept so rounding ≠ real error |
| **Code** | `GoodsTNVEDCode` (HS / ԱՏԳ) | **exact** + **hierarchical** agreement at 2/4/6/8/10 digits |
| **Enum** | unit, origin, currency | exact after normalisation |
| **Description** | `GoodsDescription` | **chrF** + token-F1 + **attribute rubric** (below); optional embedding cosine |

**Why descriptions aren't exact-matched.** A customs description has many valid
phrasings, so exact match is the wrong target. What makes one *correct* is: same
commodity meaning, the required attributes present (brand / trade name /
material), and nothing invented. `evalkit` measures those:

- **chrF** — character-n-gram F-score; robust for morphologically rich Armenian
  (word-BLEU over-penalises inflection). Deterministic, cheap → per-commit gate.
- **attribute rubric** — booleans: `brand_retained`, `trade_name_present`,
  `material_stated`, `no_hallucinated_brand`. These map to customs-correctness,
  not string cosmetics. With a case's `ground_truth.json` atoms the checks are
  **exact**; without them they degrade gracefully (expected brand detected from
  the reference) and never fail on nothing.
- **embedding cosine** *(optional)* — plug an `Embedder` into `evalkit.semantic`
  to catch valid paraphrases surface metrics miss.
- **LLM-as-judge** *(optional, your harness)* — for a periodic release gate that
  approximates the human read; keep it out of the per-commit path.

A **line passes** when every numeric field is exact, the code is exact, chrF
clears its floor, and no rubric check is violated. A **case passes** when line
F1 is 1.0 and every line passes. Thresholds live in `evalkit.score.Thresholds`.

### Source-grounding — don't punish external info

A field the pipeline gets wrong is only *its* failure if the information was in the
scanned documents. Brokers routinely add facts the invoice/CMR never carried — an
origin confirmed by phone, a net weight the invoice omitted — so a declaration can
hold values no scan could recover. Pass the after-scan text (`--source <file>`, or
`source_text=` in the library) and any ground-truth value **absent from the scan** is
**excused**: it no longer fails the case, and the scorecard reports `excused N
external`. With no source supplied, every field is attributable (the strict default).
This is why the tool is an *assistant* score, not a verdict — the broker still adds or
edits what the documents don't say.

## Corpus layout

One folder per case; filenames are configurable (`--mine`, `--gold`, `--atoms`):

```
corpus/
  case-001/
    declaration.xml       # produced output  ("mine")
    ground_truth.xml      # expected output  ("gold")
    ground_truth.json     # optional per-line atoms (see below)
  case-002/
    ...
```

`ground_truth.json` (optional) supplies the atoms that make the rubric exact,
one entry per gold goods line, in order:

```json
{ "goods": [
    { "brand": "MEILOSE", "trade_name": "MEILOSE GMC 3110", "material": "ՑԵԼՅՈՒԼՈԶ" },
    { "brand": null, "trade_name": null, "material": "ՊՈՂՊԱՏ" }
] }
```

## About the corpus data

The published corpus is **synthetic** — fictional companies, tax IDs, and
recombined product lines — built to exercise the pipeline's real cases
(multi-line shipments, repeated goods, mixed HS codes, missing fields,
foreign-language and scanned inputs). It contains no real party or shipment data.

## Library use

```python
from evalkit import parse_declaration, score_case

case = score_case(
    parse_declaration("output.xml"),
    parse_declaration("ground_truth.xml"),
    name="case-001",
)
print(case.as_dict())        # headline numbers
print(case.passed)           # CI gate
```

## Layout

```
evalkit/
  parse.py        ESADout_CU XML -> Declaration/Good
  align.py        line alignment -> precision/recall/F1
  codes.py        hierarchical HS-code agreement
  textmetrics.py  chrF, token-F1, normalized-exact
  rubric.py       attribute presence (brand/trade_name/material)
  semantic.py     optional embedding tier (bring your own model)
  score.py        roll up -> line/case/corpus scorecards + thresholds
  cli.py          `evalkit pair` / `evalkit corpus`
tests/            stdlib unittest, no pytest needed
```
