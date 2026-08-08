---
name: architecture-review
description: Gate on architectural changes in DeepClare. Use BEFORE writing code for any decision that changes the pipeline shape, module boundaries, data sources, model assignments, or an external contract — update the living architecture artifact, then stop and ask for review. Triggers on adding/removing/reordering a pipeline stage, changing what a module knows, changing where data comes from, swapping a model, or resolving a dossier open question.
---

# Architecture review gate

DeepClare's architecture is a **living artifact**, not a document written once. It is the
thing the user reads to see what is being built and how it wires together. Code that
diverges from it silently is worse than no diagram at all.

## The rule

**An architectural decision is updated in the artifact and reviewed by the user before
any code implementing it is written.** Not after. Not alongside.

Implementing first and documenting after produces a diagram that describes something
nobody agreed to.

## What counts as architectural

Apply the gate when a change would do any of these:

- **Pipeline shape** — add, remove, reorder, split or merge a stage; change a branch
  condition; change what runs per-run versus per-goods-line.
- **Module boundaries** — move a responsibility between modules, or add a dependency
  that crosses one of the "must not know about" statements in dossier file 10. Those
  statements are load-bearing: a dependency in the wrong direction is a defect, not a
  smell.
- **Data sources** — where any input comes from at run time. Which store, which API,
  which artifact, and what happens when it is absent.
- **Model assignments** — which model serves which call, and its decoding settings.
  Dossier open question D3 requires these pinned explicitly, because no measurement
  taken without pinning is reproducible.
- **External contracts** — anything touching the emitted declaration XML. It is fixed
  and not open to redesign; a change here is a change to what the customs portal
  receives.
- **Resolving a dossier open question** — the dossier carries explicit `[UNKNOWN]` and
  `[INFERRED]` markers. Closing one is a decision, and it is the user's to confirm.

## What does not need the gate

Ordinary implementation inside an already-agreed boundary: choosing a helper's name,
splitting a long function, adding a test, fixing a bug, adding a type hint. Build those
directly.

If unsure, ask this: *would the artifact's diagram or module table need to change?* If
yes, gate it.

## The procedure

1. **Write the decision down** — what changes, what it replaces, and what it costs.
   Name the consequences that are not obvious, especially anything it silently removes.
2. **Update the architecture artifact** so the diagram, the module table and the model
   table all reflect the proposed state. Mark the change as *proposed*, not as fact.
3. **Republish** the artifact to the same URL so the user reads one current page rather
   than a trail of versions.
4. **Stop and ask**, naming the decision and its alternatives in one short message. Give
   a recommendation — a review request is not an excuse to avoid having an opinion.
5. **Only then implement**, and only what was agreed.

## Recording it

Every gated decision goes in `PROGRESS.md` with its reasoning and what it cost, so the
record of *why* survives longer than the memory of the conversation. The dossier's own
lesson: a shipped rule whose justification cannot be located is a rule that has to be
re-tested from scratch.
