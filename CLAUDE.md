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

Exception, decided 2026-08-09: the public marketing / lead-capture web app (not the
declaration pipeline) may reuse `mootq-ai/services/web/deepclare_web` as its starting
point — code, templates, static assets, and its FastAPI structure may be copied in and
adapted. This exception covers that one prior directory and that one component only. It
does not extend to `src/mootq_agent` or any other predecessor code, and it does not
loosen the rule for the classification/extraction/eval pipeline itself.

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

## Verification discipline

**Do not run the full test suite.** It is large, it is not yet fully trusted, and running
it at every step burns budget that is better spent building. Verify your own change with
**one or two targeted examples** — the specific test file you touched, or a short script
exercising the thing you just wrote — and move on. A full run happens once, at the end,
deliberately.

The same applies to live provider calls. Prove a model-calling path works **once**, with
one representative input, and say so. Re-running it to feel confident costs real money and
tells you nothing new.

Automated checks never call a provider. Where a model is involved, intercept at the HTTP
layer and assert on the request that *would* have been sent. Scripts that genuinely call
the API are named `check_*.py` so pytest never collects them.

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
