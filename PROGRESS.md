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
