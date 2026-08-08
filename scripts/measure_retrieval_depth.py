"""Two measurements about the candidate list the final pick reads.

This makes real, billed provider calls. It is a script, not a test: it changes nothing,
it decides nothing, and no production default is read from it or written by it.

    .venv/bin/python scripts/measure_retrieval_depth.py --qdrant-path /some/scratch/copy

**Question 1 — does depth beyond 30 help the pick, or only the recall?** Recall is a
ceiling, not an outcome. Retrieval is run once per line at the deepest setting, the ranked
list is truncated to each depth, and the *same* real pick call is made on each truncation.
One retrieval per line means the only thing that varies between depths is how much of the
one list the model was shown.

**Question 2 — does factoring out the repeated path prefix help or hurt?** Retrieval is
scoped to one or two headings, so the opening of every candidate row is usually the same
text. The factored rendering states that opening once and gives each row only its own
tail. Compared at one depth, on the same lines, against the same retrieval.

Both questions are answered by the same pick call, so both share a sample and the sample
is small on purpose: this is a direction, not an evaluation. See the report footer for
what the sample size does and does not support.

The lines come from the evaluation corpus, whose codes are its generator's choices rather
than a broker's — so an accuracy number here is agreement with the corpus, not customs
correctness. The comparison between depths is unaffected, because every arm is scored
against the same labels.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import qdrant_client

from deepclare.classification.features import ClassificationFeatures
from deepclare.classification.line import ClassificationLine
from deepclare.classification.nodes import (
    NodeContext,
    _line_alone,
    pick_final_code,
    pick_heading_and_write_query,
    retrieve_candidates,
    shortlist_chapters,
)
from deepclare.classification.rendering import NOTHING, candidate_list
from deepclare.classification.schemas import PickCode
from deepclare.classification.state import TraversalState
from deepclare.config import load_settings
from deepclare.description import DescriptionWriter, build_line_contexts
from deepclare.domain import InvoiceGoodsLine, InvoiceRecord, Provenance, Traced, ValueOrigin
from deepclare.embedding import GeminiEmbedder
from deepclare.models import GenerativeModel, ModelTier
from deepclare.prompting import render_prompt
from deepclare.reference.store import Candidate, NomenclatureStore

DEPTHS = (10, 30, 50)
"""The candidate counts compared. 30 is what retrieval ships with today."""

FACTORED_DEPTH = 30
"""Question 2 is asked at the shipped depth, so its answer applies to the list the system
actually sends today."""

SAMPLE_SIZE = 25
SAMPLE_SEED = 20260808
MAX_LINES_PER_CASE = 2
"""One synthetic invoice is one product family. Without a cap, three lines of the same
family crowd out three chapters and the sample stops describing the corpus."""

PICK_WORKERS = 6
PATH_SEPARATOR = " › "

# The corpus states each line's unit as an OKEI code. An invoice prints an abbreviation,
# which is what the reading stage would hand the pipeline, so the five codes the corpus
# uses are written the way a document writes them. Nothing downstream of this script
# consumes the mapping.
PRINTED_UNIT_BY_OKEI = {
    "166": "KG",
    "796": "PCS",
    "055": "M2",
    "112": "L",
    "113": "M3",
}

EXTRACTED = Provenance(origin=ValueOrigin.EXTRACTED, source_document_id="invoice")


# --- the sample --------------------------------------------------------------


@dataclass(frozen=True)
class SampledLine:
    """One corpus goods line and the code the corpus expects for it."""

    case_id: str
    line_id: str
    source_name: str
    expected_code: str
    """Ten digits. The corpus files eleven; the eleventh is the national subdivision."""


def choose_sample(corpus_dir: Path, store: NomenclatureStore) -> list[SampledLine]:
    """A reproducible draw from the corpus's goods lines.

    Three filters, each removing a way one line would count twice or count wrongly:
    a goods name already seen, a ground-truth code already drawn, and a code this tree
    does not publish as a leaf (the corpus is synthetic and carries a few of those, which
    the existence gate rejects correctly and which no depth could ever retrieve).
    """
    candidates: list[SampledLine] = []
    seen_names: set[str] = set()
    for spec_path in sorted(corpus_dir.glob("*/case-*/ir.json")):
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        for position, goods in enumerate(spec["goods"]):
            name = goods["source_name"].strip()
            key = name.lower()
            if key in seen_names:
                continue
            seen_names.add(key)
            code = goods["hs_code"][:10]
            entry = store.entry(code)
            if entry is None or entry.level != 5:
                continue
            candidates.append(
                SampledLine(
                    case_id=spec["case_id"],
                    line_id=str(position + 1),
                    source_name=name,
                    expected_code=code,
                )
            )

    random.Random(SAMPLE_SEED).shuffle(candidates)
    drawn: list[SampledLine] = []
    seen_codes: set[str] = set()
    per_case: dict[str, int] = {}
    for line in candidates:
        if line.expected_code in seen_codes:
            continue
        if per_case.get(line.case_id, 0) >= MAX_LINES_PER_CASE:
            continue
        seen_codes.add(line.expected_code)
        per_case[line.case_id] = per_case.get(line.case_id, 0) + 1
        drawn.append(line)
        if len(drawn) == SAMPLE_SIZE:
            break
    return sorted(drawn, key=lambda one: (one.case_id, int(one.line_id)))


def invoice_of(corpus_dir: Path, case_id: str) -> InvoiceRecord:
    """The whole case as an invoice record, so the sibling summary is the real one."""
    spec_path = next(corpus_dir.glob(f"*/{case_id}/ir.json"))
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    return InvoiceRecord(
        source_document_id=case_id,
        goods_lines=tuple(
            _goods_line(str(position + 1), goods)
            for position, goods in enumerate(spec["goods"])
        ),
    )


def _goods_line(line_id: str, goods: dict) -> InvoiceGoodsLine:
    unit = PRINTED_UNIT_BY_OKEI.get(str(goods.get("unit") or ""))
    trade_name = goods.get("trade_name") or goods.get("brand")
    return InvoiceGoodsLine(
        line_id=line_id,
        description=Traced[str](value=goods["source_name"], provenance=EXTRACTED),
        unit=Traced[str](value=unit, provenance=EXTRACTED) if unit else None,
        unit_price=Traced[Decimal](
            value=Decimal(str(goods["unit_price"])), provenance=EXTRACTED
        ),
        trade_name=(
            Traced[str](value=trade_name, provenance=EXTRACTED) if trade_name else None
        ),
    )


# --- the two renderings ------------------------------------------------------


def shared_path(candidates: Sequence[Candidate]) -> str:
    """The path segments every candidate opens with, or the literal for none.

    At least one segment is always left on every row: two distinct codes can render an
    identical path, and a row reduced to nothing would be a code with no description.
    """
    paths = [_segments(one) for one in candidates]
    if not paths:
        return NOTHING
    limit = min(len(path) for path in paths) - 1
    common = 0
    while common < limit and len({path[common] for path in paths}) == 1:
        common += 1
    return PATH_SEPARATOR.join(paths[0][:common]) if common else NOTHING


def factored_candidate_list(candidates: Sequence[Candidate], shared: str) -> str:
    """The candidates as code plus the part of the path below the shared opening."""
    if shared == NOTHING:
        return candidate_list(candidates)
    depth = len(shared.split(PATH_SEPARATOR))
    return "\n".join(
        f"{index:>4}. {one.code} — {PATH_SEPARATOR.join(_segments(one)[depth:])}"
        for index, one in enumerate(candidates, start=1)
    )


def _segments(candidate: Candidate) -> list[str]:
    rendered = candidate.entry.path_en or candidate.entry.title()
    return rendered.split(PATH_SEPARATOR)


# --- the run -----------------------------------------------------------------


@dataclass
class Retrieval:
    """What one line's single retrieval produced, before any pick is made."""

    sample: SampledLine
    line: ClassificationLine
    candidates: tuple[Candidate, ...]
    chapters: tuple[str, ...]
    headings: tuple[str, ...]
    query: str
    state: TraversalState

    def rank_of_expected(self) -> int | None:
        for position, one in enumerate(self.candidates, start=1):
            if one.code == self.sample.expected_code:
                return position
        return None


def retrieve_once(
    sample: SampledLine,
    line: ClassificationLine,
    ctx: NodeContext,
) -> Retrieval:
    """Chapter shortlist, heading and query, then one search at the deepest setting.

    The real narrowing nodes, in the real order. Retrieval is not scoped to the correct
    heading: a list built from a mis-narrowed heading is part of what deeper retrieval has
    to survive, and hiding that would answer an easier question than the one asked.
    """
    state = TraversalState(line=line)
    state = shortlist_chapters(state, ctx)
    state = pick_heading_and_write_query(state, ctx)
    state = retrieve_candidates(state, ctx)
    return Retrieval(
        sample=sample,
        line=line,
        candidates=state.candidates,
        chapters=state.chapters,
        headings=state.headings,
        query=state.query,
        state=state,
    )


@dataclass
class PickOutcome:
    """One pick call: what it chose, what the prompt cost, what it was shown.

    Keyed by how many candidates were actually shown rather than by the depth that was
    asked for. Most scoped searches exhaust their two headings well before fifty rows, and
    when two depths truncate the same list to the same rows they are the same prompt —
    paying twice for it would buy nothing but this model's run-to-run variance.
    """

    line_key: str
    variant: str
    shown: int
    chosen_code: str | None
    abstained: bool
    prompt_tokens: int | None
    candidate_block_chars: int
    rationale: str

    def as_json(self) -> dict:
        return {
            "line_key": self.line_key,
            "variant": self.variant,
            "shown": self.shown,
            "chosen_code": self.chosen_code,
            "abstained": self.abstained,
            "prompt_tokens": self.prompt_tokens,
            "candidate_block_chars": self.candidate_block_chars,
            "rationale": self.rationale,
        }


def pick_full_path(retrieval: Retrieval, depth: int, ctx: NodeContext) -> PickOutcome:
    """The production pick, on the top `depth` of the one retrieved list."""
    shown = retrieval.candidates[:depth]
    state = retrieval.state.model_copy(update={"candidates": shown})
    after = pick_final_code(state, ctx)
    outcome = after.result
    call = after.steps[-1].call
    return PickOutcome(
        line_key=_key(retrieval.sample),
        variant="full_path",
        shown=len(shown),
        chosen_code=outcome.code if outcome else None,
        abstained=bool(outcome and outcome.code is None),
        prompt_tokens=call.usage.prompt_tokens if call else None,
        candidate_block_chars=len(candidate_list(shown)),
        rationale=(outcome.rationale if outcome else "")[:400],
    )


def pick_shared_path(retrieval: Retrieval, depth: int, ctx: NodeContext) -> PickOutcome:
    """The same pick, with the repeated opening of every path stated once.

    It is a different prompt file because it is different prompt text, and prompt text
    lives in the prompt directory. That is also the confound to state plainly: the two
    arms differ in the sentence that explains the list as well as in the list itself.
    """
    shown = retrieval.candidates[:depth]
    shared = shared_path(shown)
    block = factored_candidate_list(shown, shared)
    top_chapter = shown[0].code[:2]
    prompt = render_prompt(
        ctx.prompts_dir,
        "pick_code_shared_path",
        {
            **_line_alone(retrieval.line),
            "chapter_note": ctx.store.chapter_note(top_chapter),
            "shared_path": shared,
            "candidate_codes": block,
            "subheading_hint": NOTHING,
        },
    )
    result = ctx.model.generate(tier=ModelTier.STRONG, prompt=prompt, output=PickCode)
    answer = result.value
    chosen = None if answer.abstain or not answer.chosen_code.strip() else answer.chosen_code
    by_code = {one.code: one for one in shown}
    if chosen is not None and chosen not in by_code:
        # The production node abstains rather than substituting a candidate; scoring a
        # code that was never retrieved as a hit would measure a different system.
        chosen = None
    return PickOutcome(
        line_key=_key(retrieval.sample),
        variant="shared_path",
        shown=len(shown),
        chosen_code=chosen,
        abstained=chosen is None,
        prompt_tokens=result.call.usage.prompt_tokens,
        candidate_block_chars=len(block) + len(shared),
        rationale=answer.rationale[:400],
    )


def _key(sample: SampledLine) -> str:
    return f"{sample.case_id}/{sample.line_id}"


# --- the report --------------------------------------------------------------


def report(
    retrievals: list[Retrieval], outcomes: list[PickOutcome], out: Path
) -> None:
    expected = {_key(one.sample): one.sample.expected_code for one in retrievals}
    ranks = {_key(one.sample): one.rank_of_expected() for one in retrievals}
    retrieved = {_key(one.sample): len(one.candidates) for one in retrievals}
    recorded = {(one.line_key, one.variant, one.shown): one for one in outcomes}

    def arm_at(variant: str, depth: int) -> list[PickOutcome]:
        """Every line's outcome at this depth, resolved through what it could show."""
        found = []
        for key, count in retrieved.items():
            outcome = recorded.get((key, variant, min(depth, count)))
            if outcome is not None:
                found.append(outcome)
        return found

    lines: list[str] = []
    write = lines.append

    write("=" * 96)
    write(f"SAMPLE  {len(retrievals)} corpus goods lines, seed {SAMPLE_SEED}")
    write("=" * 96)
    write("")
    write(f"{'line':<16} {'expected':<12} {'retrieved':>10} {'rank':>6}  source name")
    for one in sorted(retrievals, key=lambda r: _key(r.sample)):
        rank = ranks[_key(one.sample)]
        write(
            f"{_key(one.sample):<16} {one.sample.expected_code:<12} "
            f"{len(one.candidates):>10} {(rank if rank else '-'):>6}  "
            f"{one.sample.source_name[:48]}"
        )
    write("")

    write("-" * 96)
    write("HOW DEEP THE LIST ACTUALLY GOES")
    write("-" * 96)
    write("  A depth setting is a ceiling, not a length: retrieval is scoped to the one or")
    write("  two chosen headings, and most headings do not hold that many leaves.")
    for depth in DEPTHS:
        reached = sum(1 for count in retrieved.values() if count >= depth)
        write(f"  lines whose scoped search returned at least {depth:>2} candidates: "
              f"{reached:>3}/{len(retrieved)}  {_pct(reached, len(retrieved))}")
    write(f"  median candidates retrieved: "
          f"{statistics.median(retrieved.values()) if retrieved else 0:g}")
    write("")

    write("-" * 96)
    write("RECALL — is the expected code in the list at all")
    write("-" * 96)
    for depth in DEPTHS:
        hits = sum(1 for rank in ranks.values() if rank is not None and rank <= depth)
        write(f"  recall@{depth:<3} {hits:>3}/{len(ranks)}  {_pct(hits, len(ranks))}")
    write("")

    write("-" * 96)
    write("QUESTION 1 — accuracy of the pick at each depth (full-path rendering)")
    write("-" * 96)
    write(f"  {'depth':>6} {'exact@10':>18} {'agree@6':>18} {'abstained':>12} "
          f"{'prompt tokens':>15}")
    for depth in DEPTHS:
        arm = arm_at("full_path", depth)
        write(f"  {depth:>6} {_score(arm, expected, 10):>18} {_score(arm, expected, 6):>18} "
              f"{_abstentions(arm):>12} {_tokens(arm):>15}")
    write("")

    changed = sorted(key for key, count in retrieved.items() if count > min(DEPTHS))
    write(f"  Restricted to the {len(changed)} lines where the list length actually "
          f"differs between depths:")
    for depth in DEPTHS:
        arm = [one for one in arm_at("full_path", depth) if one.line_key in changed]
        write(f"  {depth:>6} {_score(arm, expected, 10):>18} {_score(arm, expected, 6):>18} "
              f"{_abstentions(arm):>12}")
    write("")

    settled = sorted(
        key
        for key, rank in ranks.items()
        if rank is not None and rank <= min(DEPTHS) and retrieved[key] > min(DEPTHS)
    )
    write(f"  Restricted further, to the {len(settled)} of those whose expected code is "
          f"inside the top {min(DEPTHS)} —")
    write("  the correct answer is available in every arm, so only the noise around it grows:")
    for depth in DEPTHS:
        arm = [one for one in arm_at("full_path", depth) if one.line_key in settled]
        write(f"  {depth:>6} {_score(arm, expected, 10):>18} {_score(arm, expected, 6):>18} "
              f"{_abstentions(arm):>12}")
    write("")

    write("  Per line, at each depth ('=' means the list was too short for this depth to")
    write("  differ from the one before it, so the same prompt was not paid for twice):")
    write(f"  {'line':<16} " + " ".join(f"{'k=' + str(d):>10}" for d in DEPTHS))
    for retrieval in sorted(retrievals, key=lambda r: _key(r.sample)):
        key = _key(retrieval.sample)
        cells = []
        previous: int | None = None
        for depth in DEPTHS:
            shown = min(depth, retrieved[key])
            if shown == previous:
                cells.append(f"{'=':>10}")
            else:
                outcome = recorded.get((key, "full_path", shown))
                cells.append(f"{_cell(outcome, expected[key]):>10}")
            previous = shown
        write(f"  {key:<16} " + " ".join(cells))
    write("")

    write("-" * 96)
    write(f"QUESTION 2 — full path against shared path, both at k={FACTORED_DEPTH}")
    write("-" * 96)
    write(f"  {'rendering':>14} {'exact@10':>18} {'agree@6':>18} {'abstained':>12} "
          f"{'prompt tokens':>15} {'candidate chars':>17}")
    for variant in ("full_path", "shared_path"):
        arm = arm_at(variant, FACTORED_DEPTH)
        write(f"  {variant:>14} {_score(arm, expected, 10):>18} "
              f"{_score(arm, expected, 6):>18} {_abstentions(arm):>12} "
              f"{_tokens(arm):>15} {_chars(arm):>17}")
    write("")
    write("  Lines where the two renderings chose differently:")
    disagreements = 0
    for key in sorted(retrieved):
        shown = min(FACTORED_DEPTH, retrieved[key])
        full = recorded.get((key, "full_path", shown))
        short = recorded.get((key, "shared_path", shown))
        if full is None or short is None or full.chosen_code == short.chosen_code:
            continue
        disagreements += 1
        write(f"    {key:<16} expected {expected[key]}  full "
              f"{full.chosen_code or 'abstain':<12} shared "
              f"{short.chosen_code or 'abstain':<12}")
    if not disagreements:
        write("    none")
    write("")
    write("  Repeated opening, per line, at that depth. A second shortlisted heading is")
    write("  what usually cuts the shared opening back to the chapter title alone:")
    write(f"  {'line':<16} {'headings':>9} {'shared segs':>12} {'shared chars':>13} "
          f"{'x rows':>9} {'% of block':>11}")
    for retrieval in sorted(retrievals, key=lambda r: _key(r.sample)):
        shown = retrieval.candidates[:FACTORED_DEPTH]
        if not shown:
            continue
        shared = shared_path(shown)
        segments = 0 if shared == NOTHING else len(shared.split(PATH_SEPARATOR))
        chars = 0 if shared == NOTHING else len(shared)
        block = len(candidate_list(shown))
        write(
            f"  {_key(retrieval.sample):<16} {len(retrieval.headings):>9} "
            f"{segments:>12} {chars:>13} "
            f"{chars * len(shown):>9} {_pct(chars * len(shown), block):>11}"
        )
    write("")

    write("-" * 96)
    write("WHAT THIS SAMPLE SUPPORTS")
    write("-" * 96)
    write(f"  n = {len(retrievals)}. One line is {100 / max(len(retrievals), 1):.0f} "
          "percentage points, so a gap of one or two lines between two arms is noise.")
    write("  The corpus is synthetic: a hit is agreement with its generator, not customs")
    write("  correctness. Every arm is scored against the same labels, so the comparison")
    write("  between arms is unaffected by that.")
    write("  Reasoning models are not reproducible from pinned decoding alone (PROGRESS")
    write("  entry 8), so a single run of a single arm carries its own run-to-run variance.")

    text = "\n".join(lines)
    print(text)
    (out / "report.txt").write_text(text + "\n", encoding="utf-8")


def _cell(outcome: PickOutcome | None, expected: str) -> str:
    if outcome is None:
        return "?"
    chosen = outcome.chosen_code
    if chosen is None:
        return "abstain"
    if chosen == expected:
        return "exact"
    if chosen[:6] == expected[:6]:
        return "6-digit"
    return "wrong"


def _score(arm: list[PickOutcome], expected: dict[str, str], digits: int) -> str:
    if not arm:
        return "-"
    hits = sum(
        1
        for one in arm
        if one.chosen_code
        and one.chosen_code[:digits] == expected[one.line_key][:digits]
    )
    return f"{hits}/{len(arm)}  {_pct(hits, len(arm))}"


def _abstentions(arm: list[PickOutcome]) -> str:
    if not arm:
        return "-"
    return f"{sum(1 for one in arm if one.abstained)}/{len(arm)}"


def _tokens(arm: list[PickOutcome]) -> str:
    counted = [one.prompt_tokens for one in arm if one.prompt_tokens is not None]
    return f"{round(statistics.mean(counted)):,} avg" if counted else "-"


def _chars(arm: list[PickOutcome]) -> str:
    counted = [one.candidate_block_chars for one in arm]
    return f"{round(statistics.mean(counted)):,} avg" if counted else "-"


def _pct(part: int, whole: int) -> str:
    return f"{100.0 * part / whole:.1f}%" if whole else "-"


# --- entry point -------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--qdrant-path",
        type=Path,
        required=True,
        help="A copy of the collection with its lock removed. The embedded store is "
        "exclusive-locked to one process and another agent holds the real one.",
    )
    parser.add_argument("--corpus", type=Path, default=Path("evalkit/corpus"))
    parser.add_argument(
        "--limit-lines",
        type=int,
        default=0,
        help="Run only the first N of the chosen sample. For a smoke run before "
        "spending on the whole thing; it narrows the sample and never changes it.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Directory for the raw per-call records and the report.",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    settings = load_settings()
    embedder = GeminiEmbedder(settings)
    client = qdrant_client.QdrantClient(path=str(args.qdrant_path))
    store = NomenclatureStore(
        artifact_dir=settings.reference_dir,
        qdrant_client=client,
        collection=settings.qdrant_collection,
        embedder=embedder,
    )

    sample = choose_sample(args.corpus, store)
    if args.limit_lines:
        sample = sample[: args.limit_lines]
    print(f"sample       : {len(sample)} lines from {args.corpus}")
    print(f"nomenclature : vintage {store.vintage}")
    print(f"embedding    : {store.embedding_pairing[0]} at {store.embedding_pairing[1]}d")
    print(f"strong model : {settings.genai_model_strong}")
    print()

    with GenerativeModel(settings) as model:
        deep = NodeContext(
            store=store,
            model=model,
            prompts_dir=settings.prompts_dir,
            features=ClassificationFeatures(candidate_limit=max(DEPTHS)),
        )
        writer = DescriptionWriter(model, settings.prompts_dir)

        retrievals = _phase_one(sample, args, deep, writer)
        outcomes = _phase_two(retrievals, args, deep)

    report(retrievals, outcomes, args.out)
    return 0


def _phase_one(
    sample: list[SampledLine],
    args: argparse.Namespace,
    ctx: NodeContext,
    writer: DescriptionWriter,
) -> list[Retrieval]:
    """Description, narrowing and one retrieval per line. Serial: the embedded vector
    store is a single process and a local file, and nothing here is worth racing it for.

    A completed phase one is reloaded rather than repeated. That is not only thrift: the
    picks recorded beside it were made against *these* descriptions and *this* candidate
    order, and writing fresh ones under the same keys would score one run's picks against
    another run's lists.
    """
    cached = _load_retrievals(sample, args, ctx)
    if cached is not None:
        print(f"phase one     : reloaded {len(cached)} retrievals from {args.out}\n")
        return cached

    retrievals: list[Retrieval] = []
    for position, one in enumerate(sample, start=1):
        context = _context_for_sample(one, args)
        written = writer.write(context)
        line = _classification_line(
            one, context, written.text.value, written.search_term.value
        )
        retrieval = retrieve_once(one, line, ctx)
        retrievals.append(retrieval)
        rank = retrieval.rank_of_expected()
        print(
            f"[{position:>2}/{len(sample)}] {_key(one):<16} {one.source_name[:38]:<38} "
            f"chapters {list(retrieval.chapters)} headings {list(retrieval.headings)} "
            f"-> {len(retrieval.candidates)} candidates, expected at rank "
            f"{rank if rank else 'absent'}"
        )
    (args.out / "retrievals.json").write_text(
        json.dumps(
            [
                {
                    "line_key": _key(one.sample),
                    "source_name": one.sample.source_name,
                    "expected_code": one.sample.expected_code,
                    "description_hy": one.line.description_hy,
                    "search_term_hy": one.line.search_term_hy,
                    "chapters": list(one.chapters),
                    "headings": list(one.headings),
                    "query": one.query,
                    "rank_of_expected": one.rank_of_expected(),
                    "candidates": [
                        {"code": c.code, "similarity": c.similarity} for c in one.candidates
                    ],
                }
                for one in retrievals
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return retrievals


def _context_for_sample(sample: SampledLine, args: argparse.Namespace):
    """The line's real per-line context, siblings and all, from its own case."""
    invoice = invoice_of(args.corpus, sample.case_id)
    contexts = {one.line_id: one for one in build_line_contexts(invoice)}
    return contexts[sample.line_id]


def _classification_line(
    sample: SampledLine, context, description_hy: str, search_term_hy: str
) -> ClassificationLine:
    return ClassificationLine(
        line_id=sample.line_id,
        description_hy=description_hy,
        search_term_hy=search_term_hy,
        source_name=context.goods_name,
        source_language=context.source_language,
        unit=context.unit,
        trade_name=context.trade_name,
        material=context.material,
        grounding_facts=context.grounding_facts,
        sibling_names=context.sibling_names,
    )


def _load_retrievals(
    sample: list[SampledLine], args: argparse.Namespace, ctx: NodeContext
) -> list[Retrieval] | None:
    """A previous phase one, or None if there is not one covering exactly this sample.

    The candidates are rebuilt from the store by code, so the reloaded list is the same
    codes in the same order at the same similarities the picks were made against.
    """
    path = args.out / "retrievals.json"
    if not path.exists():
        return None
    stored = {
        row["line_key"]: row
        for row in json.loads(path.read_text(encoding="utf-8"))
    }
    if {_key(one) for one in sample} - set(stored):
        return None

    retrievals: list[Retrieval] = []
    for one in sample:
        row = stored[_key(one)]
        context = _context_for_sample(one, args)
        line = _classification_line(
            one, context, row["description_hy"], row["search_term_hy"]
        )
        candidates = tuple(
            Candidate(
                code=held["code"],
                similarity=held["similarity"],
                entry=ctx.store.entry(held["code"]),
            )
            for held in row["candidates"]
        )
        state = TraversalState(line=line).advance(
            "reloaded",
            f"phase one reloaded from {path}",
            None,
            chapters=tuple(row["chapters"]),
            headings=tuple(row["headings"]),
            query=row["query"],
            candidates=candidates,
            retrieval_scope="reloaded",
        )
        retrievals.append(
            Retrieval(
                sample=one,
                line=line,
                candidates=candidates,
                chapters=tuple(row["chapters"]),
                headings=tuple(row["headings"]),
                query=row["query"],
                state=state,
            )
        )
    return retrievals


def _phase_two(
    retrievals: list[Retrieval], args: argparse.Namespace, ctx: NodeContext
) -> list[PickOutcome]:
    """Every pick call. Parallel across lines; each writes its record as it lands, so a
    failure part-way costs only the calls that had not landed yet.
    """
    record_path = args.out / "picks.jsonl"
    done: set[tuple[str, str, int]] = set()
    if record_path.exists():
        for row in record_path.read_text(encoding="utf-8").splitlines():
            if row.strip():
                have = json.loads(row)
                done.add((have["line_key"], have["variant"], have["shown"]))

    planned: dict[tuple[str, str, int], tuple] = {}
    for retrieval in retrievals:
        available = len(retrieval.candidates)
        if not available:
            continue
        key = _key(retrieval.sample)
        for variant, depths in (
            ("full_path", DEPTHS),
            ("shared_path", (FACTORED_DEPTH,)),
        ):
            for depth in depths:
                shown = min(depth, available)
                planned.setdefault(
                    (key, variant, shown), (retrieval, variant, shown)
                )
    jobs = [job for signature, job in planned.items() if signature not in done]
    print(
        f"\npicks to make : {len(jobs)} "
        f"({len(planned) - len(jobs)} already recorded, "
        f"{len(retrievals) * (len(DEPTHS) + 1) - len(planned)} skipped as duplicate "
        f"prompts)\n"
    )

    write_lock = threading.Lock()
    outcomes: list[PickOutcome] = []

    def run(job) -> None:
        retrieval, variant, shown = job
        if variant == "full_path":
            outcome = pick_full_path(retrieval, shown, ctx)
        else:
            outcome = pick_shared_path(retrieval, shown, ctx)
        with write_lock:
            outcomes.append(outcome)
            with record_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(outcome.as_json(), ensure_ascii=False) + "\n")
            print(
                f"  {outcome.line_key:<16} {variant:<12} shown={shown:<3} -> "
                f"{outcome.chosen_code or 'abstain':<12} "
                f"{outcome.prompt_tokens or '?'} prompt tokens"
            )

    with ThreadPoolExecutor(max_workers=PICK_WORKERS) as pool:
        list(pool.map(run, jobs))

    # Re-read so a resumed run reports every arm, not only the ones it made itself.
    outcomes = [
        PickOutcome(**json.loads(row))
        for row in record_path.read_text(encoding="utf-8").splitlines()
        if row.strip()
    ]
    return outcomes


if __name__ == "__main__":
    sys.exit(main())
