# DeepClare

Import customs declaration drafting for the EAEU / Republic of Armenia. Documents in,
declaration XML plus a review report out. It produces a reviewable draft and never files.

The specification is `docs/handoff/` — twelve numbered files. It is authoritative. Read
the relevant one rather than guessing at a rule you can look up.

## Hard constraints

These are not style preferences. Breaking one is a defect.

**1. Clean-room. Nothing is copied from any prior system.**
A predecessor product exists elsewhere on this machine. Its *data* may migrate; its
source code, tests, evaluations, prompts, file structure and module names may not. Do
not read it, do not copy from it, and do not reconstruct it from memory. Every test and
every evaluation in this repository is written fresh from the specification. If you find
yourself outside this repository looking at code, stop.

**2. No datasets in the repository.**
No nomenclature copy, no customer data, no sample declaration XML. `data/` is gitignored
and holds only what was explicitly supplied: the Qdrant ATG collection and the
nomenclature metadata artifact beside it. Never add to it without being asked.

**3. No customer-history reuse.**
Classification and description writing must not search a customer's prior filings. It
was removed from the design deliberately. Nomenclature search over the ATG collection is
a different thing and is fine.

**4. No silent stubs.**
Anything unimplemented raises `NotImplementedError` naming what is missing. Never return
placeholder data, never swallow an error to keep a pipeline green, never write a
function that looks real and returns a constant. A missing feature is fine; a fake one
is not.

**5. No secrets or environment values in code.**
Everything environment-specific comes from the typed settings object in
`src/deepclare/config.py`, which reads the environment exactly once at startup. No API
key, endpoint, model id or path is hardcoded anywhere else.

**6. Prompts live in `prompts/`, one file per model call.**
No prompt strings in Python — not short ones, not f-strings built at the call site. A
thin loader reads that directory and nothing else touches it.

**7. Architectural decisions are reviewed before they are implemented.**
See `.claude/skills/architecture-review`. Pipeline shape, module boundaries, run-time
data sources, model assignments, anything touching the XML contract, or resolving one of
the specification's `[UNKNOWN]` markers: update the published architecture artifact and
ask, then build.

## Layering

Module boundaries come from specification file 10, whose "must not know about"
statements are load-bearing — a dependency in the wrong direction is a defect. Three
rules generate most of the structure:

- Value production is separate from value expression. **Exactly one module knows the
  filed XML format**, in both directions.
- Domain work is separate from delivery. The run must be executable with no network
  boundary, no authentication, no job store and no persistence present.
- Knowledge is separate from its acquisition.

And a fourth from the pipeline's shape: generative work and deterministic rule
application never share a module.

## The governing asymmetry

*Wrong is worse than missing.* On a legal document a wrong value is a consequential
error while a missing value is work left for a human. This is why the system abstains
rather than guessing a code, never auto-claims a duty preference, and files nothing
rather than fabricating arithmetic. When a design choice is genuinely balanced, this
breaks the tie.

## Environment

Python 3.13, venv at `.venv`. Use `.venv/bin/python` and `.venv/bin/pip`. Dependencies
are pinned in `requirements.txt`. The package is installed editable from `src/`.
