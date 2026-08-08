# Task prompt — DeepClare, next build step

Copy everything below the line into a fresh agent session.

---

You are continuing the DeepClare build. Work in `/Users/raffi/workspace/deepclare` on
branch `main`. Read `CLAUDE.md` first — its hard constraints are not style
preferences, and breaking one is a defect.

## Read before writing anything

The specification is `docs/handoff/`, twelve numbered files. It is authoritative. Read
the relevant file rather than guessing at a rule you can look up. For this task that
means, at minimum:

- **`02-AI-ARCHITECTURE.md` §4** — the classifier layer stack and the Code Assignment
  graph, node by node, with every branch condition. §6.2 gives the exact edges. §7.1
  gives the failure behaviour per node.
- **`11-REFERENCE-DATA.md` §3.2 and §3.3** — the retrieval traversal and the rules for
  code-shaped inputs printed on documents.
- **`10-MODULE-DECOMPOSITION.md` §3 M9 and M4** — the boundaries. What classification
  must not know about is load-bearing.
- **`06-PROMPTING-STRATEGY.md`** — for every model call you add. It is 2029 lines; read
  it in two passes with offset/limit so you cover all of it.
- **`03-FIELD-SEMANTICS.md` §3.2** — what a classification result must carry.
- **`07-FAILURE-MODES.md`** — the recorded failures each defence exists for.

Also read `PROGRESS.md` for what has been built and decided so far, and why.

## What already exists and works

- **The reference layer is built and verified.** The Qdrant collection `atg_aa_codes`
  (14,332 points, 768-dim cosine) now carries, on every point:
  `code, level, p2, p4, p6, p8, name_en, name_hy, name_ru, path_en, path_hy, path_ru,
  supplementary_unit`. The `path_*` fields are the full taxonomic path including the
  intermediate group levels — this matters, because 29.5% of leaves are named only
  "other" and are meaningless without their ancestry.
- `data/reference/nomenclature_exim/entries.jsonl` — the same 14,332 codes with their
  ancestry as structured data, plus `headings.json` (1,228 titles, none blank).
- `src/deepclare/reference/` — acquisition, tree building, enrichment.
- `src/deepclare/models.py` — the generative client. Tiers are configuration:
  `ModelTier.CHEAP / STANDARD / STRONG`. Construct with `GenerativeModel(settings)`.
- `src/deepclare/prompting.py` — the prompt loader. Prompts live in `prompts/`.
- `src/deepclare/intake/` and `src/deepclare/reading/` — M5 and M6, working end to end
  against a real model (see `tests/check_reading_end_to_end.py`).
- `src/deepclare/domain/` — provenance, three-part confidence, transform chain, review
  items, and the extracted document records.

Verify these claims yourself before building on them; do not take this summary on trust.

## Your task, in order

### Part 1 — close the two open gaps in step 2

**1a. Implement the page-type classifier.** `prompts/classify_page_type.md` is written
and orphaned: nothing renders it, and its `{{page_manifest}}` placeholder has no
producer. `src/deepclare/intake/classifier.py` defines the `PageTypeClassifier` port and
the `PageVerdict` type. Write the implementation that calls the model and satisfies the
port, and place it where it belongs — **not** in `intake`, which must not know which
model reads a page. Note the invariant already recorded in `classifier.py`: `PageVerdict`
is the port's type and must never be bound as a provider output schema, because its field
descriptions become prompt text. Define a prose-free answer shape and map it, the way
`reading/schemas.py` does.

**1b. Carry page-less documents forward.** After a fix earlier in the build, a routed XML
or workbook produces no pages, so grouping never sees it and it vanishes from the output.
`RoutedSubmission` still holds it and nothing connects the two. Decide where that seam
belongs and make it explicit.

Do **not** build the spreadsheet reading path in this task. It raises
`NotImplementedError` naming itself, which is correct until someone builds it.

### Part 2 — build M9 Classification

One commodity code per goods line, or an abstention with a stated reason.

**The layer stack**, outermost first. A line descends until one layer decides, and the
decision returns outward through every layer it passed:

- **L1 Existence gate** — no code leaves this module that is absent from the current
  nomenclature, whatever produced it. Accepts the 10-digit leaf form and the filed
  11-digit national form. Rejects wrong length, letters, and all-zeros fillers. On
  rejection it strips **only the code**, clears confidence and the supplementary unit,
  rewrites the rationale, and raises the review item. It does its work on the *return*.
- **L4 Vendor-catalogue code** — a code printed in a supplied catalogue, validated
  against the nomenclature, short-circuits at moderate confidence and is **always**
  flagged for review. A code shorter than 10 digits never short-circuits.
- **The Code Assignment graph** underneath.

**There is no L2 and no L3.** Customer-history reuse was removed from this product
deliberately. Do not add any code that searches a customer's prior filings. The
specification describes those layers; they are out of scope here and `CLAUDE.md` says so.

**The Code Assignment graph** — one traversal per goods line, and the only part of this
system that is genuinely a graph rather than a line. Build it as a declared graph:
nodes take state and return state, edges and conditions live in the graph definition
where they can be read in one place, and no node calls the next. It must be inspectable —
printable without running, and traceable node by node afterwards.

Nodes: printed-code fast path · chapter shortlist · heading pick + English query write
(one call does both) · optional subheading preference · candidate retrieval · final pick
· optional veto-only verification · dead-end reset. Exact behaviour, reads and writes per
node, and every branch condition are in `02-AI-ARCHITECTURE.md` §4.3 and §6.2.

Rules that must survive, each for a recorded reason:

- **Two chapters, not one.** A wrong chapter filters the correct code out of retrieval
  entirely and is unrecoverable.
- **Subheading preference is a soft annotation, never a retrieval filter.** Hard
  narrowing losses are unrecoverable.
- **No similarity threshold on retrieval.** Every retrieved candidate is shown to the
  model. Dedupe by code keeping maximum similarity, sort descending.
- **The final pick sees the full taxonomic path, not bare codes** — use the `path_*`
  payload. It must be able to see that *none* of the candidates fits and abstain.
- **The retry is guarded structurally, not by a counter**: the reset clears the very slot
  the entry branch tests, so a second pass always terminates.
- **A code the model invents must not be silently replaced** by the top candidate at zero
  confidence. The specification records that as a shipped silent-failure path and says
  not to reproduce it. Abstain instead.
- **Ship the confidence review gate enabled.** The specification records it as present
  but disabled, which makes two of its files disagree; enabling it makes them agree.

**The query side of the embedding is a contract.** The index was built from an English,
broad-to-specific, em-dash-separated noun phrase: `<chapter> — <heading> — <leaf>`. The
prompt that writes the search query must mirror that structure. Measured: a query in that
form scored 0.84 against the correct leaf where a plain English phrase for the same goods
scored 0.65. Change one side and you must change the other.

Embeddings must use `models/gemini-embedding-001` at **768 dimensions**. This is locked,
not chosen: the collection was built with it, and a different model or width does not
align with those vectors.

## How to work

- Follow `.claude/skills/architecture-review`: if you are about to make an architectural
  decision — pipeline shape, module boundary, a run-time data source, a model assignment,
  anything touching the XML contract, or resolving a specification `[UNKNOWN]` — write it
  down and **ask before implementing it**.
- Commit after every working piece, with a clear message. Never batch the session into
  one commit.
- Append to `PROGRESS.md` as you go: what works and how you verified it, what is partial,
  every decision you took where the specification was silent, where you are least
  confident, and anything in the specification that turned out wrong or contradictory
  once you built against it.
- Run `.venv/bin/python -m pytest -q` before each commit. It currently passes 125 tests.

## Definition of done

Classification runs on a real goods line and returns a real code with a confidence and a
candidate list, or a real abstention with a rationale. Show the actual output, including
one line that should abstain. Tests for the deterministic parts — the existence gate,
chapter normalisation and validation, candidate dedupe and ordering, the terminal
condition and the retry guard — none of which may touch the network.

Do not fake a working system. Anything unimplemented raises `NotImplementedError` naming
what is missing. Never return placeholder data, never swallow an error to keep the
pipeline green, and never write a function that looks real and returns a constant.
