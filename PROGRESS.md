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
