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
