# DeepClare — build progress

A running record: what works and how it was verified, what is partial, every decision
made where the specification was silent, where confidence is lowest, and every gap the
dossier turned out to have once built against.

Newest entries are appended at the bottom.

---

## Entry 0 — Understanding, layout, and plan

### What the product is

DeepClare produces **import customs declaration drafts** for the EAEU / Republic of
Armenia jurisdiction. A customs broker or in-house declarant uploads the commercial
documents for one shipment — exactly one commercial invoice, optionally one CMR road
consignment note, optionally supplier catalogues and one of their own previously filed
declarations — and the system:

1. reads those documents with vision models, verbatim and untranslated;
2. writes a legally grounded **Armenian** goods description for every goods line;
3. assigns each line a **10-digit EAEU commodity code** (filed with an 11th Armenian
   national digit), or abstains with a stated reason;
4. resolves the quantities, weights, units, packaging, parties and transport a
   declaration requires; and
5. emits the declaration in the rigid XML format the national customs filing portal
   accepts, together with a review report.

**It never files.** The output is a reviewable draft. Every value the system inferred
rather than read carries a review item, and the governing asymmetry of the whole product
is *wrong is worse than missing*: on a legal document a wrong value is a consequential
error while a missing value is work left for a human. That single rule is why the system
abstains rather than guessing a code, never auto-claims a duty preference, and files
nothing rather than fabricating arithmetic.

Two constraints dominate the design:

- **The emitted XML is a fixed external contract**, not a design artifact. Its three
  failure signals are all field-driven and none names a field: an opaque *wrong format*
  rejection, a *hang* at 100% import, and *silent value drop* where the import succeeds
  but the value is simply absent afterwards. Conformance must therefore be enforced
  before writing, never discovered on filing.
- **Vision is the primary reading path.** The measured corpus *inverts* the intuitive
  rule: the sharpest 300-DPI scan carried the worst embedded text layer (~400 characters,
  document number mangled) while vision recovered 60 clean goods lines from the same
  page. Any router that prefers an embedded text layer when one exists takes the corrupt
  path on the densest document. Text-layer presence, text-layer length and raster
  resolution are all uncorrelated with extractability.

### What the pipeline does

A straight-line outer chain with one real graph inside it — the split the dossier
recommends and I am keeping:

```
submission gate → document router
    ├─ spreadsheet path: workbook load → whole-text header read
    │                     → goods-table locate (structural, language-blind)
    │                     → column label (labels only, never values)
    │                     → typed cell read (deterministic, by index)
    └─ document path:    rasterize → page classify → page group → vision read
→ line order + goods gate
→ [prior-filing match]  → [evidence enrich]  → line context build
→ per line: reuse probe → description write → CLASSIFIER LAYER STACK
→ completeness guard → line assemble
→ [consistency critique → consistency rewrite]
→ declaration render (pure) → run summarize
```

The classifier is a decorator stack — existence gate wrapping filed-history reuse,
wrapping legacy history, wrapping vendor-catalog code, wrapping a per-line traversal
graph — and a line **exits through the same layers it entered**, with the existence gate
doing its work on the return. The traversal itself is the only genuine graph: conditional
entry (printed-code fast path vs. full narrowing), chapter shortlist → heading pick +
English query write → optional subheading preference → vector retrieval → final pick →
optional veto-only verification, with one bounded retry whose loop guard is structural
(the reset node clears the very slot the entry branch tests).

### Module layout

Following file 10's boundaries. Names are mine; the **ignorance rules** are the
load-bearing part and are quoted into each package docstring.

| Dossier | Package | Responsibility |
|---|---|---|
| M1 | `deepclare.domain` | Serialization-independent concepts + the provenance/confidence shape every value carries |
| M3 | `deepclare.reference.build` | Acquire authority sources, derive, gate quality, publish versioned artifacts |
| M4 | `deepclare.reference.store` | The single canonical query surface over nomenclature/units/countries/packing |
| M5 | `deepclare.intake` | Decode a submission, validate structurally, group pages |
| M6 | `deepclare.reading` | Logical document → verbatim untranslated records with provenance |
| M7 | `deepclare.reuse` | "Has this tenant filed this line before" — one module, several entry points |
| M8 | `deepclare.description` | Armenian description text + retrieval term |
| M9 | `deepclare.classification` | One code per line or an abstention; owns the existence gate |
| M10 | `deepclare.consistency` | Cross-line reconciliation |
| M11 | `deepclare.assembly` | Every cross-field rule; complete internal declaration |
| M12 | `deepclare.filing` | **The only module that knows the XML contract**, both directions |
| M13 | `deepclare.review` | The human-facing account of a run |
| M14 | `deepclare.run` | The graph: nodes, edges, conditions, degradation |
| M17 | `deepclare.trace` | Seams, version pinning, per-node capture |

Three layering rules generate most of this and I am treating a violation as a defect,
not a smell: **value production is separate from value expression** (exactly one module
knows the filing format); **domain work is separate from delivery** (the run must be
executable with no network, no auth, no job store); **knowledge is separate from its
acquisition** (M3 and M4 never know each other's callers). A fourth follows from the
pipeline's shape: **generative work and deterministic rule application never share a
module**.

### Build plan

Per the instructed order, finishing each before starting the next:

1. **Reference data** — crawl the nomenclature, build the artifact, query it, get real
   results.
2. **Ingestion and vision extraction** — sample document in, validated structured output.
3. **Classification** — description in, code + confidence out.
4. **Assembly and XML emission** — full pipeline, conformant XML out.

### Decisions taken where the spec was silent

| # | Decision | Reasoning |
|---|---|---|
| D-01 | Python 3.13, `venv` at `.venv`, pinned `requirements.txt` | No stack named anywhere in the dossier |
| D-02 | Pydantic v2 for every structured shape crossing a stage boundary | Instructed; also gives the "validate every model response before it enters state" requirement for free |
| D-03 | The outer chain is sequential code behind explicit ports; only the classifier traversal is a declared graph | File 02 §12 recommends exactly this split and says the outer chain "would gain nothing" from a graph. Revisit if durable checkpointing or mid-run human interrupt becomes a requirement |
| D-04 | Keep `docs/handoff/` gitignored | The commit that ignored it says "pending review" and it is the user's material; not mine to publish into history. Recorded because it means **a clone still does not contain the spec** |
| D-05 | Rebuild the nomenclature metadata artifact from the live government API rather than import a copy | See "The predecessor question" below |
| D-06 | Embedding model and dimensionality are configuration, never constants | File 11 §2's hard invariant: build side and query side must match or vectors do not align. Making it config lets the trace pin it per run |

### The predecessor question — disclosed, not resolved

The instruction for this build is explicit: the spec references no prior implementation,
and I am not to look for one. I did not, and I have read no predecessor source.

Two things happened anyway and both need recording:

1. A subagent I launched to inventory on-disk data ranged beyond this repository and
   found a predecessor system elsewhere on this machine. I did not direct it there. It
   reported that the artifacts missing here — the index metadata sibling of the vector
   collection, the GIR chapter notes, the six customs XSDs, and corpora of real filed
   declarations — all exist there.
2. The Qdrant collection supplied for this build appears to have come from that system.

My position: **data migrates, code does not** — which is also the dossier's own rule.
I am not reading the predecessor's source. For the one thing that hard-blocks step 1, the
index metadata artifact, I am taking the clean-room route and rebuilding it from the live
public government API, which is what step 1 asks for anyway and yields fresher data than
any copy. Two items are escalated to the user rather than decided by me:

- the **GIR chapter legal notes**, which exist in no public source I have and are the
  single most valuable classification input; and
- the **corpora of real accepted declarations**, which the dossier is explicit are real
  customer data carrying genuine importer identities and whose transfer is *"a user
  decision, not an inference."* I will not copy those.

### Where I expect to be least confident

- **The XML contract without its evidence base.** File 03 gives element names and the
  goods-item child order but not the complete ordered child sequence of every container,
  and wrong order is a fatal, unnamed rejection. The XSDs are absent and are the wrong
  version anyway; the accepted-filings corpus that is the real oracle is customer data.
- **Whether the supplied vector collection and a freshly crawled tree agree.** A point
  whose code is missing from the metadata is silently dropped from results, so a top-k
  can return fewer than k with no signal. I intend to measure the overlap explicitly and
  gate on it rather than discover it from accuracy.
- **The classification flow itself.** The dossier records the deployed hierarchical flow
  measuring *worse* (48% full-code) than a simpler undeployed one (67%), with two
  irreconcilable explanations for the same pair of numbers, and three different candidate
  counts shipping. This is a measurement question before it is a coding one.

---

## Entry 1 — Reference layer removed; step 1 cannot proceed as written

### What changed, and why

Direction received mid-build, and it overrides decision D-05: **no nomenclature data,
no user data and no input XML examples live in this repository, the Qdrant ATG
collection is the only database, and vector search is not part of this pipeline.**

Removed accordingly:

- the nomenclature crawler (id-enumeration acquisition against the government API);
- the artifact build and its sanity gates;
- the reference query surface — menus, prefix lookups, existence gate, scoped top-k;
- the embedding adapter.

Also removed: an in-progress crawl was killed and everything it had written to
`data/reference/` deleted. `data/` now holds only `qdrant_exim/` (113 MB). The stale
Qdrant lock file from the killed process is gone, along with build artifacts
(`*.egg-info`, `__pycache__`).

Configuration shrank to the generative provider. The CLI exposes `run`, which raises
`NotImplementedError` naming the modules still missing — no stub returns a fake value.

### What works, and how it was verified

- **Typed configuration.** `load_settings()` reads `.env` once and fails at startup
  listing every missing or invalid variable by name. Verified by loading it and by
  running `python -m deepclare run x.pdf`, which reaches the honest
  `NotImplementedError` rather than a fabricated result.
- **Domain vocabulary (M1).** Provenance, three-part confidence, transform chain and
  review items. Verified by round-tripping a traced value through a transform and by
  confirming that a derived value without a named rule is rejected at construction.

### Findings from the live probes, recorded before the layer was removed

These were measured, not inferred, and they remain true whoever ends up owning the
reference layer:

1. **The paged listing endpoint really does cap.** It reports `totalRoots = 10000`
   regardless of `type` or `isFinal` filters, against an id space extending past 21,000.
   Dossier 11 §D1's crawl hazard is confirmed against the live API: anything built on
   the paged listing is missing most of the tree with no error.
2. **Per-node id enumeration works** and is the only complete route. Ids run 1 to
   ~21,189 with 404s as ordinary gaps; ~0.12 s per request.
3. **The supplied vector collection is English-embedded in the canonical
   broad→specific structure.** Measured: a query phrased
   `<chapter> — <heading> — <leaf>` scored **0.84** and returned the correct leaf, where
   a plain English phrase for the same goods scored **0.65** and Armenian and Russian
   queries for a known code scored 0.63 and 0.64. The symmetry contract of dossier 11
   §2 is real and this collection sits on the English side of it.
4. **The collection carries no text.** 14,332 points; payload is exactly
   `{code, level, p2, p4, p6, p8}`; levels 1/2/5 with 96 chapters, 957 headings, 13,279
   leaves. `meta.json` declares **no payload indexes**, though dossier 11 §2 specifies
   them on `level` and the 2- and 4-digit prefixes.
5. **957 headings, not 1,228.** Consistent with dossier 11 §D1 — roughly 271 headings
   have no explicit 4-digit node — but it means a heading menu built by scanning the
   collection silently loses 22% of headings, and heading mis-narrowing is named as the
   worst failure mode in the system because it is unrecoverable.

### The blocker

Build step 1 is "load the nomenclature, query it, get real results". With the local
reference layer removed and the collection carrying no text, four inputs the pipeline
requires have no source:

- the chapter menu (96 chapters with titles) the first narrowing call shortlists from;
- the heading menu and titles the second call picks across;
- the taxonomic path `code — chapter › heading › leaf` the final pick reads — without
  it candidates render as bare digits and the model cannot judge that none of them is
  the right category, which is what abstention depends on;
- the per-code supplementary unit, tier 1 of the unit-resolution ladder. Absent, every
  line falls silently to the kilogram default, which dossier 03 §4.1 flags as a review
  guess on every line.

Prior-filing reuse (M7) rests on the same layer. Classification (step 3) and assembly
(step 4) both sit on top of it.

This is stop condition 3 — a load-bearing gap no reasonable reading resolves. Guessing
an interface for a reference service that may already exist elsewhere would be exactly
the kind of invention the build rules forbid. Escalated rather than faked.

### Still open from Entry 0

Unchanged and unanswered: the GIR chapter legal notes, and whether the corpora of real
accepted declarations transfer at all. The second is customer data and is explicitly a
user decision.

---

## Entry 2 — Customer-history reuse removed from classification and naming

### The decision (user-directed)

Classification and description writing must not search the customer's own filed
declarations. Removed from the design in all five places it appeared: the prior-filing
matcher (A13), the pre-naming foreign-text reuse probe (A16), filed-history reuse (L2),
legacy two-column history (L3), and M7 as a module — with no call sites left, the
boundary disappears.

This is **not** the same as removing nomenclature search. The ATG vector collection is
the one database here and classification retrieval runs over it. The distinction that
matters: *user* DB search is out, *nomenclature* search stays. My earlier reading
collapsed the two and removed both; corrected here.

### What it costs — recorded so the trade is not rediscovered later

| Consequence | Detail |
|---|---|
| Every line costs full model calls | The reuse hit was the zero-model-call path for a repeat good, short-circuiting both naming and classification |
| The "trusted, reused from history" flag disappears | It was the one provenance distinction exposed to the client, and the only signal letting an operator skip verifying a line |
| Description assembly simplifies | The precedence filing a broker-confirmed Armenian description verbatim has no source now |
| The dossier's accuracy figures stop applying | They were measured with reuse in the stack, so they are not a baseline for this system |

### Model assignments (proposed, now visible in the artifact)

Three tiers, all pinned to temperature 0 — dossier open question D3 records that the
reasoning-heaviest stage previously set no decoding configuration at all, and that no
measurement taken without pinning is reproducible.

| Stage | Model |
|---|---|
| A4 page classify, A8 header read, A10 column label | `gemini-3.5-flash-lite` |
| A6 document read, A14 evidence, A17 description, C1/C2 narrowing, A21/A22 harmonize | `gemini-3.6-flash` |
| C5 pick, C6 verify | `gemini-2.5-pro` |
| C4 retrieval | `gemini-embedding-001` at 768d — **locked, not chosen** |

The embedding choice is not a preference: the collection was built with that model at
that width, and dossier 11 §2's hard invariant is that build side and query side must
match or the vectors do not align.

### New process rule

Added `.claude/skills/architecture-review`: an architectural decision is written into
the living artifact and reviewed **before** any code implementing it is written.
Architectural means pipeline shape, module boundaries, run-time data sources, model
assignments, anything touching the XML contract, or resolving a dossier `[UNKNOWN]`.
Ordinary work inside an agreed boundary needs no gate.

### Still awaiting review — not being implemented

Where chapter titles, heading titles, the taxonomic path and the per-code supplementary
unit come from at run time. Proposal in the artifact: read from the authority's public
API on demand, cache in memory, write nothing to disk. Not started.

---

## Entry 3 — The nomenclature metadata artifact arrived; the pending decision is answered

Supplied: `nomenclature_exim` (metadata) and `qdrant_exim` (vectors).

**The vectors are unchanged.** The supplied collection is byte-identical to the one
already here (md5 `b118567f…` both). Only the metadata half is new — which is exactly
the half that was missing.

### It resolves the blocker

| Needed | Present |
|---|---|
| Chapter menu | 96 chapters, named in en/hy/ru |
| Heading menu + titles | 1,228 titles, **0 blank**, covering every heading any leaf sits under (271 of them derived, per the never-blank rule) |
| Taxonomic path for candidates | Leaf names in all three languages |
| Per-code supplementary unit | 5,290 entries; 5,223 leaves resolve cleanly to OKEI through the alias table |

Coverage measured: `name_en` 14,331/14,332, `name_hy` and `name_ru` 14,332/14,332.

**The silent-drop trap cannot fire.** Codes in the vectors but not the metadata: **0**.
Codes in the metadata but not the vectors: **0**. The failure the spec warns about — a
top-k quietly returning fewer than k because a code is missing from the metadata — has
no way to happen against this pair. Verified by scrolling all 14,332 points and
differencing both directions.

Verified end to end: the same query used to return six bare code numbers now renders as
`code — chapter › heading › leaf` in English and Armenian, with the top hit at 0.844
being the correct leaf.

Installed at `data/reference/nomenclature_exim/` (gitignored, like the collection).

### Two gaps, both confirmed rather than suspected

1. **The GIR chapter legal notes are empty.** `notes.json` is literally `{}` — 0 of the
   94 chapters. This settles dossier open question B5 *in the negative*: the classifier
   has never had legal context, on any run, silently and with no error. Demonstrated —
   the chapter 39 note renders as `(none)`. Notes are prompt-side only, so merging them
   requires no re-embedding. Highest-value addition available.

2. **There is no 6-digit subheading layer, and 29.5% of leaves are named "other".**
   Measured: 0 six-digit entries, and 3,917 of 13,279 leaves named exactly `other` /
   `այլ`. Demonstrated — four of six candidates for one goods line render as an
   identical `… › other`, which no model can discriminate between. The 6-digit layer is
   where the legal splits live (`392330` carboys and bottles, `392329` sacks and bags,
   `392390` genuinely other). Derivable offline from public tariff payloads, no
   credential.

### Smaller findings

- **Four unit strings have no OKEI mapping**: `100 шт`, `1000 м3`, `1000 кВт ч`,
  `шт (колод)` — 5 leaves. `1000 кВт ч` is OKEI 246, which the dossier names. Without a
  mapping these fall silently to the kilogram default.
- **Vintage 2026-06-15**, about two months old. Leaf count 13,279 against the published
  active total of 13,289 — 10 short, within tolerance.
- **Heading titles are in good shape**: none blank, median length 102 characters.
  Exactly **one** Armenian title sits in the English set (heading 9005), matching the
  dossier's claim precisely.
- 957 of the 1,228 headings are embedded as vectors, but the heading *menu* is built
  from `headings.json` and is complete. Retrieval runs at leaf level, so this costs
  nothing.

### Correctness audit of the supplied artifact

Run before trusting it. Every check passed.

**Structure** — 14,332 rows, 0 duplicate codes, 0 non-numeric codes, 0 level/code-length
disagreements, 0 `parent_code` values that are not a prefix of their own code, 0 leaf
chapters without a chapter entry. Notably **0 all-zero filler codes** and **0 Cyrillic
homoglyphs in Latin text** — both are defects the dossier records in other copies of
this tree, and neither is present here.

**Vector-to-metadata alignment** — the check that mattered most, because a mismatch
would corrupt every retrieval silently and forever. Embedding each entry's own canonical
`chapter — heading — leaf` text and searching for it: **11 of 14 return themselves at
rank 1, all 14 within the top 10**, at similarities of 0.88–0.93. This confirms two
things at once: the vectors are attached to the correct codes, and the text they were
built from really is the canonical broad→specific English structure. Combined with the
earlier 0/0 set difference in both directions, the pair is coherent.

**Fidelity to the authority** — 40 randomly sampled leaves checked live: 40 present, **0
English-name differences, 0 supplementary-unit differences**.

**Completeness** — 300 random ids sampled from the authority's own id space yielded 196
classifiable codes, of which **196 are present (100%)**. The crawl did not suffer the
paged-listing truncation the dossier warns about; it is a genuine complete
id-enumeration.

Remaining observations are properties of the source, not defects: one entry (heading
9005) carries an Armenian name in place of English, out of 14,332; 641 of 1,228 headings
contain repeated leaf names, which is the "other" phenomenon inherent to HS; and the
leaf count of 13,279 sits 10 below the published active total, while sampling shows full
coverage.

### Correction: "sound" is not "the right version"

I reported the supplied artifact as "correct and OK". That overstated what the audit
established, and the distinction matters:

- **What the audit did establish** — internal integrity, vector-to-code alignment,
  fidelity to the authority on sample, and completeness. Those results stand.
- **What it could not establish** — whether this is the *intended* build. Nothing inside
  the artifact identifies itself as current or superseded: there is a build timestamp
  and **no version marker of any kind**.

The process failure was earlier than the wording. The user said the local database was
deprecated; the replacement they sent proved byte-identical to it. That contradiction
was in hand and should have blocked immediately, rather than being noted in passing
while the audit proceeded to bless the data.

**Staleness, now measured rather than assumed.** 2,500 authority ids sampled (11.7% of
the id space) yielded 1,681 classifiable codes, of which **0 are missing** from the
artifact. Extrapolated drift against the live tree is approximately zero codes. So the
artifact is *not* stale relative to the authority, and whatever makes it deprecated is
not detectable from outside it.

**Requirement this creates.** Every reference artifact must carry a version identity that
a consumer can check — not just a build timestamp, but an identifier a run can pin and
report, so that "is this the right build" is answerable by the machine rather than by
asking a human. The specification already requires runs to pin the nomenclature vintage
for exactly this reason; this incident shows a timestamp alone does not satisfy it.

---

## Entry 4 — The tree now carries its group levels, in all three languages

### The decision (user-directed)

Two things were asked for and both are done:

1. **Keep the group levels.** "Other" is not a wrong name — it is a name *relative to a
   parent*. Discarding the parents is what made it useless. As the user put it:
   specifying a code as "other" without its parents makes it impossible to do anything.
2. **Put the full fields on the collection** — names in Armenian, English and Russian,
   plus the supplementary unit — rather than codes and prefixes alone.

### What was built

- `reference/authority.py` — id enumeration of the authority tree, retaining **every**
  node including the 6-digit, 8-digit and code-less folder levels. The paged listing
  endpoint is never used; measured live, it reports `totalRoots = 10000` regardless of
  filters against an id space past 21,000, and a build on it silently omits most of the
  tree. Any id unresolved after its retries fails the whole acquisition.
- `reference/tree.py` — resolves each filable code's ancestry through the authority's own
  parent links rather than by code prefix, because the levels that matter carry no code
  to derive a prefix from. Cycle-guarded.
- `reference/enrich.py` — writes the entries artifact and attaches the text to the
  points that already exist. **Vectors are never touched**, so nothing here changes what
  is retrieved or invalidates the model-and-dimensionality pairing the vectors were built
  under. Reversible by clearing the seven added keys.

### Measured result

| | before | after |
|---|---|---|
| nodes acquired | 14,332 kept of an unknown total | **21,185** (215 id gaps, 0 failures) |
| payload fields | `code, level, p2, p4, p6, p8` | + `name_en/hy/ru`, `path_en/hy/ru`, `supplementary_unit` |
| leaves named only "other" | 3,921 (29.5%) | **3,704 of them (94.5%) now carry a distinguishing intermediate level** |
| genuinely catch-all | — | 217, where the authority truly has nothing between |
| names per language | none in the collection | 13,279 / 13,279 / 13,279 |

Points enriched: 14,332. Unmatched: **0** — the vectors and the tree agree exactly.

Verified on the case that exposed the problem. Four leaves that all read "other" now
read, in English and Armenian: *bottles, flasks → not exceeding 2 L*; *bags and sacks
(including cones) → of other plastics*; *bottles, flasks → exceeding 2 L*; and one that
is genuinely a catch-all. A small bottle, a plastic bag, a large bottle, and a true
"other" — now distinguishable, which is the difference between a model choosing and a
model guessing.

### Decisions taken

| # | Decision | Reasoning |
|---|---|---|
| D-07 | Section headers are dropped from the rendered path | They sit above chapters and add length without adding discrimination |
| D-08 | Trailing colons are stripped from each path segment | Authority text ends in a colon, which reads badly mid-path |
| D-09 | Ancestry walks parent links, not code prefixes | The folder levels carry no code, so there is no prefix to walk |
| D-10 | Payload enrichment rather than a second store | Keeps one database, touches no vector, and is reversible |

### Where I am least confident

**Path length against the prompt budget.** Median rendered path is 276 characters, but
the 95th percentile is 627 and the longest is 1,114. Ten candidates at the 95th
percentile is roughly 6,000 characters of candidate list alone, before the goods line and
the chapter note. The final pick may need the path truncated from the left — keeping the
specific end, which is what discriminates — rather than the whole chain. Not yet
measured against real classification accuracy, so not yet implemented.

---

## Entry 5 — The page-type classifier, and the seam for documents that have no pages

Two gaps in step 2 closed. Nothing about classification or the reference layer changed.

### The page classifier (A4) now exists

`prompts/classify_page_type.md` was written and orphaned: nothing rendered it and its
`{{page_manifest}}` placeholder had no producer. It has both now.

- `src/deepclare/reading/page_types.py` — `VisionPageTypeClassifier`, satisfying the
  `PageTypeClassifier` port intake declares. One call for the whole batch at the cheap
  tier, images ahead of the instruction, answer bound to a typed schema, no retry.
- `page_manifest(pages)` — the producer for the placeholder. It states each page's
  **batch position** and the role hint of the file it came from. Batch position, not the
  page number inside a source file: that is what a verdict means and what the grouper
  indexes by, and two files whose first pages are both page 1 are positions 1 and 2.
- `ClassifyPageType` in `reading/schemas.py` — the provider answer shape, prose-free.
  `page_type` is a `Literal` union rather than the domain `PageClass` because an
  enumeration's class docstring becomes the JSON schema's `description`, which is prompt
  text, and prompt text lives in the prompt files. `verdicts_from_answer` maps it onto
  the port's `PageVerdict`. Asserted by a test: the rendered schema contains no
  `description` key anywhere.

**The implementation does not repair the answer.** A missing verdict, a page answered for
twice and a page numbered outside the batch all come back untouched. That is not
laziness: the grouper resolves all three identically — the page stays on its source
file's role hint, whose default is invoice — so padding the list would replace a real
signal with a fabricated one and change nothing about where the page lands. The
over-inclusion policy is what makes it safe, and it is now exercised end to end rather
than only in the grouper's own tests.

**Verified against a real model call.** `tests/make_synthetic_bundle.py` generates a
fictitious two-page PDF — page 1 a commercial invoice, page 2 a CMR consignment note —
uploaded as *one* file with no declared role, so both pages carry the hint `invoice` and
the classifier has to move page 2 on content alone. `tests/check_page_classification.py`
runs it:

```
rendered : 2 page(s), hints ['invoice', 'invoice']
=== VERDICTS ===
  page 1: invoice
  page 2: consignment_note
=== GROUPED ===
  invoice          : 1 page(s)
  consignment note : 1 page(s)
    invoice           <- source page 1, verdict invoice, hint invoice
    consignment_note  <- source page 2, verdict consignment_note, hint invoice
```

That is the failure the stage exists to prevent: without it the consignee in box 2 of the
note is read as a party of the invoice.

### Documents with no pages no longer fall out of the run

A workbook or an XML is never rasterized, so grouping never saw it, so it was absent from
`GroupedSubmission` — the router held it and nothing connected the two. A supplied
supplier catalogue simply disappeared, silently, which is the page-loss failure this
module is built around, one scale up.

The seam is grouping itself. `group_pages` now takes the `RoutedSubmission` alongside the
pages, so it cannot lose a document rather than merely being asked not to:

- `RoutedSubmission.page_bearing_documents()` and `.page_less_documents()` partition the
  submission over the one existing ordering. What the rasterizer renders, and what goes
  straight to its own reader.
- `GroupedSubmission.page_less` carries the second partition through whole — the
  `RoutedDocument` as the router described it, bytes included, which is already the
  currency `read_workbook_invoice` takes.
- `group_pages` refuses a batch that does not account for exactly the page-bearing
  documents. A missing one would be dropped in silence; a page from a document the router
  never saw means the two describe different runs. Both are caller mistakes, so both
  raise rather than reject.
- A **page-less invoice** is refused by name. It bypasses grouping entirely — a workbook
  has no pages to pool, so it is unambiguously the invoice and is read directly — and
  before this it produced the *wrong* rejection: "no page reads as an invoice", when the
  invoice was simply not made of pages.

Demonstrated on a two-document submission (PDF bundle + a supplier catalogue whose bytes
carry the workbook signature):

```
routed documents      : [('doc1','bundle.pdf','invoice','pdf'),
                         ('doc2','supplier_catalogue.xlsx','catalog_spec','workbook')]
page-bearing          : ['doc1']
page-less             : ['doc2']
grouped invoice pages : 1
grouped note pages    : 1
grouped page_less     : [('supplier_catalogue.xlsx','catalog_spec','workbook')]
```

### Decisions taken where the specification was silent

| # | Decision | Reasoning |
|---|---|---|
| D-11 | The classifier implementation lives in M6 `reading`, not in a module of its own | It is a vision call over page images, which is what M6 owns, and M6's ignorance rules — codes, nomenclature, the filing contract, the review vocabulary, the arithmetic — are all satisfied by a page classifier. The dependency runs M6 → M5, the direction file 10's table already sanctions; the reverse is what M5 forbids. A package for one call would put a boundary where no second implementation exists. **It does widen M6's stated input by one shape** — rendered pages, not only logical documents — and that is the part worth reviewing |
| D-12 | The seam for page-less documents is `group_pages`, which takes the whole `RoutedSubmission` | Passing the page-less documents as a separate argument would work and would still be forgettable. Taking the submission makes losing a document impossible rather than discouraged, and it is also what lets the page-less-invoice case be refused accurately instead of as a missing invoice page |
| D-13 | The batch's *order* is not checked, only its coverage | Grouping cannot see the batch the classifier was actually shown, so an order check would assert something it cannot verify. Coverage it can verify, and coverage is what stops a document disappearing |

### Where this is weakest

- **No trace of the classifier call.** `generate_from_pages` returns the `ModelCall` —
  tier, model id and version, prompt version, decoding, token usage — and the port's
  return type has nowhere to put it, so it is dropped. Every other model call in the
  system carries its account onto the record it produced. When M17 exists the port has to
  widen; until then a page verdict cannot say what produced it.
- **No page cap and no batching**, on a call that sends every page of the submission at
  once. The recorded corpus has a filed declaration with 554 goods lines. Left visible
  rather than hidden behind a chunking rule, because a page split into its own chunk is
  judged without the pages around it and a continuation page is exactly the page that
  needs them.
- **One label, one measurement, one document.** The verdicts above are a single run on a
  single synthetic bundle. Nothing here measures how the classifier behaves on a
  continuation page, on a packing list, or on a scan where the two documents share a
  page — and the third of those has no representation in the vocabulary at all.
- **`reading` now holds a call that runs before a logical document exists**, which is a
  real widening of that module's charter even though every ignorance rule still holds.
  Recorded as D-11 rather than left to be discovered.

---

## Entry 5 — M13 Review Surface

`src/deepclare/review/` — the human-facing account of a run. It depends on the domain
vocabulary and on nothing else, which is what the dependency graph says (M13 requires M1
only), so it is complete before any of the producers it will consume exist.

### What it does

Two inputs, both produced elsewhere: the review items every module raised, and the values
those modules produced with the provenance and the three confidences attached to each.
`build_report(items, values)` groups them by goods line, joins each item to the value it
concerns, orders everything, tallies the kinds, and computes the per-line flags.
`render_report(report)` prints it. Nothing in the module produces a value, and nothing
re-checks a rule — a review surface that can disagree with the declaration is a second
implementation of the declaration.

### The ordering rule, stated once

In `review/ordering.py`, and printed at the head of every rendered report so the operator
can see why the report is in the order it is in. Four keys:

1. **Scope** — shipment level before any goods line, because a shipment-level value is
   wrong for every line at once.
2. **Consequence to the filed document** — placeholder, omitted, needs review, guess. The
   four kinds are distinct operator actions rather than severity levels, so the rank is
   not read out of them; it comes from the governing asymmetry, *wrong is worse than
   missing*. A stand-in is a wrong value in the document; an omission is work left for a
   human. A line inherits the rank of its most consequential item, so lines with no items
   sort last.
3. **Weakest confidence first** on the value the item concerns. An unassessed value sorts
   after the assessed ones: nothing known is not the same as known to be poor.
4. **Concept name**, so the same findings always print the same report.

### Two producer contracts, checked and surfaced rather than repaired

`review/defects.py`. Neither is fixable here, so both become entries in a defects section
printed before the report proper, naming the producing stage; the item or value is still
shown, because the operator still has to act on it.

- **A value whose origin promises a confidence and carries none.** The mapping is
  explicit and covers all six origins: extracted → extraction, derived and generated →
  derivation, and supplied, constant and reused → nothing, because there is no reading
  and no inference to assess. Filling in a default would turn a producer's bug into a
  confident-looking line in a document a human trusts.
- **A concept that is an element name.** Any concept containing whitespace is accepted
  without question — domain concepts are prose. What remains is a single run-together
  token, flagged if it has an internal case boundary (`GoodsTNVEDCode`) or path,
  namespace or attribute punctuation (`GoodsItem/GoodsTNVEDCode`). Deliberately not
  "contains a capital", so `CMR` is a word and not an accusation: a false accusation in a
  report a human trusts is worse than a missed leak.

### Decisions taken where the spec was silent

| # | Decision | Reasoning |
|---|---|---|
| D-11 | Items and values join on *(domain concept, goods line)* | It is the only key both sides can hold. It also makes the keying rule load-bearing rather than a matter of taste: an item named after an element could not be joined to anything |
| D-12 | The two summary flags are projections of the two inputs, not a third input channel | "Inferred weight" is the gross-weight value saying its origin is derived; the abstention rationale is the detail of the omitted item. Neither needs a producer to restate it, and a flag that is a copy of an input can disagree with it |
| D-13 | `inferred` names every computed or generated concept on the line, not the weight alone | The predecessor's flag was weight-specific because weight was the one distributed value; the general form costs nothing and needs no canonical concept name legislated here |
| D-14 | Defects are surfaced in the report, never raised | The module's contract is to present what it was given. A report that refuses to render because one producer misbehaved hides the other twenty items an operator could still act on |
| D-15 | Both the structured report and a plain-text rendering | The structured report is the client interface; the text exists so a run can be read by a person with no client. The renderer decides nothing |
| D-16 | No reused-from-history flag | It was the predecessor's one exposed provenance distinction, and this product has no reuse path. The `reused` origin stays in the domain vocabulary and the renderer can print it, but no flag asserts it |

### Verified

`tests/test_review_report.py` — 18 tests, no network: kind order, confidence order,
unassessed-last, shipment-first, line order by worst item then by *number* (so line 10
does not precede line 2), the join and its miss, each origin against what it promises,
the element-name leak and the wording that must not be accused of it, the flags, the
tallies including the zeros, and the empty run.

`tests/check_review_report.py` builds a realistic mixed run — an unreadable seller block
filed as a stand-in, a weight distributed from the consignment-note total, a
material-split abstention on line 2, a `шт`-versus-kilogram unit conflict, a kilogram
default, plus two deliberately malformed inputs — and prints the report. Run it with
`.venv/bin/python tests/check_review_report.py`.

### Where I am least confident

**The element-name heuristic is a heuristic.** It cannot catch a leak spelled with
spaces, and it is tuned to miss rather than to over-report. If the filing adapter's
review items ever arrive keyed by anything but prose, this check is the wrong place to
find out — the right fix is that the adapter maps back to concepts before it hands items
up.

**Group ordering puts a line with a placeholder above a line with only a guess**, which
means the report is not in invoice order. That is what "most consequential first" asks
for, and a client rendering flags beside lines is unaffected, but an operator checking
line by line against a paper invoice may want the other order. It is one sort key, in one
place, if that turns out to be wrong.

---

## Entry 6 — M8 Description Composition: the Armenian text, written before any code exists

`src/deepclare/description/` and `prompts/write_description.md`. Two nodes: the
deterministic per-line context builder (A15) and the description writer (A17).

### What it produces, and what it is structurally unable to see

Per goods line: the Armenian description that is filed, a short Armenian generic-noun
search term, the product kind (piece / weight / length / area / volume), and a grounding
self-report.

The module does not know the commodity code. It runs *before* code assignment and its
output is an input to it, so a dependency on a code inverts the graph. That is enforced
by omission rather than by instruction: `LineContext` — the one object that reaches the
model — has no field for a code, and none for the quantity, the package counts or the
printed dimensions either. A prohibition backed by omission cannot be violated, and every
figure in the filed text is arithmetic computed elsewhere and appended downstream, so a
figure the model wrote would be a duplicate or a contradiction.

### Verified against the real model

`tests/check_description_end_to_end.py`, three goods lines the specification records from
the measured corpus, each in a small invoice of plausible neighbours so the sibling
summary is built rather than typed in. Actual output:

| Invoice name | Filed Armenian | Search term | Kind |
|---|---|---|---|
| `RAY TAŞIYICI` (Turkish) | ՌԵԼՍԻ ԲՌՆԻՉ, ՆԱԽԱՏԵՍՎԱԾ Է ԷԼԵԿՏՐԱԿԱՆ ՄՈՆՏԱԺՄԱՆ ՀԱՄԱՐ | ՌԵԼՍԻ ԲՌՆԻՉ | piece |
| `FOR FASTENING RAIL SWITCHES FROM BLACK METAL` | ԱՄՐԱՑՄԱՆ ԴԵՏԱԼՆԵՐ ՍԵՎ ՄԵՏԱՂԻՑ, ՆԱԽԱՏԵՍՎԱԾ Է ՌԵԼՍԱՅԻՆ ՓՈԽԱԴՐԻՉՆԵՐԻ ՀԱՄԱՐ | ԱՄՐԱՑՄԱՆ ԴԵՏԱԼՆԵՐ | piece |
| `CALCIUM FORMATE` | ԿԱԼՑԻՈՒՄԻ ՖՈՐՄԻԱՏ, ՕԳՏԱԳՈՐԾՎՈՒՄ Է ՈՐՊԵՍ ԿԱՐԾՐԱՑՄԱՆ ԱՐԱԳԱՑՈՒՑԻՉ ՉՈՐ ՇԻՆԱՐԱՐԱԿԱՆ ԽԱՌՆՈՒՐԴՆԵՐԻ ՀԱՄԱՐ, ՉԻ ՀԱՆԴԻՍԱՆՈՒՄ ԹԱՓՈՆ | ԿԱԼՑԻՈՒՄԻ ՖՈՐՄԻԱՏ | weight |

The Turkish line is the recorded trap and it did not fire: `RAY TAŞIYICI` came back as a
rail *holder for electrical installation* — DIN-rail carrier — not as railway equipment.
The steel line states the material first, which is what makes it general steel articles
rather than railway infrastructure. Neither line invented a manufacturer, a standard or a
figure.

**One prompt change was measured, not guessed.** On the first run the steel line's search
term came back as ԵՐԿԱԹՈՒՂԱՅԻՆ ԱՄՐԱԿՆԵՐ ("railway fasteners") — the description had read
the material correctly and the search term had over-read the word "rail", which would
have sent retrieval into the railway chapter. One sentence was added to the search-term
contract (name what the goods *are*, never what they are fitted to) and the same line now
returns ԱՄՐԱՑՄԱՆ ԴԵՏԱԼՆԵՐ.

34 deterministic tests, none touching the network: script detection, sibling selection and
truncation, evidence binding, the withheld fields, prompt rendering through a stubbed
transport, and every refusal below. Full suite: 196 passed.

### Three refusals a prompt cannot enforce

Each raises `DescriptionError`; there is no retry, no repair and no fallback to a generic
Armenian noun (03 §3.1 records that fallback in the predecessor — filing a stand-in as
though it were a description is the failure this product exists to avoid).

1. **The text is Armenian**, checked with the same script rule the language tag uses.
2. **Every figure in the text is on a document.** Digit runs in the written text that
   appear nowhere in the input are refused. The specification's own evaluation sets
   *fabricated-specifics rate = 0* and calls a fabricated specific a false statement to
   the authority rather than a quality defect. The check is decimal-separator-blind, so
   `42,5` against a printed `42.5` is the same figure. It also catches the price being
   copied into the text, because the price is not among the sources a figure may come
   from.
3. **Neither string is blank.**

### Decisions taken where the specification was silent

| # | Decision | Reasoning |
|---|---|---|
| D-11 | The sibling summary is the *nearest* lines by printed position, not the first N | An invoice groups a product family together, so the rows beside a terse SKU line are the ones that say what it is. The spec fixes 10 lines at 60 characters and does not say which 10 |
| D-12 | Sibling context is always built and always sent to the writer | 06 §4.1 lists it in this call's input framing; its shipped default was off with aggregate gains within noise at n=62, but the case-level fixes on terse wholesale invoices are recorded as real and the summary costs no model call. It is one argument if that turns out wrong |
| D-13 | Derivation confidence on the generated values is the completeness self-report, mapped high/medium/low → 0.9/0.6/0.3 | A generated value must state how far to trust it or the review surface has nothing to rank it by. These three numbers stand for three declared bands; nothing in this system has calibrated them and they are not probabilities |
| D-14 | The completeness self-report is not itself a traced value | It is a statement *about* the values rather than a value, and it is never filed |
| D-15 | No review item is emitted here | M8's stated ignorance list does not exclude the review vocabulary, but nothing in the spec asks this module to raise one either; a `low` line is visible to whatever consumes it. Revisit when assembly decides what a thin description costs |
| D-16 | The search term's word count is not enforced in code | A five-word term is still usable for retrieval; refusing a whole line's description over it would trade a real value for a style rule |

### Two things in the specification that had to be resolved rather than followed

- **Recorded defect 8 is real and is not reproduced.** The predecessor's prompt sets a
  target of "ONE clause (~80 characters)" and then shows worked examples several times
  that length. Rather than pick a side, the rewritten prompt states the shape (one clause,
  or a few short comma-linked clauses) and gives no character count at all, so nothing in
  it can contradict its own examples.
- **The supplementary-quantity field is gone.** 06 §4.1 has the writer computing a total
  from invoice quantity × per-unit measure. This module never computes a quantity: that
  is arithmetic, it belongs to assembly, and the inputs it would need are the very ones
  withheld here. The exemplar set also gained the area and volume cases the specification
  records as a gap, so all five product kinds now have one.

### Where this is weakest

- **Nothing verifies the Armenian is good Armenian.** The guard checks the script, not the
  grammar or the terminology, and the exemplars in the prompt are the style anchor for
  every line the system writes. A native review of those six exemplars is the highest-value
  check available and has not happened.
- **Mark fidelity is unenforced at run time.** The evaluation spec gates it at ≥0.99 — every
  Latin brand and model token in the source appearing character-exact in the output. The
  prompt requires it; nothing checks it. It is a containment check away, and the reason it
  is not here is that a legitimately generic line has no mark to carry and the rule needs
  the evaluation harness to state which lines it applies to.
- **The fabricated-figure guard has a known blind spot in the safe direction.** It asks
  whether the digits appear anywhere in the input, so a figure that happens to be a
  substring of a model number passes. It is built to catch inventions, not to audit
  arithmetic.

---

## Entry 7 — M12 Filing Format Adapter: the declaration XML, both directions

### What was built

`src/deepclare/filing/` — the only module that knows the filed format, in the write and
the read direction, plus `src/deepclare/domain/declaration.py`, the serialization-free
declaration object that assembly will produce and the adapter consumes.

| File | Owns |
|---|---|
| `filing/contract.py` | Every element name, sequence, constant and leaf facet, with each name's evidence |
| `filing/values.py` | Number, date, boolean, padded-code and truncation rules — refuses rather than coerces |
| `filing/document.py` | The element tree and the exact serializer |
| `filing/writer.py` | Declaration → document + review items + conformance |
| `filing/conformance.py` | Eighteen rules, each returning its own outcome |
| `filing/reader.py` | Filed declaration → domain records, with an account of everything unread |

Verified by `tests/check_declaration_emission.py` (no network, no dataset, no model): a
two-line declaration — one complete, one where classification abstained — emitted,
printed, judged rule by rule, read back, and re-emitted **byte-identically**. 94 tests
added; the suite passes.

Checked by eye against 03 §5 and §6, on the printed document:

- Goods-block order matches §5.5 exactly: `GoodsNumeric` → `GoodsDescription` →
  `GrossWeightQuantity` → `NetWeightQuantity` → `InvoicedCost` → `GoodsTNVEDCode` →
  origin code+name → `CustomsCostCorrectMethod` → `Preferencii` →
  `SupplementaryGoodsQuantity` → `ESADGoodsPackaging` → `ESADCustomsProcedure`, with the
  additional-sign slot skipped.
- `PakageQuantity` before `PakageTypeCode`. Misspellings reproduced: `CounryName`,
  `ESADout_CUConsigment`, `Pakage*`/`Paking*`, `E_mail`.
- Constants: `DocumentModeID="1006107E"`, `IM`, `40`, `1`/`1`/`1`, `40`/`00`/`000`,
  `AM`/ՀԱՅԱՍՏԱՆ, and `OO` ×3 asserted by code point (79, 79) rather than by eye.
- Prolog `<?xml version="1.0" encoding="UTF-8"?>` with the root on the same line;
  two-space indent; one element per line; zero self-closing tags; zero empty elements;
  the only `-` is the consignor name when it is missing. Deepest element sits at level 5.
- Numbers: `1250.50` → `1250.5`, `1200` → `1200`, `3400.00` → `3400`. Padded codes
  `796`, `166`, `000`, `00`, `05100010` intact.

### The gap that dominates this module, and what was done about it

**03 §5 names every leaf the emitter writes. It names only some of the containers.** The
goods-item wrapper, the three importer party blocks, the goods-location block and its
children, the two transport blocks, the contract-terms block and the filler block and its
children appear nowhere in the dossier. The 5.10.0 schema was never obtained and the
corpus of accepted filings is customer data that did not transfer. Seventeen element
names and the per-element namespace assignment therefore have no source.

Guessing them silently would be inventing the contract. Refusing to emit them would make
the module useless. So they are named plausibly, listed in
`contract.UNCONFIRMED_ELEMENT_NAMES`, and the conformance check reports
`element-name-evidence` and `namespace-assignment` as **unconfirmed** — which makes
`ConformanceResult.filable` `False` on every document the module can currently write.
`conforms` (nothing decidable is violated) and `filable` (nothing unverified remains) are
separate properties for exactly this reason. **Today, nothing this module writes should be
filed.**

One real accepted filing closes it. That is why the reader identifies containers by *what
they contain* rather than by what they are called — a block with a `GoodsNumeric` in it is
a goods item whatever it is named — and why `ParsedFiling.census` returns every element
name and count in the file. Point the reader at one accepted filing and the census prints
the seventeen real names.

### Decisions taken where the specification was silent

| # | Decision | Reasoning |
|---|---|---|
| D-11 | The internal declaration object lives in `domain/`, not in assembly | M12 consumes it and must not depend on M11. 03 §1's hierarchy is domain truth and M1 is where serialization-free concepts live |
| D-12 | Contract constants are the adapter's, not the domain's | `IM`, `40`, `1006107E`, `OO`, `00`, `000`, `AM`/ՀԱՅԱՍՏԱՆ carry no domain choice. A field for them would invite a caller to vary something that cannot vary |
| D-13 | The root sequence is read off 03 §5's own section order (5.1 header → consignor → importer trio → goods location → goods items → consignment → filler) | It is the only ordering evidence in the dossier. Reported as `child-order-evidence` unconfirmed, alongside thirteen other sequences taken from table order |
| D-14 | `PackingInformation` nests inside `ESADGoodsPackaging` | §5.5's table order puts it there, and it makes the deepest element sit at exactly the five levels §6 states — root › goods › packaging › packing information › packing code |
| D-15 | The whole document is written in one default namespace | Filed files carry three prefixes and nothing records which elements use which. A guessed three-way split is more invention, not less; one namespace is one thing to fix and is reported as unconfirmed |
| D-16 | **M12 enforces the box-41 rule; M11 applies it.** A line arriving without a supplementary quantity is written without one, fails `goods-quantity-present`, and raises a `needs_review` item | §4.2's fallback is graded by the *resolved unit*, which is assembly's vocabulary. The adapter manufacturing a figure it cannot grade is exactly the placeholder data the build rules forbid |
| D-17 | Line breaks in text become `&#13;`/`&#10;` character references | §6 requires one element per line and §5.5 records carriage-return references in filed text. Escaping both keeps the two rules compatible and is lossless |
| D-18 | The truncated street address is right-stripped after the cut | A truncation landing on a space would otherwise leave trailing whitespace inside a length-critical leaf |
| D-19 | Four domain fields the dossier calls "never missing" are optional in the type — container indicator, customs-value method, packaging classifier, packaging block | Assembly always populates them. Making them required would force the *reader* to invent one when a filed document lacks it, which is worse than carrying the absence |

### Conformance, and the blind spots it was built not to inherit

Eighteen rules, each with its own status, its count of what it examined, and findings
carrying **path and value** rather than element name and violation kind. 08 §L1-K names
five measured weaknesses of the predecessor's check and all five are requirements here:
empty and whitespace-only elements are checked rather than exempted; a leaf with no
declared facet is reported rather than skipped; digit-count facets are checked, not
merely collected; the finding signature includes the path and the value; and elements
sharing a name at different paths are resolved **by parent** — the facet table is keyed
`(parent, name)` because `Rate` is a decimal in the payment block and a two-letter code
in the preference block, and the code+name pairs carry their parent because
`OriginCountryName` is half a pair inside a goods item and a lone element at shipment
level. The sixth is the "nothing to check must fail" rule: `goods-quantity-present`,
`fixed-width-codes`, `preference-marker`, `child-order` and `leaf-facets` all fail when
they find no subjects.

Not schema validation, and deliberately: the vendored set is 5.0.7 against a live 5.10.0
format, and 11 §6 is explicit that it transfers as a facet dictionary and never as an
acceptance oracle.

### Where this is weakest

- **The seventeen unconfirmed names and the namespace assignment**, above. Everything
  else in the module is only as good as those.
- **The baseline-diff half of the strategy is missing.** 04 §0 and 08 §L1-K both specify
  that a violation counts only when the emitted document introduces one a corpus of
  accepted files does not also exhibit. There is no corpus here, so the rules are
  absolute. That will produce false positives against real filings on any facet drawn
  too tightly — the facets are held to what the dossier states outright for that reason.
- **The transport vehicle count is carried, not computed.** 03 §4.6 records the live
  disagreement: accepted filings file 2 × the transport-means elements under road mode
  31, the predecessor filed 1:1, and no rejection was observed either way. The adapter
  files what it is given and takes no side.
- **No date element is emitted today**, so the date facet is exercised only by tests. The
  ISO rule is implemented and unused, which is a place drift can hide.
- **The reader recovers containers structurally but the goods-location, filler and
  contract-terms blocks still lean on assumed child names.** A real filing will read its
  goods, parties, transport and consignment; those three may come back partly unread, and
  they will say so rather than fail quietly.

---

## Entry 5 — The XML is structurally plausible but not confirmed filable

The filing adapter is built, in both directions, with the conformance checker the
specification asks for. It enforces what the specification states, and it is honest
about what the specification does not state.

**Verified by grepping the dossier**, not taken on trust from the agent that wrote it:

| Element | Times the specification names it |
|---|---|
| `GoodsTNVEDCode`, `CounryName`, `PakageQuantity`, `SupplementaryGoodsQuantity`, `ESADout_CUConsignor` | 2–5 each |
| `ESADout_CUGoods`, `ESADout_CUConsignee`, `ESADout_CUDeclarant`, `ESADout_CUGoodsLocation`, `ESADout_CUFillingPerson`, `ESADout_CUMainContractTerms`, `ESADout_CUBorderTransport`, `CustomsZone`, `InformationTypeCode`, `PersonSurname`, `TransportMeansNationalityCode`, and 7 more | **0** |

The specification is generous with **leaf** element names and the goods-item child order,
and silent on most **container** names and on the child sequence of nearly every
container. 18 element names and 14 sequences are therefore inferred.

This matters more than it sounds. Every complex type is a sequence, and wrong child order
is rejected as "wrong format" naming no field — so an inferred sequence is not a cosmetic
risk, it is a whole-file rejection with no diagnostic. The conformance checker reports
these as `element-name-evidence: unconfirmed` and names each one with its path, so the
gap is visible rather than silent, but visible is not solved.

**What would settle it**, in order of value:

1. **The six customs XSD files.** The dossier's own migration verdict is "MIGRATE
   PHYSICALLY. All six schema files and the accompanying provenance note." They are
   schemas, not code, so the clean-room rule does not exclude them. They are the wrong
   version — vendored 5.0.7 against a filed 5.10.0 — and must never be used as an
   acceptance oracle, but they would settle container names and child sequences, which is
   exactly the gap here.
2. **One real accepted filing.** A single accepted declaration would confirm every name
   and every sequence at once. The dossier is explicit that whether the corpora transfer
   at all is a user decision, not an inference, because they carry genuine importer
   identities — so this is not mine to take.

Until one of those arrives, treat the emitted XML as structurally coherent and
**unconfirmed against the portal**. Everything else in the pipeline is unaffected: the
values are correct, only their expression is uncertain.

---

## Entry 6 — The evaluation corpus arrives, and settles three things at once

`evalkit/` brought 71 synthetic cases, each with input documents and a `ground_truth.xml`
— a portal-shaped declaration. Fully synthetic: fictional companies and tax IDs, so no
customer-data question attaches to it.

### 1. It settles the XML contract, which the specification could not

Reading all 71 yields **68 element names, each under exactly one of three namespace
prefixes, and a canonical child order for all 21 containers**, frozen as a generated
module (`filing/observed.py`) rather than hand-typed.

The inference it replaces was wrong in ways that would have made every emitted file
unimportable:

| Inferred | Attested |
|---|---|
| *(absent)* | `ESADout_CUGoodsShipment` — the container wrapping the entire shipment |
| `ESADout_CUFinancialResponsiblePerson` | `ESADout_CUFinancialAdjustingResponsiblePerson` |
| `ESADout_CUFillingPerson` | `FilledPerson`, at root level, children `PersonSurname` + `PersonName` |
| `CustomsOfficeCode` | `CustomsOffice` |
| `CustomsZone`, `TransportMeans`, `Contact`, `Phone`, `E_mail`, `BorderCustomsOffice`, `DeliveryPlace`, `DispatchCountry*` and 8 more | appear in **zero** filings |

### 2. The commodity codes verify

2,842 codes across the corpus, **all in the 11-digit filed form**. 99.65% resolve against
our nomenclature. The national 11th digit is `0` on 97.7% and `8` on 2.3% — the
specification says "~98% zero", so that corroborates independently.

The 10 that fail are `39069090090` and `39100000090`, which exist neither in our tree nor
at the authority; the corpus is synthetic, so they are generator artifacts. The existence
gate rejects them correctly. **Consequence for scoring: abstaining on those two is right
and the ground truth will penalise it.**

### 3. Retrieval depth was capping accuracy, and now it is measured

Recall@k on 60 corpus lines, scoped to the correct heading, asking only whether the
expected code is retrieved at all:

| k | 5 | 10 | 15 | 20 | 30 | 50 | 100 |
|---|---|---|---|---|---|---|---|
| recall | 58.3% | **68.3%** | 76.7% | 80.0% | **86.7%** | 96.7% | 100% |

**At k=10 — the value the traversal shipped with — a third of correct codes are never
shown to the model.** Ranks beyond ten run 11, 12, 14, 15, 17, 20, 22, 23, 27, 28, 31 …
76. That is the same shape the specification describes for its recorded 48% → 67% jump,
reproduced here independently, which resolves its open question about whether that gain
came from retrieving more or from restructuring the traversal: **retrieving more is
sufficient to explain it.**

Raised to 30. Fifty buys another ten points of ceiling and is the next thing to measure
once end-to-end scoring runs.

### A caveat on the ground truth itself

On the one line examined closely, the classifier picked `8539213009` (halogen lamps with
tungsten filament, for motor vehicles) where the ground truth says `8539229000` (other
incandescent lamps, not exceeding 200 W). The pick looks *more* defensible than the
label. The corpus is synthetic, so its codes are the generator's choices, not a broker's.
**Scoring against it measures agreement with the generator, not customs correctness** —
worth stating before any accuracy number from it is quoted.

### An architectural constraint discovered by hitting it

**Embedded Qdrant is exclusive-locked to a single process.** A second process opening the
same directory fails outright. The specification assumes concurrent runs bounded at four,
sharing a resident index; with the embedded store that bound is one. Either the runs
serialise on the store, or it moves behind a server. Recorded rather than worked around —
the test here used a filesystem snapshot, which is not a production answer.

---

## Entry 8 — M9 Classification: the layer stack and the Code Assignment graph

`src/deepclare/classification/` and five prompt files. One commodity code per goods line,
or an abstention with a stated reason.

### The stack, which is five lines of code because the order is the design

```
L1  existence gate         wraps everything; does its work on the return
L4  vendor-catalogue code  short-circuits at 0.7, always flagged
--  Code Assignment graph  the per-line traversal, which abstains rather than guessing
```

**There is no L2 and no L3.** The specification's filed-history and legacy-history reuse
layers are absent because customer-history reuse was removed from this product. The
numbering is kept rather than closed up, so a reader holding the specification can see
that two layers are missing on purpose. Nothing in this package searches anyone's prior
filings; nomenclature search over the ATG collection is the different thing, and it is
what the graph runs on.

### The graph is declared, not wired

`assignment.py` holds every node, every edge and every branch condition in one place;
`nodes.py` holds bodies that take state and return state and never choose what runs next.
It prints without running (`Classifier.graph.describe()`) and every run returns the step
log each node appended to.

Mis-declarations are caught at **construction**: an edge naming a node that does not
exist, a node nothing can reach, a node whose last edge is conditional (a traversal could
arrive with no way out), an edge declared after an unconditional one (it could never be
taken). Four tests assert each refusal.

**The retry guard is structural.** The only cycle is C7 → C1, and C7's whole job is to
clear the printed prefix — the slot the entry branch tests *and* the slot the dead-end
condition tests. A second pass cannot enter the fast path and cannot reach C7 again.
Nothing counts anything. There is a visit budget inside the graph machinery, but it is a
mis-declaration detector that raises naming the cycle; it cannot fire on this declaration.

### Verified end to end against the real models

`tests/check_classification_end_to_end.py` — five fictitious lines, each through
description composition and then classification, with the real reference collection and
real embeddings. Actual output:

| Case | Outcome | Confidence | Review | Path taken |
|---|---|---|---|---|
| `PORTLAND CEMENT CEM I 42.5 N` | `2523290000` | 0.6836 | yes | C1 · C2 · C4 · C5 |
| `TERMINAL BLOCK 4 MM`, invoice prints `8536.90.10.00.00` | `8536901000` | 0.9525 | no | **C0** · C4 · C5 |
| `INDUCTIVE PROXIMITY SENSOR M18` | abstained twice, picked `8536500600` once | 0.0 / 0.6986 | yes | C1 · C2 · C4 · C5 |
| `CLOTHES HANGERS, 42 CM` | abstained, material split | 0.0 | yes | C1 · C2 · C4 · C5 |
| `PE BAG 50X80`, catalogue prints `3923210000` | `3923210000` | 0.7 | yes | **L4**, no model call |

The abstentions are the interesting rows and both are actionable rather than blank:

- the hangers, on every run — *"If they are made of wood, the correct code is 4421100000.
  If they are made of plastic, they would be classified under 3924900009."* Both branches
  named with their codes, which is what turns an abstention into a question an operator
  can answer, plus *"state the material of the clothes hangers"* in its own field;
- the sensor, on two runs of three — *"the subheadings below this level are differentiated
  by operating voltage … the voltage is not specified"*, resolved by *"state the operating
  voltage of the sensor"*. This is the row the specification records as unsolvable from
  the input available.

**On the third run the sensor did not abstain**, and that run is worth more than the two
that did. It picked `8536500600` and justified it with *"electronic switches consisting of
a transistor and a logic chip, which is the typical construction of a modern inductive
sensor"* — a construction detail no document states, reasoned from what such a product
usually contains. That is the confident-wrong-code shape exactly. The composite confidence
came out at **0.6986**, four thousandths under the gate, so the line was flagged. The gate
caught it; nothing else would have.

The fast path fired on the printed code, skipped both narrowing calls, and retrieved four
candidates from the 6-digit subtree — one model call for the whole line.

The cement line is the one to look at twice: the pick is right and the composite
confidence is **0.6836**, just under the gate, so it is flagged. Five sibling cement codes
retrieved at 0.673–0.695 with nothing separating them; that is what a genuinely close list
does to the similarity term, and flagging it is the correct outcome.

52 deterministic tests were added, none touching the network: code normalisation, the
confidence blend and both halves of the review gate, the retrieval contract (dedupe by
code keeping max similarity, descending order, no threshold, the scope applied inside the
store as a payload-prefix filter), the existence gate's five rejection shapes, the
vendor-catalogue layer, and the whole graph — including the dead-end retry and the fact
that a second dead end terminates. Full suite: 372 passed.

### Decisions taken where the specification was silent, or where it contradicted itself

| # | Decision | Reasoning |
|---|---|---|
| D-20 | M9 emits `needs_review: bool` and a rationale, never a `ReviewItem` | File 10 §3 M9 says this module must not know the review vocabulary; file 03 §3.2 lists the flag as a classification output. Assembly builds the item from the flag, the rationale and the new `resolving_evidence` field |
| D-21 | The abstention's remedy is its **own field**, not a sentence inside the rationale | 02 §10.3 records "what evidence would resolve it" as the highest-value affordance in the product. A field can be rendered as an instruction; a sentence buried in prose cannot |
| D-22 | `subheading_menu` was added to M4, derived from the leaves' own ancestry | The tree publishes no 6-digit nodes, but every leaf's ancestry passes through one. 1,798 recoverable. M4's stated output already includes subheading menus, so computing it in M9 would have crossed a boundary |
| D-23 | The retrieval scope ladder widens when a rung retrieves nothing, not only at the 6-digit rung | The specification names one such fallback by hand. The same reasoning holds at every rung and widening only ever *adds* candidates, so nothing can be lost by generalising it |
| D-24 | The "terminal check" of 02 §6.2 is a named predicate on two edges, not a node | A node that returns its input unchanged looks exactly like a stub. The predicate is referenced twice and printed identically in both edges |
| D-25 | The verifier's recorded self-contradiction is dissolved structurally | Its prompt and its output schema instruct opposite behaviour on "unsure" in the system described. Here schemas carry no prose at all, so the doctrine has exactly one home. The doctrine chosen: uncertainty about the *category* rejects, uncertainty about the *last digits* does not |
| D-26 | C5 and C6 are given the line **without** the language tag and the sibling summary | 02 §4.3 records the asymmetry as measured; the specification's own reproduced prompt hedges with "when the goods line carries…". Withholding is the version backed by a measurement, and a rule backed by omission cannot be broken |
| D-27 | The review gate ships with **both** halves — confidence < 0.7 **or** heading agreement < 0.5 | 02 §4.3 states the gate as both and records both as inert. Enabling only the first would leave the heading constant dead, which is the state it says to fix. It only ever adds flags |
| D-28 | Subheading preference and verification default **off**; the printed-code fast path defaults **on** | The first two are the specification's shipped defaults and neither has been measured here; the verifier's recorded record is 1 good veto to 4 costly at the widest configuration. The fast path is measured 9/9 |
| D-29 | An 11-digit code reaching the gate is reduced to its leaf with a recorded transform, and flagged when the national digit is not `0` | 07 §5.7: the "append 0" rule is wrong for a small number of real codes. Silently dropping a non-zero suffix and appending `0` downstream would file a different code than the one supplied |
| D-30 | A blank rationale from the code pick raises rather than being filled in | An abstention whose reason is blank tells the operator nothing and a stand-in reason is exactly the placeholder data the build rules forbid. There is no retry |

### Where this is weakest

- **Nothing here is measured for accuracy.** Five lines is a demonstration, not an
  evaluation. The specification's own ceiling is roughly 64% precision at the full code
  and it records the deployed flow measuring *worse* than a simpler undeployed one, with
  the cause never isolated. Treat every default in `features.py` as a starting point.
- **The deterministic query is weak in exactly the case that uses it most.** On the fast
  path there is no model-written query at all, so retrieval embeds
  `<chapter title> — <heading title> — <the invoice's printed name>`. For chapter 85 the
  chapter title alone is ~200 characters of boilerplate that every candidate in scope
  shares, and the discriminating part is one short phrase at the end. It works because the
  6-digit scope is tiny — but with a foreign-language invoice name it would be a foreign
  phrase against an English index, which is the 0.63 regime.
- **Two shortlisted headings share one top-k.** Retrieval runs one search over both, so a
  heading with many leaves can consume the whole budget and the second heading never
  reaches the pick. Raising k to 30 makes this much less likely and does not remove it.
  Retrieving per heading and merging would, and is a change to the specified retrieval
  strategy rather than an implementation detail.
- **The subheading menu is incomplete by construction.** It exists only where the
  authority publishes an intermediate 6-digit node; a leaf sitting directly under its
  heading contributes none. Costs a hint and never a code, since the preference cannot
  filter — and the feature is off by default.
- **`llm_confidence` came back as 0.95 on every single pick.** Three different lines,
  three different degrees of genuine difficulty, one number. The self-report is 0.3 of the
  composite and on this evidence it is carrying no information at all. That is a
  calibration problem in the prompt, and it is the first thing to look at if the gate ever
  fires in the wrong direction.
- **The same input does not give the same answer twice.** Every decoding parameter is
  pinned — temperature 0, top-p 1, top-k 1, a fixed seed — and the sensor line still
  abstained on two runs and picked on a third. Reasoning models are not reproducible from
  decoding settings alone. Two consequences: no single run of the check script is
  evidence, and any evaluation of this stage has to report a distribution rather than a
  number.

---

## Entry 9 — M14 Run Orchestration and the CLI: the pipeline runs end to end

Everything else existed as a module. This is the entry where it becomes a product: one
command, two documents in, a declaration and a review report out.

### What was built

`src/deepclare/run/`, seven modules, and the shape is the argument:

| Module | What it is |
|---|---|
| `state` | `RunInput`, `RunOptions`, `RunState` — the slots of dossier 02 §5.1 as one frozen typed object |
| `ports` | Every capability as a protocol, injected. Six of them; four optional, and `None` is a declared branch |
| `conditions` | Dossier 02 §6.1 as code: one named predicate per branch, with the specification's own wording beside it |
| `stages` | The nodes, each a function of the state before it |
| `pipeline` | The chain, and `describe_chain()`, which prints the whole topology without running it |
| `reporting` | The assembled declaration presented to M13 as values keyed by domain concept |
| `summary` | A24 — the run's account of itself |
| `wiring` | The composition root. Not part of the chain |

The outer chain is sequential code, which is what dossier 02 §12 recommends and for the
reason it gives: the only genuine graph in this system — conditional entry, a bounded
loop, a structural guard — is the per-line Code Assignment traversal, and that is already
declared as a graph inside `deepclare.classification`. The outer chain has no cycle, no
fan-out and no join. What a framework would have given it is exactly what was kept anyway:
every node named, every conditional edge declared, and the topology printable.

```
python -m deepclare run --show-chain
  1. intake  [A1+A2]
  2. rasterize  [A3]                runs only when: the invoice's format carries pages
  3. classify pages  [A4]           runs only when: a page-type classifier port was injected
  4. group pages  [A5]
  5. read documents  [A6]           branches on: at least one page grouped as a consignment note
  6. goods gate  [A12]
  7. enrich evidence  [A14]         branches on: an evidence enricher is configured
  8. build line contexts  [A15]
  9. write descriptions  [A17]
 10. classify lines  [A18]
 11. completeness guard  [A19]
 12. assemble lines  [A20]
 13. reconcile lines  [A21+A22]     branches on: a cross-line reconciler port was injected
 14. assemble declaration  [A23]
 15. write filing  [A23]
 16. build review report  [A24]
```

A13 (prior-filing matcher) and A16 (foreign-text reuse probe) are absent, and there is no
port for either. Customer-history reuse was removed from this product; a node that is not
there cannot be switched on by configuration.

The CLI now has three commands. `run` writes `declaration.xml` and `review.txt` to `--out`
and prints the summary; `build-index` embeds every filable code into the vector
collection; `build-reference` is unchanged. The stale `NotImplementedError` claiming
classification and filing were missing is gone.

### Verified end to end, once, against the real models

`tests/make_synthetic_invoice.py` now writes both a fictitious invoice and its matching
CMR. One billed run of the real CLI over both:

```
$ python -m deepclare run /tmp/invoice_synthetic.pdf \
      --consignment-note /tmp/cmr_synthetic.pdf --out out

running intake (A1+A2) · rasterize (A3) · classify pages (A4) · group pages (A5)
running read documents (A6) · goods gate (A12) · enrich evidence (A14)
running build line contexts (A15) · write descriptions (A17) · classify lines (A18)
running completeness guard (A19) · assemble lines (A20) · reconcile lines (A21+A22)
running assemble declaration (A23) · write filing (A23) · build review report (A24)

goods lines          3
codes assigned       3
codes abstained      0
conforms / filable   True / True

review items         32
  placeholder    0
  omitted        19
  needs_review   3
  guess          10

codes flagged for confirmation   lines 3

what the run did
  enrich evidence: skipped — no supporting document was grouped
  cross-line consistency: nothing_to_do — the critic found no inconsistency between the
  lines, so no rewrite was requested.
```

Sixteen model calls: one page classification, two vision reads, three descriptions, three
retrievals and three code picks, one consistency critique. The four-line invoice carries a
freight row; three goods lines came back, which is the row correctly excluded.

The filed document:

```xml
<catESAD_cu:TotalGoodsNumber>3</catESAD_cu:TotalGoodsNumber>
<catESAD_cu:TotalPackageNumber>114</catESAD_cu:TotalPackageNumber>
...
<catESAD_cu:GoodsNumeric>1</catESAD_cu:GoodsNumeric>
<catESAD_cu:GoodsDescription>ՊԼԱՍՏՄԱՍՍԱՅԵ ՏՈՒՓ, ՆԱԽԱՏԵՍՎԱԾ Է ՊԱՀՊԱՆՄԱՆ ՀԱՄԱՐ, ԿԱՊՈՒՅՏ,
  40*60ՍՄ</catESAD_cu:GoodsDescription>
<catESAD_cu:GoodsTNVEDCode>39231000000</catESAD_cu:GoodsTNVEDCode>
...
<catESAD_cu:GoodsTNVEDCode>39233010900</catESAD_cu:GoodsTNVEDCode>
<catESAD_cu:GoodsTNVEDCode>63053390000</catESAD_cu:GoodsTNVEDCode>
```

The third line is the run's best moment and is worth reading. The invoice prints
`3923210000` — a plastics code — against "PP woven sack 50 kg". The classifier declined
the printed code and filed 6305.33 instead, with the reason:

> *"articles made of woven plastic strips are classified as textile articles in Section
> XI, not as plastic articles in Chapter 39. Heading 6305 covers sacks for packing goods.
> Subheading 6305.33 specifically covers those made from polypropylene strips."*

Composite confidence 0.67, under the 0.7 gate, so the line is flagged for confirmation.
That is the product's whole thesis in one line: a defensible legal argument against the
document's own code, filed, and handed to a human to confirm rather than asserted.

Two other findings worth naming, both of which the run surfaced rather than hid:

* **line 1, net above gross.** The invoice prints 624 kg net; the consignment note's
  1890 kg distributed by quantity share gives 135.81 kg gross. Both were filed as printed
  and the impossibility raised as a `needs review` naming both figures.
* **`NORWAY` resolves to nothing.** The curated country table holds 22 countries — the
  corpus's own set — and Norway is not among them, so box 34 and box 16 were omitted with
  an item saying so. Filing a name without its code is the contract's quietest failure, so
  omitting the pair is correct; the table is simply narrower than the world.

Offline, `tests/test_run_pipeline.py` runs the whole chain with fake ports satisfying the
same protocols the real adapters do — which is only possible because nothing in the chain
reaches for a provider. 13 tests: the chain end to end, both skip branches, a
reconciliation change reaching the filed XML through the value's transform chain, a failed
critique leaving a filable declaration, and four shapes of broken per-line contract.

### One real defect found by running it

`assembly._total_packages` summed `item.package_quantity`, a field `GoodsItem` does not
have. It had never fired: no test had run assembly over a full set of lines and reached
the shipment total. Fixed in its own commit.

### Decisions taken where the specification was silent, or where the code disagreed with it

| # | Decision | Reasoning |
|---|---|---|
| D-31 | Cross-line consistency reconciles the **naming** text, before assembly appends the deterministic size and quantity segments | M10 is specified to receive the fully assembled filed string, with the segments named so a guardrail can check they came back verbatim. In this build the segments are composed inside `assembly.assemble_line` and do not exist yet at that point. Feeding the reconciler the assembled string would mean assembling twice and then re-appending the segments to text that already contains them. Reconciling the naming text instead achieves the guardrail's purpose structurally: a segment never shown to the model cannot be dropped by it — the same omission-over-prohibition argument the rest of the system runs on |
| D-32 | A consistency change is applied as a **`Transform` on the existing value's chain**, never as a new value | M10 hands back a `Transform` per change precisely so the caller can append it. It also settles a question with no honest answer: a re-coded line would otherwise need a fresh provenance and a fresh derivation confidence, and this pass makes no measurement to put in one. The value keeps the account its producer attached and gains one more link, and the line is flagged |
| D-33 | The description half of the completeness guard runs at `write_descriptions`, not at A19 | `build_classification_lines` already refuses a line with no description, so a guard placed after classification could never fire on that collection — unreachable code dressed as a contract. Checked where the batch is produced, it names the stage that broke the promise. A19 keeps the classifications, which is its subject in §5.1 |
| D-34 | No page classifier configured is a **skip**, not a separate direct-read path | §6.1 has A2 → A6 bypass segmentation entirely when no classifier is configured. But with no verdicts the grouper's own rule — no verdict leaves a page on its file's role — produces exactly that direct read. One code path, one over-inclusion policy, and no configuration that can route around it |
| D-35 | Supporting documents accepted and not read raise a shipment-level review item | The evidence enricher (A14) has no implementation in this build. §6.1 says the stage is skipped; it does not say the operator is told. Dossier 02 §1 says every uncertainty becomes a review item, and "your catalogue was not consulted and the codes were drafted without it" is exactly one |
| D-36 | The workbook invoice is a **separate port**, not a method on the document reader | Its input is a routed file rather than a page group, and its reader needs a model and a prompt directory the chain must not know about. Binding those is what a composition root is for. A run whose invoice is a workbook and which was handed no workbook reader stops naming what is missing |
| D-37 | `reference_tables_dir` is a settings field, not a constant | The curated tables are read from a directory and a path is environment-specific. Build rule 5 admits no exception for a path that happens to be tracked in git |
| D-38 | The run's output is the `RunState` itself, not a narrower result object | Every slot on it was written by a named stage and the summary reads them. A second, smaller result type would either duplicate those fields or hide the ones a caller turns out to need |

### Where this is weakest

- **The review report double-reports about a dozen concepts.** Assembly says "no country
  could be read from the seller's address" and the filing adapter says "so the consignor
  address was left out entirely"; both are keyed to `consignor country` and both appear.
  19 omitted items cover roughly ten distinct facts. They are genuinely different
  statements — the cause and its consequence — and M13 is specified never to drop an item,
  so nothing here deduplicates them. But a first-time reader counts twenty problems where
  there are ten, and the right fix is probably for the two modules to agree which of them
  reports an omission rather than for the surface to guess.
- **Concept vocabularies have drifted between modules.** Assembly raises
  `line goods description`; consistency raises `goods description`. `total packages`
  against `shipment package total`. The report joins an item to its value on the concept
  name, so a mismatch silently costs the join and the operator reads the finding and the
  value in two places. `reporting.py` picks the assembly spelling wherever the two
  disagree, which papers over it rather than fixing it. A single shared concept vocabulary
  is the actual fix and is a change across four modules.
- **The declarant profile is not reachable from the CLI.** Every run therefore omits the
  goods location, the filler and the importer fallback, and raises five review items about
  it. That is correct behaviour and it is also five items of noise on every single run.
  There is no `--profile` flag because nothing has decided what the profile file looks
  like.
- **The workbook path's own diagnostics are dropped.** M6's spreadsheet reader reports
  which numeric columns would not parse and whether column labelling failed; the port
  returns only the record and logs the rest. Those belong in the review report and are not
  there.
- **Nothing measures whether a run is *good*.** One synthetic shipment proves the chain
  connects. It is not evidence about accuracy, and the classification entry's warning
  applies here with more force: the same input does not give the same answer twice, so a
  single run of the CLI is a demonstration and never a measurement.
- **The chain has no resume and no checkpoint.** Dossier 02 §9 describes both. A run that
  fails on line 40 of 60 has spent forty description calls and forty traversals and keeps
  none of them. For a 554-line filing — which the corpus contains — that is the difference
  between an expensive retry and an unusable one.

---

## Entry 10 — The evaluation harness: a scorecard with the run's identity attached to it

`src/deepclare/evaluation/` and `python -m deepclare.evaluation`. A corpus directory in, a
scorecard out, with everything the number depends on printed above the number.

### What it is, and what it deliberately is not

**It does not score.** `evalkit/` is a finished, stdlib-only scorer with its own interface
and it is used in full — line alignment, chrF, the attribute rubric, the hierarchical code
comparison, the numeric tolerance. A second implementation of any of those here would be a
second opinion about what "correct" means and the two would drift. Nothing in `evalkit/`
was modified; it is bound onto the import path from a directory derived from the corpus
the caller named, and it is not installed, so no build artifact lands in a directory this
build does not own.

**It does not produce declarations.** How a case becomes XML is a **parameter** — a
callable taking the case's input paths and returning declaration XML. One producer ships:
read a file the case already holds. Pointed at `ground_truth.xml` that is the harness's own
self-check; pointed at `declaration.xml` it scores whatever a previous run wrote. The run
graph plugs in as a third-party callable and the harness learns nothing about it.

**It does not report a number without its identity.** Model ids per tier, every decoding
parameter, every prompt's declared version *and* the sha256 of its bytes, the nomenclature
vintage, the embedding model and width, retrieval depth, every classifier feature flag, the
scorer's own thresholds, and the git build with a dirty marker. All of it prints before the
first metric.

### What it reports

Per case and in aggregate: goods-line alignment precision / recall / F1; commodity-code
agreement **at 2, 4, 6, 8 and 10 digits** rather than pass/fail, plus exact match, mean
agreeing prefix length, and coverage; numeric exactness per field (quantity, net weight,
gross weight, invoiced cost, package count); and description chrF, token F1, exact rate and
the four rubric checks each over the lines where it had something to assert. `--cases N`
scores a subset, because 71 full pipeline runs is a lot of tokens and the common use is a
quick read.

Agreement is reported by depth because *where* two codes diverge says which stage broke: a
wrong chapter is a narrowing failure, a right chapter with a wrong heading is the failure
the specification names as unrecoverable, and agreement to eight digits with a wrong tail is
a different and much cheaper problem. One rate cannot tell those apart.

### The two accounting decisions that keep the number honest

**The roll-up is line-weighted.** Cases in this corpus run from 4 goods lines to 554, so a
mean of per-case accuracies is a mean over cases and says almost nothing about lines. The
case-weighted figure is printed beside it, because a metric that moves in one and not the
other is telling you which cases changed.

**Ten lines are held out and reported separately.** Two codes in the corpus — `39069090090`
and `39100000090` — exist in neither our nomenclature nor the authority. Verified again
here against the artifact: of the corpus's **316 distinct codes, exactly those two** fail to
resolve to a leaf, over **10 of 2,842 goods lines**. The existence gate refuses a code that
is not in the tree, so on those lines abstaining is the correct behaviour and the corpus
scores it as a miss. Left in the aggregate they depress it silently. The report prints the
attributable figure, the all-labels figure, and an account of the held-out lines: how many
were abstained on (right) and how many were answered anyway.

Coverage is printed with every code figure, and exact agreement is given twice — as
accuracy over all matched lines, and as precision over the lines the system answered.
Selective prediction is the frame this product operates in and an accuracy number without
its coverage is not readable.

### Verified

`python -m deepclare.evaluation evalkit/corpus --from-file ground_truth.xml` — all 71
cases, 2,842 goods lines, each ground truth scored against itself. **Every figure 100%,
every case PASS, 154 seconds.** Anything less than perfect there is a defect in the harness,
not a finding about the product.

That test alone is worthless, because a harness that always returns 1.0 passes it. So
`tests/test_evaluation_harness.py` — 12 tests, no network, no settings, no model —
degrades exactly one thing about the produced declaration and asserts that exactly the
corresponding number moves:

| Degradation | What must move | Measured |
|---|---|---|
| Blank one line's code | coverage and accuracy fall to 13/14; **precision stays 1.00**; alignment untouched | as stated |
| Wrong code sharing the first five digits | agreement at 2 and 4 stays 1.00, at 6 / 8 / 10 falls to 13/14 | as stated |
| Delete one goods block | recall 13/14, **precision stays 1.00** | as stated |
| Add 5 kg to one net weight | `net_weight` 13/14, every other field 14/14 | as stated |
| Abstain on the five impossible labels in `case-031` | attributable bucket n=1 at 100%, all-labels bucket 1/6, held-out account 5 abstained | as stated |
| Producer raises on one case | the case is named with its error, the other case still scores, the run reports itself **not complete** | as stated |

Full suite not run — per the verification discipline, one targeted file.

### Decisions taken where the specification was silent

| # | Decision | Reasoning |
|---|---|---|
| D-39 | Producing a declaration is a parameter, and no pipeline producer ships here | The pipeline was being built in parallel. A harness that imports it cannot be run or verified until it exists, and cannot be pointed at anything else afterwards — including at a stored output from a previous release, which is what a regression run needs |
| D-40 | The roll-up is line-weighted; the case-weighted figure is printed beside it | 4 to 554 lines per case. Neither figure alone is the truth and the gap between them is information |
| D-41 | Lines whose label names a code that does not exist are held out of the headline and accounted for on their own | Abstaining there is the governing asymmetry working correctly. Scoring correct behaviour as a miss makes the number mean something other than what it says, and hiding the exclusion makes it worse |
| D-42 | Code agreement is reported as accuracy **and** precision **and** coverage | A system allowed to decline has no meaningful accuracy without its coverage. The scorer reports one exact-match rate, which counts an abstention as a wrong answer |
| D-43 | `--cases N` is the first N in name order — a prefix, not a sample — and the report says it is biased | Reproducible between runs and cheap to name. A random sample would need a seed pinned in the manifest to be worth as much, and would still be a subset of one family |
| D-44 | A case whose producer raises is recorded and the run continues, but the run is never *complete* | On a corpus where each case is a full pipeline run, losing seventy results to the seventy-first is worse than reporting seventy with the seventy-first named. Recorded, listed with its error, and it blocks the completeness flag and the exit code — which is not the same as swallowed |
| D-45 | The scorer is bound onto the import path, never installed | It carries no dependencies and is copied rather than released; installing it writes build artifacts into a directory this build does not own. The path is derived from the corpus directory the caller already gave, so no path is written into the code |
| D-46 | Two small additive functions elsewhere: `prompting.prompt_identities` and `reference.store.artifact_vintage` | The manifest needs every prompt's version and content hash, and the prompt loader is the only thing allowed to read that directory. It needs the nomenclature vintage, and the store carries it but demands a Qdrant client to construct — and the embedded store is exclusive-locked to one process, so a report that only needs to *pin* the data must not take that lock away from a run |

### Where this is weakest

- **Every number in the verified report is 1.0 because the input was the truth.** The
  harness is proven to measure correctly and has measured nothing about the product. The
  first real number arrives when a pipeline producer is wired in, and per the classification
  entry's warning it has to be a distribution over runs rather than a single figure.
- **No intervals.** The specification requires a 95% interval on every proportion and a
  denominator on every number. The denominators are all there; the intervals are not. Two
  runs whose figures differ by two points currently cannot be told apart.
- **No baseline, so no regression view.** There is nothing to diff against, no item-level
  churn (`fixed` / `broken`), and no attribution verdict. The manifest is the half of §14
  that makes those possible; the comparison itself is not built.
- **No slices.** The specification calls an aggregate without its slices unreportable —
  by chapter, by input channel, by script, by whether the document printed its own code. The
  per-line detail needed to compute them is in the JSON output; nothing computes them.
- **No cost, no latency, no abstention split.** `justified` versus `costly` abstention is
  the metric that says whether declining is working, and it needs a judgement the corpus
  labels cannot supply on their own.
- **Alignment is quadratic in goods lines.** 154 seconds for the corpus, most of it in the
  554-line case, because matching computes chrF for every produced line against every
  labelled line. That is the scorer's, and it is why `--cases N` exists.
- **A pre-emitted file cannot be attributed.** The manifest prints the configuration in
  force while scoring and says, in the report, that it does not describe whatever wrote the
  file. Closing that needs the producing run to write its own manifest beside its XML.

---

## Entry 11 — M17 Trace: the observation layer

`src/deepclare/trace/`. Run identifiers, per-node capture, structured per-stage records,
and the pinned versions that explain a result. It depends on the domain vocabulary, the
model-call account the model adapter already returns, and the candidate shape the
reference store already returns — and on no producing module, which is what the
dependency table says. **Nothing else was touched**, and nothing was wired: the seam is
provided, the orchestrator connects it.

### Read-only, enforced structurally rather than promised

The module decomposition's rule for M17 is that it must not know how to change
behaviour. Two facts hold it, and neither is a comment asking for it:

- **Every method a run calls returns `None`.** `stage()` yields nothing; `node()` yields a
  draft with setters and no getters. There is no value a run could branch on, so no branch
  can depend on tracing being on. A prohibition backed by omission cannot be violated.
- **The recorder never reaches back.** It holds no port, imports no stage, calls no
  module. What to record is the caller's decision.

A mis-wired call — a node recorded outside any stage — is refused at *every* capture
level including `off`, because a defect that appears only when tracing is turned up is a
behaviour that varies on tracing.

### The seven pinned axes, and the rule they exist for

`RunManifest`: data (nomenclature vintage, index build, embedding model and width,
canonical text-structure version, code-list versions), models (id, served version and
decoding per stage), prompts (name, version, optional content hash), configuration (every
threshold and flag, plus capture volume), code, environment, evaluation. `compare_manifests`
applies the attribution rule: one axis apart is attributable, two or more is a **compound
change** and no single cause may be claimed. The run identifier is deliberately *not* an
axis, or two runs of the same build could never compare as identical.

`RunTrace.pin_drift()` is the check the manifest alone cannot give: the manifest is a
claim and the calls are the evidence. A model that answered for a stage the manifest pins
differently, or a prompt version that was rendered and is not pinned, is named.

An axis nothing in this build publishes carries `UNPINNED` and appears in
`manifest.unpinned()`. Two runs agreeing on an axis neither of them pinned have
established nothing, and the printed report says so.

### Capture volume is four levels, and redaction is not one of them

`off` → `records` (what happened: node, decision, outcome, model call, tokens, timing,
candidates with scores — **no document content**) → `states` (entry and exit state) →
`payloads` (full prompt and full response). A truncation cap that can be set to `None`,
and a sampling rate that is deterministic in the run id and sequence number so a second
reading of a trace agrees with the first. Sampling drops *content*, never the node record:
one durable record per node traversal is the specification's ask, and a sampled-away
record is a hole in the run's account of itself.

Redaction has no off switch at any level. It is driven by the domain's own field names —
`name`, `address`, `tax_code`, `surname`, `phone`, `email`, `iban` — and by the identity
strings `identities_in()` harvests out of a record the run produced, which is what makes a
*rendered prompt* safe, since a prompt is one long string with no field names left in it.
A pattern backstop catches emails, IBANs and international phone numbers no field named.
It deliberately does **not** scrub long digit runs: a commodity code is eleven digits, and
a trace that masks commodity codes cannot explain a classification.

### Retention: no function that could violate the invariant

There is no `delete`, no `prune`, no `expire`, no window that anything enforces.
`RetentionPolicy` is a declaration that gets recorded and printed. `ArtifactStore` refuses
to overwrite a retained artifact, because writing over one is a deletion under another
name. The JSONL sink opens `"a"` and only ever `"a"` — the measured precedent deleted its
trace file at the start of every run.

### Verified

`tests/check_trace_report.py` builds a two-line run through the recorder exactly as an
orchestrator would — a printed-code fast path that dead-ends and has its prefix cleared by
the reset node, a material-split abstention, two degradations, nine model calls — and
prints it. Actual output, abridged:

```
  UNPINNED (7) — a comparison establishes nothing about these:
    - code.build_identifier
    - prompts[pick_code].content_hash                      … and five more
  capture payloads, cut at 240 chars, sampling 1.00, redaction always on
  retention indefinite, declared by check_trace_report.py; deletion is by explicit
  human action only — no code path here removes an artifact or a trace

    #9    C4 retrieve              line 1    abstained     0.0 ms
           decision   : the 6-digit scope 853690 retrieved nothing at any widening rung
           abstention : no_candidates
    #10   C7 reset                 line 1    completed     0.0 ms
           superseded : printed_prefix held '853690' — dead end; cleared so the entry
                        branch cannot retake the fast path
    #13   C4 retrieve              line 1    completed     0.0 ms  attempt 2
           retrieval  : 4 candidate(s), scope p4 in (8536, 8535)
                      *   1. 8536901000  0.8412
                          2. 8536909000  0.7788
    #17   C5 pick code             line 2    abstained     0.0 ms
           abstention : none_chosen

  identity strings this run handled : 6
  identity strings still in the trace: 0  ()
  and in the trace file on disk     : 0

  model swap only        : single-axis change: models
  model swap + new tree  : COMPOUND CHANGE across data, models — no single cause may be claimed
  same build twice       : manifests are identical on all seven axes
```

`tests/test_trace_observation.py` — 35 deterministic tests, no network: the return-`None`
contract, a failing node recorded with the exception still propagating, both abstention
kinds staying distinct, the superseded slot surviving the loop guard, each capture level's
exact contents, truncation and its disabling, sampling determinism, the redaction proof
(the fixture is asserted to leak *before* it is masked, so the check has teeth), the
manifest's unpinned list, all three attribution verdicts, pin drift, the append-only sink
across two runs, and the artifact store's refusal to overwrite.

### Decisions taken where the specification was silent

| # | Decision | Reasoning |
|---|---|---|
| D-31 | Four capture levels rather than the specification's two (`records` / debug) | It names node records and payload capture as separate concerns but gives one dial. Entry and exit state is document content and belongs between them, so a run can account for every node without storing an invoice |
| D-32 | Sampling governs states and payloads, never the node record | §16.3's sampling sentence sits under *input and output capture*; §16.2 asks for one durable record per traversal. Sampling away a record would make the two contradict |
| D-33 | The redactor is *given* the identity strings, harvested from the records by field name | A pattern scrubber alone cannot find a company name, and a field mask alone cannot help a rendered prompt. The domain model already says which fields are identity, so the field semantics are the mask |
| D-34 | A bare `name` is always masked, including country and customs-office names | Over-masking costs nothing recoverable here: in this domain every non-identity name travels beside its code, and codes are never masked. Under-masking is the consequential error |
| D-35 | Long digit runs are not scrubbed | An eleven-digit commodity code would be masked and the trace would stop explaining the thing it exists to explain. Tax codes are removed by value, from the field that declared itself one |
| D-36 | The run identifier and start time are excluded from the axis fingerprints | They differ by construction, so including them makes every comparison a compound change |
| D-37 | `UNPINNED` is a declared sentinel, listed by `unpinned()`, never a fabricated version | An invented version string makes two different runs look identical, which is worse than a run that admits what it could not pin |
| D-38 | A sink write failure raises rather than being swallowed | It does mean an infrastructure failure can surface with tracing on that would not with it off. The values a run produces are unaffected either way, and a trace that silently did not record is the failure §16.2 exists to prevent |
| D-39 | The recorder's node context manager measures wall clock itself | The alternative is every caller timing its own node, which is the shape that produces a pipeline with no latency numbers — and §15.2 records that no latency measurement of any kind survives in the evidence base |

### Where this is weakest

- **A name learned late is not masked retroactively.** `learn_identities` extends the
  redactor; nothing rewrites a record already written. Anything captured before the invoice
  has been read is masked by field name and by pattern only. There is a test asserting
  exactly this, so the limit is stated rather than discovered.
- **Prompt content hashes are unpinned.** `PromptPin.content_hash` is optional and every
  prompt is currently listed as unpinned, because nothing outside the prompt loader reads
  the prompt directory. `deepclare.prompting.prompt_identities`, added concurrently by the
  evaluation work, is the natural source; wiring it is the composition root's job.
- **`canonical_text_structure_version` has no publisher.** Nothing in the reference
  artifact carries one — Entry 3 already raised that the artifact needs a version identity
  a consumer can check, not just a build timestamp. Until it does, this axis is whatever
  the composition root types, which is exactly the drift the pin is meant to prevent.
- **Two `RunManifest` types now exist.** `deepclare.trace.manifest.RunManifest` (seven
  axes, per run, with the attribution rule) and `deepclare.evaluation.manifest.RunManifest`
  (built concurrently, filled from settings and artifacts for a scoring run). They overlap
  substantially and were written in parallel against the same specification section.
  Reconciling them is an architectural decision and has not been taken.
- **Nothing computes a metric.** Golden sets, metric definitions, the judge harness and
  the published report are not in this package and have no stub here that looks as though
  they are. This is the layer they would be computed from.

---

## Entry 12 — The spreadsheet reading path (A7–A11): the only route carrying Armenian goods text

`src/deepclare/reading/workbook.py`, `table.py`, `columns.py`, `spreadsheet.py`, plus
`prompts/read_workbook_invoice.md` and `prompts/label_columns.md`. A workbook invoice now
reads end to end; before this the entry point raised `NotImplementedError` naming itself.

This channel matters more than its size. It is the **only** input route that carries
Armenian-language goods text, and it had no recorded extraction evidence at all.

### The shape, and why it is three nodes and not one

```
A7  buffer the workbook     one forward-only streaming pass; the only read there will be
A8  whole-text read         header fields, always, whatever A9–A11 do
A9  locate the goods table  structural, language-blind, no model
A10 label the columns       one label per column, never a value
A11 read the typed cells    deterministic, by column index
```

**A10 is the whole design.** Asking one model to transcribe every numeric value across a
goods table reliably drops one of two adjacent similar fields — gross weight beside net
weight — regardless of prompt wording, because the source column order does not match the
schema's field order. The fix is structural: the model emits one label per column out of a
closed set of eighteen, and code reads the cells by index. The answer space is bounded by
the table's own width, so a figure cannot be lost by a binding that never touches it.

**A9 reads no word of any language.** Its primary signal is a run of ≥2 consecutive
buffered rows whose first cell counts 1, 2, 3… — the invoice's own numbering. A preamble
is skipped because no preamble row begins the count, and a totals row is excluded because
it does not continue it. Both fall out of the shape rather than being special-cased. The
fallback is the highest-scoring header-like row (cells that are strings of stripped length
in `(0, 40)`, ≥3 needed to score at all), earliest row winning a tie.

### Verified against the real models, once

`tests/make_synthetic_workbook.py` generates a fictitious workbook carrying every hazard
the path exists for: a seven-row preamble, the table starting at row 9, **Armenian column
headers**, gross weight beside net weight in that order, a `Կոդ` column of seller article
numbers next to a real `ԱՏԳ ԱԱ ԿՈԴ` column, a quantity cell holding the words `շուրջ 500`,
a row with no description, a freight row inside the table, a totals row below it, a second
sheet with no table, and a declared used range inflated by hand to `A1:BZ50000`.
`tests/check_workbook_reading.py` runs it. Actual output:

```
=== A9 / A10 PER SHEET ===
Invoice               : located by numbered_run, 6 data row(s), 11 columns, 4 goods line(s)
  no description      : (13,)
  service rows        : (15,)
    column  0 -> printed_line_number      column  6 -> gross_weight
    column  1 -> description              column  7 -> net_weight
    column  3 -> printed_customs_code     column  8 -> unit_price
    column  4 -> quantity                 column  9 -> total_price
    column  5 -> unit                     column 10 -> origin_country
  not bound           : [2]
Notes                 : no goods table; contributes nothing

=== A8 HEADER ===
invoice_number        : MPS-2026-0417        incoterms_code : FCA
invoice_date          : 2026-03-12           incoterms_place: Mersin
currency              : EUR                  total_amount   : None
seller                : MERSIN PLASTIK SANAYI A.S.
buyer                 : ԱՐԱՐԱՏ ՓԱԹԵԹԱՎՈՐՈՒՄ ՍՊԸ
service charges       : [('ՓՈԽԱԴՐՄԱՆ ԾԱԽՍ / FREIGHT MERSIN-YEREVAN', 620.0)]

=== GOODS LINES (typed_cells) ===
  line 1: ՊՈԼԻԷԹԻԼԵՆԱՅԻՆ ՊԱՐԿ 50X80 ՍՄ
      printed_line_number 1   quantity 12000   unit հատ
      gross_weight 318.5      net_weight 300   unit_price 0.042
      total_price 504         origin_country TR
      printed_customs_code 3923210000
  line 2: ՊՈԼԻՊՐՈՊԻԼԵՆԱՅԻՆ ՊԱՐԿ 55X95 ՍՄ
      printed_line_number 2   unit հատ
      gross_weight 92.4       net_weight 88    unit_price 0.115
      total_price 57.5        origin_country TR
      printed_customs_code 3923290000
  line 3: ՍՏՐԵՉ ԹԱՂԱՆԹ 500ՄՄ X 300Մ
      printed_line_number 3   quantity 240     unit ռուլոն
      gross_weight 1104       net_weight 1056  unit_price 8.75
      total_price 2100        origin_country TR
      printed_customs_code 3919109000
  line 4: ԿՈՆՏԵՅՆԵՐԱՅԻՆ ՆԵՐԴԻՐ 20 ՖՈՒՏ
      printed_line_number 5   quantity 60      unit հատ
      gross_weight 471        net_weight 450   unit_price 14.2
      total_price 852         origin_country TR
      printed_customs_code 3923900000

=== WHAT COULD NOT BE READ ===
  sheet 'Invoice' column 4 bound to quantity: 1 cell(s) at row(s) 11 — e.g. 'շուրջ 500'

=== CALLS ===
read_workbook_invoice : gemini-3.5-flash-lite v1, 2784 in / 1575 out
label_columns         : gemini-3.5-flash-lite v1, 1505 in / 156 out
```

Five things in that output are the ones worth checking:

1. **The two weights stayed apart, and in the right order.** Gross at column 6, net at
   column 7, both filed. This is the reproduced bug and it did not fire.
2. **`Կոդ` was not read as a customs code.** Column 2 holds `ART-5080`-style article
   numbers and is the only column the labeller left unbound, while column 3's `ԱՏԳ ԱԱ ԿՈԴ`
   became `printed_customs_code`. The confusion pair in the prompt is doing work.
3. **The whole table is Armenian and the locator never read a word of it.**
4. **`total_amount` came back null**, which is right: the only printed total includes the
   freight row, and the prompt says return null rather than reconcile.
5. **`line 4` carries `printed_line_number 5`** — the invoice's own numbering with the
   description-less row 4 skipped, while `line_id` stays positional. Two different
   identities, both correct.

25 deterministic tests, none touching the network (`tests/test_spreadsheet_reading.py`):
the buffer's blank-row and trailing-blank rules, interior-blank alignment, the empty
workbook, the text rendering, the numeric parser, both location methods, the totals-row
exclusion, the labeller payload's three-row cap and `(blank)` convention, duplicate labels,
out-of-range columns, a failed labelling call, the typed read, the skipped row, the
unreadable cell, the freight row, and provenance.

### The silent-failure path, made loud

07 §1.2 records a cell that will not parse as a number becoming an empty field with **no
error, no warning and no log** — so a text column bound to a numeric field loses every
value it holds, invisibly. Three things changed:

- **It is refused rather than guessed.** `parse_number` handles `1 250,50`, `1.234,56`,
  `1,234.56` and `2 500,75`, and **refuses `1,234`** — 1234 in one convention and 1.234 in
  another, with nothing in the cell to decide. A refusal is visible; a coin-flip is a wrong
  weight on a legal document.
- **It is reported per column, not per cell**, because per column is the shape of the
  failure. `UnreadNumbers` carries the sheet, the 0-based column, the field it was bound
  to, every 1-based row, and up to three distinct example texts.
- **It is logged at warning**, with the same content.

The same treatment covers the rest of what this path decides quietly: duplicate labels
(lowest column index wins), out-of-range columns, unlabelled columns, rows skipped for want
of a description, and the sheets that had no table at all. All of it is on the returned
`WorkbookReading`, typed.

### A defect the live run found, and the fix

The first live run filed the freight row **twice** — once as a goods line and once as a
service charge. A structural pass cannot tell them apart: a freight row inside the goods
table is numbered, priced and shaped like a goods row. The vision path has no such problem
because the model judges each row.

The fix is D-44 below: a data row whose description matches, verbatim, a service charge the
whole-text read returned is left out of the goods and listed in `SheetOutcome.service_rows`.
The match is whitespace-collapsed and case-folded and nothing else, so a row A8 paraphrased
rather than copied stays as goods — the direction that loses no goods.

### What A7's streaming actually buys, measured here

The specification's figure is 25+ s materializing against 0.08 s streaming. That is not
what this library does, and the honest numbers are different in an instructive way. On a
230-row invoice with the declared range inflated to `A1:XFD1048576`:

| | cells visited | time |
|---|---|---|
| streaming, declared range trusted | **3,833,856** | 0.18 s |
| materializing (`read_only=False`) | 1,872 | 0.01 s |
| A7 — streaming **and dimensions discarded** | **1,848** | 0.01 s |

So in openpyxl it is not `read_only` that saves the phantom cells — it is
`reset_dimensions()`, called before a single row is read. Trusting the declared range costs
**2,075× the cells**, and every one of them would become a buffered object that A9, A10 and
A11 then walk. On a second workbook where whole-column formatting had written 600 real but
empty cells per row, the file itself is 328 KB and every reader pays to parse it; A7 still
trims the buffer to the 1,848 cells that hold anything.

### Decisions taken where the specification was silent

| # | Decision | Reasoning |
|---|---|---|
| D-40 | The label vocabulary **is** the goods line's own field names, so there is no translation table | 06 §3.4 requires the vocabulary be a single source of truth shared with the reader that consumes it. Identity is the strongest form of that: a label cannot drift from the field it binds to when they are the same string |
| D-41 | The workbook answer shapes carry **no page and no confidence-of-legibility**; `confidence` grades *identification* | A workbook is not paginated and a sheet is not a page, so a page number would be a value asked for and invented. And the text is the cell, character for character — legibility is not in question. What is uncertain is which cell holds which field, which is the same question the vision path's confidence answers, resting on the one risk this input actually has |
| D-42 | Values read by A11 carry extraction confidence **1.0** | Extraction confidence asks whether the value was read correctly off the source. Here the value *is* the cell, copied by index. The separate risk — a wrongly bound column — belongs to A10 and is reported by this module's notes rather than smuggled into a number that means something else. See the weakness below |
| D-43 | The structural path falls back to A8's guess whenever it yields **no** lines, not only when the labelling call fails | 02 §7.1 names the call failure. The same reasoning holds for a sheet whose mapping has no description column and for a workbook where nothing located: the alternative is a `ReadingError` on an invoice A8 has already read. `goods_source` says which happened |
| D-44 | A row the whole-text read named verbatim as a service charge is excluded from the typed goods | Found by running it. Without this the freight row is filed as goods *and* as the charge meant to explain the gap between the invoice's total and the declared goods value, so the reconciliation the charge exists for cannot close. A8's service rows are kept on the record whatever happens to its goods, so this is the one judgement the typed path defers to |
| D-45 | A date cell renders ISO 8601 | A spreadsheet stores a date as a serial number plus a display format; there is no printed form to preserve, so "verbatim" has no referent. Reconstructing Excel's display from its format code is a subsystem. The convention is stated in the prompt rather than left to be inferred |
| D-46 | A blank cell renders `(blank)` in the labeller's **sample rows** as well as its header | 06 §3.4 records two conventions in one payload as a defect — a blank header rendered `(blank)`, a blank sample cell rendered as nothing. One convention, stated once, and it matches 06 §2.4's rule that absence is written out rather than omitted |
| D-47 | An ambiguous written number is refused, not resolved | `1,234` is 1234 or 1.234 depending on locale. Guessing produces a silently wrong weight; refusing produces a visible note. The governing asymmetry decides it |
| D-48 | `read_workbook_invoice` returns `WorkbookReading`, which *contains* the same `InvoiceReading` the vision path returns | Downstream should not branch on how the invoice arrived, so the invoice shape is identical. Everything only this route can say sits beside it rather than being flattened into a record the vision path would then carry empty |
| D-49 | A labelling failure abandons the structural path for the **whole workbook**, not for the one sheet | A run whose lines came half from typed cells and half from a whole-text guess is two readings of one invoice joined by position, and nothing downstream could tell which line came from which |

### Where this is weakest

- **`read_workbook_invoice` changed signature and the run's call site has not caught up.**
  It now takes `(document, model, prompts_dir)` and returns `WorkbookReading`;
  `run/stages.py:133` still calls it with one argument and assigns the result straight to
  `invoice_reading`. The path makes two model calls and cannot be dependency-free, so the
  old signature was never reachable. The break is a `TypeError` naming both missing
  arguments, at that line. `run/` belongs to another agent and was not touched.
- **Extraction confidence 1.0 on every typed cell is the confident-wrong-value shape.**
  The transcription really is exact, but the review surface ranks weakest-confidence first,
  so a mis-bound column sorts to the *bottom* of what a human checks. The mis-binding
  signal exists — it is in `unread_numbers`, `duplicates` and `unlabelled_columns` — but
  nothing joins it back to the values it taints. Whoever turns these notes into review
  items should.
- **A workbook value cannot say which cell it came from.** `DocumentRegion` counts pages,
  a workbook has none, so provenance carries `region=None`. Sheet and row survive only for
  the cells that could *not* be read. Two optional fields on `DocumentRegion` would fix it
  and that is domain surgery for another module's benefit, so it was not taken.
- **The fallback locator has no totals-row rule.** The numbered run excludes a totals row
  structurally; the header-score fallback takes everything below the header, so a totals
  row carrying a description is filed as a goods line. The specification prescribes nothing
  here and inventing a "looks like a total" test is exactly the language-dependence A9 was
  built to avoid.
- **Two columns labelled the same field lose the second, silently to the model.** The rule
  is the specification's and the loss is recorded, but the case that produced it in the live
  run would be a *mis*-labelling, not a duplicate, and nothing here can tell the operator
  which of the two columns was actually right.
- **One workbook, one run, one model.** The multilingual accuracy of the labeller is
  recorded in the specification as unverifiable except by live-model verification. This is
  one such verification, on one synthetic Armenian invoice. It is evidence that the path
  works; it is not a measurement of how often it does.
- **`tests/test_prompting.py::test_every_shipped_prompt_file_loads` still fails**, on
  `pick_code_shared_path.md` — a prompt added concurrently by other work whose placeholder
  entry is missing from that test's table. The two prompts added here are entered and
  render.
