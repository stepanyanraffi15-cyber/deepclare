# BLOCKED — initial build cannot start

**Date:** 2026-08-08
**Stop condition:** #3 — a specification gap no reasonable reading resolves (and #1
in part: material I cannot obtain).

## The blocker

The build instructions require reading all twelve specification files in
`docs/handoff/` before writing anything, and they bind the implementation to specific
files: the pipeline graph to file 02, the prompt strategy to file 06, the XML
contract to files 03 and 09, and the module boundaries ("must not know about"
statements) to file 10.

Only two of the twelve files exist on this machine:

- `03-FIELD-SEMANTICS.md` — present, read in full
- `11-REFERENCE-DATA.md` — present, read in full

Missing: `00-INDEX.md` and files 01, 02, 04, 05, 06, 07, 08, 09, 10. From
cross-references in the two surviving files, the missing set includes the dossier
index, the AI-architecture/pipeline file, the domain-knowledge file, the prompting
file, the evaluation spec, the XML-contract evidence file, the extension spec, the
module-layout file, and the schema-critique file.

Building without them would mean inventing the module boundaries, the pipeline graph,
and the prompt strategy that the handoff deliberately fixes — exactly the
fake-it-to-get-past case the stop rules forbid.

## Why the files are not in git — and how to transfer them

`docs/handoff/` is matched by the `handoff/` pattern in `.gitignore` (added in commit
1c30205 "Ignore transferred material pending review"), so the handoff files are
untracked and ignored; none has ever been committed. **A git pull or clone will not
deliver the missing files.** They must be copied from wherever the dossier lives
directly into `docs/handoff/`, the same way the two present files arrived.

## Exactly what is needed to unblock

1. The ten missing dossier files copied into `docs/handoff/`, using the same naming
   scheme as the two present files (`00-INDEX.md` … `10-….md`).

## Known upcoming needs — will block again shortly after; bundle if possible

Per `11-REFERENCE-DATA.md` §0.2, the reference-data layer (build step 1) depends on
artifacts that are deliberately untracked and are not on this machine:

- **D2, the EEC SQLite nomenclature database** — the only source of the GIR chapter
  notes; provenance unknown and **not re-derivable**. Highest-value data item.
- The D1 national-nomenclature crawl snapshot (re-crawlable from the public govtech
  API by id-enumeration if absent, so not strictly blocking — but the snapshot saves
  a full crawl).
- The built semantic-index artifacts and vector collection (~140 MB on the
  predecessor's serving host; regenerable only with an embedding API key — the
  deployed build used `gemini-embedding-001` truncated to 768 dimensions).
- Any D6–D10 harvest/curated files that exist as data beyond what file 11
  transcribes, and the customs XSD set (D11) if it is not inside one of the missing
  dossier files' accompanying material.
- `.env` credentials: an embedding-model API key (step 1 index build) and an LLM API
  key for extraction and classification (steps 2–3).

Once the ten files land in `docs/handoff/`, re-run the build loop and it will
proceed from the top of the build order.
