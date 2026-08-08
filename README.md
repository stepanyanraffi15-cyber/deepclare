# DeepClare

Produces **import customs declaration drafts** for the EAEU / Republic of Armenia.

Documents in — a commercial invoice, usually a CMR consignment note, sometimes a supplier
catalogue — and out comes the declaration XML the national customs portal accepts, plus a
review report naming everything a human should confirm.

**It never files.** The output is a reviewable draft. Every value the system inferred
rather than read carries a review item, because the governing rule of the whole product
is that *wrong is worse than missing*: on a legal document a wrong value is a
consequential error, while a missing value is work left for a human. That single
asymmetry is why the classifier abstains rather than guessing, why a duty preference is
never claimed automatically, and why arithmetic that cannot be grounded is left out
rather than fabricated.

---

## What it does

```
invoice (+ consignment note, catalogues)
      │
      ├─ read every page as an image, verbatim and untranslated
      ├─ write a legally grounded Armenian description per goods line
      ├─ assign a 10-digit EAEU commodity code, or abstain with a reason
      ├─ resolve units, weights, packaging, parties, transport
      │
      └─→  declaration XML  +  review report
```

Vision is the primary reading path, not a fallback. In the measured corpus that rule
*inverts* the intuitive one: the sharpest 300 DPI scan carried the worst embedded text
layer, so a router preferring embedded text takes the corrupt path on the densest
document.

---

## Requirements

- **Python 3.12+** (developed on 3.13)
- **A Gemini API key** — used for vision reading, description writing, classification and
  embeddings
- **~1 GB free disk** for the reference data

---

## Install

```bash
git clone <this repo> && cd deepclare
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/pip install -e .
cp .env.example .env          # then fill in GOOGLE_API_KEY
```

Every variable in `.env.example` is required. Configuration is read once at startup, and
a missing or malformed value fails immediately naming itself — never halfway through a
run.

---

## Reference data — read this before the first run

**A clone does not contain the reference data**, and this is deliberate rather than an
oversight. The commodity nomenclature and its vector index are large derived artifacts:
the vector collection alone is 113 MB, which is over GitHub's per-file limit. `data/` is
gitignored in full.

Two ways to get there.

### If you were given a `data/` directory

Put it in place and you are done:

```
data/
  qdrant_exim/                       # the vector collection, 113 MB
    collection/atg_aa_codes/storage.sqlite
  reference/nomenclature_exim/       # names, paths, units, chapter notes
    entries.jsonl  headings.json  notes.json  meta.json
```

### If you are starting from nothing

```bash
# 1. Acquire the nomenclature and build the tree (~4 minutes, no API cost)
./.venv/bin/python -m deepclare build-reference --reacquire

# 2. Build the vector collection (14,332 embedding calls — this one costs money)
./.venv/bin/python -m deepclare build-index
```

Step 1 enumerates the authority's node ids. It does **not** use the paged listing
endpoint: measured against the live service, that endpoint reports 10,000 rows against an
id space past 21,000, and anything built on it silently misses most of the tree. Any id
that cannot be resolved fails the whole acquisition rather than returning a partial tree.

Step 2 embeds each entry as an English broad-to-specific noun phrase —
`<chapter> — <heading> — <leaf>`. **The query side must be phrased the same way**, and it
is: a query in that form scores 0.84 against the correct leaf where a plain English
phrase for the same goods scores 0.65. Change one side and you must rebuild the other.

Embeddings are pinned to `gemini-embedding-001` at **768 dimensions**. That is locked, not
chosen — a different model or width does not align with an existing collection.

---

## Run

```bash
./.venv/bin/python -m deepclare run path/to/invoice.pdf \
    --consignment-note path/to/cmr.pdf \
    --out ./out
```

Writes the declaration XML and the review report to `--out`.

---

## Verifying it works

Two layers, deliberately separated.

**Automated checks — no network, no cost:**

```bash
./.venv/bin/python -m pytest -q
```

These never call a provider. Where a model is involved they intercept at the HTTP layer
and assert on the request that *would* have been sent — the rendered prompt, the decoding
settings, the output schema — which catches a wrong prompt without paying for one.

**Live checks against the real API — these cost tokens:**

```bash
./.venv/bin/python tests/check_reading_end_to_end.py        # vision extraction
./.venv/bin/python tests/check_description_end_to_end.py    # Armenian descriptions
./.venv/bin/python tests/check_classification_end_to_end.py # commodity codes
```

They are named `check_*` rather than `test_*` so pytest never collects them and they
cannot fire by accident in CI.

---

## Scoring against the corpus

`evalkit/` holds 71 synthetic cases — input documents plus the expected declaration.
Fully synthetic: fictional companies and tax IDs, no real shipment data.

```bash
python -m evalkit corpus evalkit/corpus/
```

It scores commodity codes hierarchically at 2/4/6/8/10 digits rather than pass-fail,
numerics exactly, and descriptions by character-n-gram overlap plus an attribute rubric —
because a customs description has many valid phrasings and exact match is the wrong
target.

One caveat worth stating before quoting any number from it: the corpus labels are the
**generator's** classifications, not a broker's. Scoring against it measures agreement
with the generator, which is not the same as customs correctness.

---

## Layout

| Path | What lives there |
|---|---|
| `src/deepclare/domain/` | Concepts, provenance, confidence, review items. Depends on nothing. |
| `src/deepclare/intake/` | Submission validation, page rasterizing and grouping |
| `src/deepclare/reading/` | Documents to verbatim records, by vision |
| `src/deepclare/description/` | The Armenian goods description |
| `src/deepclare/classification/` | Commodity code assignment — the one real graph |
| `src/deepclare/assembly/` | Every cross-field rule: units, weights, arithmetic |
| `src/deepclare/filing/` | **The only module that knows the XML format**, both directions |
| `src/deepclare/review/` | The human-facing report |
| `src/deepclare/reference/` | Nomenclature acquisition, tree, index, queries |
| `prompts/` | One file per model call. No prompt strings live in Python. |
| `docs/handoff/` | The specification this is built from |
| `evalkit/` | Scoring harness and the 71-case corpus |

Module boundaries are load-bearing — see `CLAUDE.md`. Exactly one module knows the filed
document's element names and ordering; everything upstream decides *what a value should
be* and never *how it is written*.

---

## Which model runs what

| Stage | Model |
|---|---|
| Page classification, spreadsheet header, column labelling | `gemini-3.5-flash-lite` |
| Vision document reading, evidence, descriptions, chapter/heading narrowing | `gemini-3.6-flash` |
| Final code pick and verification | `gemini-2.5-pro` |
| Embeddings | `gemini-embedding-001` at 768d — **locked** |

All pinned at temperature 0. Every model id is configuration, never a constant, so a run
can record what actually answered it.
