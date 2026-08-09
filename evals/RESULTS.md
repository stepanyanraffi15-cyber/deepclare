# Eval results

Runs against `evalkit/corpus/oneToOne` (71 synthetic cases, 2,842 goods lines) at commit
`f2861cc`, nomenclature vintage `2026-06-15`, embedding `gemini-embedding-001 @768d`.
Raw `results.jsonl` files are gitignored (large, re-derivable); the per-run manifests and
the paired overlap set are in `results/`.

## Gemini vs DeepSeek on the same lines

The two providers were run over different samples, so the honest comparison is the
**170 lines both processed**. The third column is the same DeepSeek run scored over the
whole corpus, to show the 170-line slice is representative rather than a lucky draw.

| metric | Gemini (170) | DeepSeek (170) | DeepSeek (full set) |
|---|---|---|---|
| committed / total | 114/170 | 95/170 | 1490/2390 |
| coverage | 67% | 56% | 62% |
| precision @2 (chapter) | 90% | 89% | 91% |
| precision @4 (heading) | 82% | 77% | 77% |
| precision @6 | 76% | 71% | 70% |
| precision @10 (exact) | 65% | 62% | 61% |
| correct answers | 74 | 59 | 911 |

- **Gemini**: `gemini-3.5-flash-lite` / `gemini-3.6-flash` / `gemini-2.5-pro`
- **DeepSeek**: `deepseek-v4-flash` / `deepseek-v4-flash` / `deepseek-v4-pro`, reasoning
  on the strong tier only
- **precision** is over the codes a run actually emitted; the classifier abstains by
  design, so precision and coverage are reported separately rather than merged into one
  accuracy figure
- per-line detail for all 170: `results/overlap_gemini200_vs_deepseek.jsonl`

DeepSeek's figures barely move between the 170-line slice and the full 2,390 (62%→61% at
ten digits, 77%→77% at heading), so the overlap is not a distorted sample.

On the 84 lines **both** committed to a code: Gemini 68%, DeepSeek 63%. Where the two
disagree, Gemini is right 21 times and DeepSeek 6.

## All runs

| run | models | reasoning | subset | lines | coverage | P@10 |
|---|---|---|---|---|---|---|
| `hs_deepseek_flash_baseline` | DeepSeek flash/flash/pro | strong only | full corpus | 2,390 | 62% | 61% |
| `hs_final` | DeepSeek pro/pro/pro | none | 7 chapters (selected) | 1,216 | 41% | 74% |
| `hs_deepseek_half` | DeepSeek pro/pro/pro | all tiers | random 50% (partial) | 341 | 61% | 56% |
| `hs_gemini_tenth` | Gemini | n/a | random 10% | 261 | 72% | 61% |

**Read these with their caveats.** Only the first is a clean full-corpus number.

- `hs_final` — those 7 chapters were chosen *because* the baseline scored ≥70% on them,
  so 74% is in-sample for the slice and not comparable to the rest. The rule is recorded
  in `results/manifest_hs_final.json`.
- `hs_deepseek_half` — 341 of 1,421 lines finished before the Google account ran out of
  credit; they are the cases that completed first, not a random draw.
- `hs_gemini_tenth` — n=261.

## End to end

Three cases through the full product CLI (scans → declaration XML), scored by `evalkit`:

```
cases 3 | pass_rate 0.00 | line_f1 0.75 | numeric_exact 0.75
code_exact 1.00 | code@6 1.00 | desc_chrf 0.28
```

## Observations that are not about model choice

**Coverage, not precision, is where the runs differ.** Precision sits at 61–65% across
every unselected run while coverage swings 41–72%.

**53% of the 170 overlap lines are wrong for both providers**, frequently with the
*identical* wrong code — `3923100000`→`3924900009` (plastic baskets),
`8528722001`→`8528724000` (LED televisions, all three sizes),
`3214101009`→`3824509000` (grout). A shared wrong answer is not a model failure.

**Whole product families abstain on both**: paints (`3209100009`) 5/5, adhesive tapes
(`3919108000`) 3/3, sand-mill parts (`8474909000`) 3/3.

**The confidence score does not separate right from wrong** — median 0.65 when correct,
0.65 when wrong, in every run. The `review_below_confidence: 0.7` gate is therefore
flagging on a signal that carries no information about correctness.

**Retrieval is a plausible common cause.** `reference/index.py` embeds each leaf as
`<chapter> — <heading> — <leaf>`, skipping the 6-digit subheading. Since ~29% of leaf
names are literally "other", 7,299 of 13,279 leaves (55%) share an identical embedding
text — and therefore an identical vector — with at least one sibling; the largest such
group has 103 members. Abstained lines are 74% "other"-named leaves against 47% for
committed ones. In 1,740 of 1,741 collision groups the *rendered path* the picker reads
does distinguish the members, so the ambiguity is in what retrieval can rank, not in what
the model can read.

## Reproducing

```bash
python -m evals.hs_classification.run --provider deepseek --workers 8 --line-workers 8 \
       --out runs/hs_deepseek
python -m evals.hs_classification.score runs/hs_deepseek
```

Gemini is gated behind `--allow-gemini` in both pipelines: its generation tiers are
billed to the Google account and a sweep drains it quickly. Note that retrieval embeds
through Gemini whatever the generation provider, so a depleted Google account blocks
every run.
