# evals

Two reproducible evaluations against `evalkit/corpus/oneToOne` (71 synthetic cases,
2,842 goods lines). Each writes a `manifest.json` pinning the commit, provider, model
ids, feature flags and nomenclature vintage — a scorecard without that provenance is
an anecdote.

They answer different questions and cost different amounts:

| | what it measures | scale | cost |
|---|---|---|---|
| **`hs_classification`** | how good is the commodity code, in isolation | all 2,842 lines | ~$15 / ~1 h |
| **`end_to_end`** | is the whole chain intact, scans → filed XML | 3 cases | minutes per case |

## 1. HS classification

```bash
# full corpus, DeepSeek, reasoning only on the tier that decides
python -m evals.hs_classification.run --provider deepseek --workers 8 --line-workers 8 \
       --out runs/hs_deepseek

# every tier on v4-pro with thinking
python -m evals.hs_classification.run --provider deepseek --all-pro \
       --reasoning-tiers cheap,standard,strong --out runs/hs_pro_thinking

# Gemini, 200 lines sampled round-robin across cases
python -m evals.hs_classification.run --provider gemini --lines 200 --out runs/hs_gemini

python -m evals.hs_classification.score runs/hs_deepseek          # no API calls
```

Survives crashes and interruptions. Every finished line is appended to
`results.jsonl` keyed `<case>:<line_id>` and skipped on restart; written
descriptions are cached separately because M8 is a billed call and
`build_classification_lines()` needs one for *every* line in a case before it can
classify *any*. Re-running a completed run makes zero API calls. For long runs:

```bash
tmux new -d -s hs 'evals/hs_classification/supervise.sh 8 runs/hs_deepseek --provider deepseek'
```

**The scorer reports precision, coverage and yield, not accuracy.** The classifier
abstains, and the specification wants it to — on a legal document a wrong value is
consequential while a missing one is work left for a human. A single accuracy number
can't tell a pipeline that abstains on everything from one that guesses on
everything.

### `retrieval_recall.py` — a cheaper diagnostic

```bash
python -m evals.hs_classification.retrieval_recall --lines 300
```

Embeddings only, no generation, well under a dollar. Answers whether the gold code
is even *in* the candidate set, which caps everything downstream: if retrieval
misses, no picker can recover. Compares the invoice line as-is against the
contract-shaped `<chapter> — <heading> — <leaf>` query the index was built from.

## 2. End to end

```bash
python -m evals.end_to_end.run --cases 3 --out runs/e2e
python -m evals.end_to_end.run --case-ids case-007,case-019 --out runs/e2e
```

Invokes the product's own CLI (`python -m deepclare run invoice.pdf
--consignment-note cmr.pdf`) so the eval tests what ships, then stages the output
where `evalkit` expects it and runs `python -m evalkit corpus`. Scoring is **not**
reimplemented — evalkit already compares ESADout_CU against ground truth with the
right metric per field type and exits non-zero when a case misses its thresholds.

Defaults to the smallest cases: this is about whether the chain holds, and a
554-line invoice proves that no better than a 4-line one at a hundred times the cost.

## Outputs

`runs/` and `*_out/` are gitignored — large, machine-specific, re-derivable. The
harness and the scorers are the artifact; numbers belong in a report.

```
runs/<name>/
  manifest.json        commit, provider, models, flags, vintage
  results.jsonl        one row per line: gold, predicted, correctness, per-stage tokens
  descriptions.jsonl   cached M8 output (resume without re-paying)
  run.log              timestamped progress
```

## Reading the numbers

- **precision** — of the codes it emitted, how many were right
- **coverage** — how often it emitted one rather than abstaining
- **yield** — precision × coverage, the end-to-end useful rate

Reported at 2/4/6/10 digits, because a code wrong at the chapter is a different
failure from one wrong in the last two digits. The scorer also checks whether the
**confidence score separates right from wrong** — if it doesn't, the
`review_below_confidence` gate is flagging blind, and that is worth knowing before
trusting it.

## Known corpus caveat

Three codes are fabricated — `39069090090`, `39100000090`, `39269097098` — confirmed
absent from the live tariff at `exim.src.am`. They are unreachable labels rather than
misses, so the harness skips them and the manifest records that it did.
