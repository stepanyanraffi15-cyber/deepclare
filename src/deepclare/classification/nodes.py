"""The nodes of the Code Assignment graph.

Each takes state and returns state. None of them decides what runs next — the edges do,
and they are declared in `assignment.py`, which is the one place the topology reads.

Every node appends one step record, including the nodes that decide without a model. A
trace that only shows the model calls cannot show why two of them were skipped.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from deepclare.classification.codes import (
    HARMONIZED_DIGITS,
    HEADING_DIGITS,
    harmonized_prefix,
    leaf_form,
    normalize_at,
    normalize_chapter,
)
from deepclare.classification.confidence import (
    HEADING_DIGITS as AGREEMENT_HEADING_DIGITS,
)
from deepclare.classification.confidence import (
    agreement,
    below_review_gate,
    composite_confidence,
)
from deepclare.classification.errors import ClassificationError
from deepclare.classification.features import ClassificationFeatures
from deepclare.classification.line import ClassificationLine
from deepclare.classification.rendering import (
    NOTHING,
    bullets,
    candidate_list,
    deterministic_query,
    menu,
    value,
)
from deepclare.classification.schemas import (
    PickCode,
    PickHeading,
    PreferSubheading,
    ShortlistChapters,
    VerifyCode,
)
from deepclare.classification.state import GraphOutcome, TraversalState
from deepclare.models import GenerativeModel, ModelError, ModelResult, ModelTier
from deepclare.prompting import render_prompt
from deepclare.reference.store import NomenclatureStore

NARROWING_TIER = ModelTier.STANDARD
"""Chapter, heading and subheading choice. Reading and writing work across languages,
constrained by a menu the call is given — not a label-emitting call, and not the material
or legal distinction the final pick turns on."""

PICK_TIER = ModelTier.STRONG
"""The final pick and the verifier. These are the calls that decide a legal
classification, and they are the only place in the run where a material or legal
distinction is made."""

MAX_CHAPTERS = 2
"""Two, not one. The single largest measured failure is a chapter mis-pick, which filters
the correct code out of retrieval entirely and cannot be recovered downstream. The second
chapter is the safety net; picking one chapter twice wastes it."""

MAX_HEADINGS = 2
MAX_SUBHEADINGS = 2
_TRACE_EXCERPT = 160


@dataclass(frozen=True)
class NodeContext:
    """What the nodes need from outside themselves."""

    store: NomenclatureStore
    model: GenerativeModel
    prompts_dir: Path
    features: ClassificationFeatures


# --- shared predicates, used by the edges in assignment.py --------------------


def usable_printed_prefix(
    line: ClassificationLine, store: NomenclatureStore
) -> str | None:
    """The harmonized prefix of a code printed on this line, when this tree can use it.

    Three conditions, all of them about the tree rather than about the code: it must
    reduce to at least six digits, its chapter must be a chapter here, and its heading
    must resolve to a heading title here. A foreign national code that fails any of them
    names a subheading that does not exist in this nomenclature, so it is not a shortcut,
    it is a wrong turn.
    """
    if line.printed_code is None:
        return None
    prefix = harmonized_prefix(line.printed_code.value)
    if prefix is None:
        return None
    if prefix[:2] not in store.known_chapters():
        return None
    if not store.heading_title(prefix[:HEADING_DIGITS]):
        return None
    return prefix


def is_dead_end(state: TraversalState) -> bool:
    """The fast path was taken and produced no code.

    Abstained, retrieved nothing, or was vetoed — the three shapes are the same problem:
    a printed code that pointed at the wrong subtree, which would otherwise strand the
    line there forever.
    """
    return state.printed_prefix is not None and (
        state.result is None or state.result.code is None
    )


# --- C0 ---------------------------------------------------------------------


def take_printed_code(state: TraversalState, ctx: NodeContext) -> TraversalState:
    """Take the chapter and the heading from the code the invoice printed.

    The exporter's broker already classified this product and the first six digits of
    what they wrote are internationally harmonized. Both narrowing calls and the
    subheading call are skipped: the document already states the subheading.
    """
    prefix = usable_printed_prefix(state.line, ctx.store)
    if prefix is None:
        raise ClassificationError(
            f"line {state.line.line_id}: the fast path ran on a printed code this tree "
            "cannot use. The entry condition and this node disagree, which is a defect "
            "in the graph declaration."
        )
    chapter, heading = prefix[:2], prefix[:HEADING_DIGITS]
    query = deterministic_query(ctx.store, state.line, (chapter,), (heading,))
    return state.advance(
        "C0",
        f"printed code {state.line.printed_code.value!r} reduces to {prefix}; "
        f"chapter {chapter}, heading {heading}, both narrowing calls skipped",
        None,
        primary_chapter=chapter,
        chapters=(chapter,),
        headings=(heading,),
        printed_prefix=prefix,
        query=query,
    )


# --- C1 ---------------------------------------------------------------------


def shortlist_chapters(state: TraversalState, ctx: NodeContext) -> TraversalState:
    """Shortlist one or two of the ninety-six chapters.

    An empty or unvalidatable shortlist is not an error. It degrades to an unfiltered
    search over the whole nomenclature, which is a worse search and not a failed line.
    """
    known = ctx.store.known_chapters()
    result = _ask(
        ctx,
        state.line,
        "shortlist_chapters",
        {
            **_line_with_context(state.line),
            "chapter_menu": menu(ctx.store.chapter_menu()),
        },
        ShortlistChapters,
        NARROWING_TIER,
        "shortlisting chapters",
    )
    answer = result.value
    chapters = _kept(
        (normalize_chapter(offered) for offered in answer.chapters),
        lambda code: code in known,
        MAX_CHAPTERS,
    )
    detail = (
        f"identified as {_excerpt(answer.identity)}; chapters {list(chapters) or 'none'}"
        f" — {_excerpt(answer.reasoning)}"
    )
    return state.advance(
        "C1",
        detail,
        result.call,
        chapters=chapters,
        primary_chapter=chapters[0] if chapters else None,
    )


# --- C2 ---------------------------------------------------------------------


def pick_heading_and_write_query(
    state: TraversalState, ctx: NodeContext
) -> TraversalState:
    """Pick the headings and write the search text, in one call.

    One call because they are two views of one judgement: what the product is decides
    both which heading covers it and how to describe it to the index.
    """
    offered = ctx.store.heading_menu(list(state.chapters)) if state.chapters else []
    if not offered:
        return state.advance(
            "C2",
            "no chapter shortlist, so no heading menu and no call; retrieval will run "
            "unfiltered over the whole nomenclature with the deterministic query",
            None,
            headings=(),
            query=deterministic_query(ctx.store, state.line, (), ()),
        )

    result = _ask(
        ctx,
        state.line,
        "pick_heading",
        {**_line_with_context(state.line), "heading_menu": menu(offered)},
        PickHeading,
        NARROWING_TIER,
        "picking headings and writing the search query",
    )
    answer = result.value
    available = {code for code, _ in offered}
    headings = _kept(
        (normalize_at(offer, HEADING_DIGITS) for offer in answer.headings),
        lambda code: code in available,
        MAX_HEADINGS,
    )
    query = answer.search_text.strip()
    detail = (
        f"headings {list(headings) or 'none'} of {len(offered)} offered; "
        f"query {_excerpt(query) or 'empty'} — {_excerpt(answer.reasoning)}"
    )
    return state.advance("C2", detail, result.call, headings=headings, query=query)


# --- C3 ---------------------------------------------------------------------


def prefer_subheading(state: TraversalState, ctx: NodeContext) -> TraversalState:
    """Name one or two likely 6-digit subheadings, as a soft preference.

    It marks candidates and never removes one. That is what makes the call safe to make
    on a line whose deciding attribute is unstated: the permission to guess costs nothing
    when the guess cannot narrow anything.
    """
    offered = ctx.store.subheading_menu(list(state.headings)) if state.headings else []
    if not offered:
        return state.advance(
            "C3",
            "the tree publishes no 6-digit level under these headings, so there is "
            "nothing to prefer and no call was made",
            None,
            subheadings=(),
        )

    result = _ask(
        ctx,
        state.line,
        "prefer_subheading",
        {**_line_with_context(state.line), "subheading_menu": menu(offered)},
        PreferSubheading,
        NARROWING_TIER,
        "preferring subheadings",
    )
    answer = result.value
    available = {code for code, _ in offered}
    subheadings = _kept(
        (normalize_at(offer, HARMONIZED_DIGITS) for offer in answer.subheadings),
        lambda code: code in available,
        MAX_SUBHEADINGS,
    )
    return state.advance(
        "C3",
        f"prefers {list(subheadings) or 'none'} of {len(offered)} offered — "
        f"{_excerpt(answer.reasoning)}",
        result.call,
        subheadings=subheadings,
    )


# --- C4 ---------------------------------------------------------------------


def retrieve_candidates(state: TraversalState, ctx: NodeContext) -> TraversalState:
    """Embed the query once and search the leaves, at the narrowest scope available.

    **No similarity threshold is applied.** Every retrieved candidate is shown to the
    model, because a threshold decides on a number what the final pick has to decide on
    meaning — and because a list the model can reject wholesale is what abstention
    depends on. Candidates are deduplicated by code keeping the maximum similarity and
    sorted descending; that happens inside the store, along with the prefix scope.
    """
    query = state.query.strip()
    substituted = not query
    if substituted:
        query = deterministic_query(
            ctx.store, state.line, state.chapters, state.headings
        )

    # The ladder always ends with the unfiltered scope, so the loop always assigns.
    ladder = _scope_ladder(state)
    tried: list[str] = []
    outcome = None
    for label, prefixes in ladder:
        outcome = ctx.store.search(
            query, prefixes=prefixes, limit=ctx.features.candidate_limit
        )
        tried.append(f"{label} -> {len(outcome.candidates)}")
        if outcome.candidates:
            break
    if outcome is None:
        raise ClassificationError(
            f"line {state.line.line_id}: the retrieval scope ladder was empty, which "
            "cannot happen — the unfiltered scope is always its last rung."
        )

    detail = f"query {_excerpt(query)!r}; scopes {' | '.join(tried)}"
    if substituted:
        detail = "the model wrote no query, so the deterministic one was used; " + detail
    if outcome.dropped_unknown_codes:
        detail += (
            f"; {outcome.dropped_unknown_codes} retrieved code(s) are absent from the "
            "tree and were dropped"
        )
    return state.advance(
        "C4",
        detail,
        None,
        query=query,
        candidates=tuple(outcome.candidates),
        retrieval_scope=" | ".join(tried),
    )


def _scope_ladder(state: TraversalState) -> list[tuple[str, list[str] | None]]:
    """Scopes from narrowest to widest, as the specification's preference order.

    A scope that retrieves nothing widens to the next one rather than ending the line.
    The specification names one such fallback by hand — a 6-digit-scoped search that
    returns nothing falls back to the full heading, because the EAEU tree may split that
    subtree differently than the harmonized level suggests. The same reasoning applies at
    every rung, and widening only ever adds candidates: nothing is removed, so nothing
    can be lost.
    """
    ladder: list[tuple[str, list[str] | None]] = []
    if state.printed_prefix:
        ladder.append(("printed 6-digit subtree", [state.printed_prefix]))
    if state.headings:
        ladder.append(("chosen headings", list(state.headings)))
    if state.chapters:
        ladder.append(("shortlisted chapters", list(state.chapters)))
    ladder.append(("whole nomenclature", None))
    return ladder


# --- C5 ---------------------------------------------------------------------


def pick_final_code(state: TraversalState, ctx: NodeContext) -> TraversalState:
    """Choose one code from the candidates, or abstain.

    The highest-stakes call in the system, and the one place the governing asymmetry is
    enforced against a model: a human reviewer catches an abstention and does not catch a
    confident wrong code.

    Two structural defences sit around the call. The line is shown *without* the source
    language and the sibling summary, because broad context measurably helps chapter and
    heading choice and measurably distracts leaf-level discrimination. And a code that is
    not in the candidate set produces an **abstention**, never the top candidate at zero
    confidence — the specification records that silent substitution as a shipped failure
    path and says not to reproduce it.
    """
    if not state.candidates:
        return state.advance(
            "C5",
            "no candidates were retrieved, so no call was made and the line abstains",
            None,
            result=GraphOutcome(
                rationale=(
                    "Retrieval found no commodity codes for this line, so there was "
                    "nothing to choose from. Scopes tried: "
                    f"{state.retrieval_scope or 'none'}."
                ),
                resolving_evidence=(
                    "A statement of what the product is made of and what it does, or a "
                    "commodity code from the supplier."
                ),
            ),
        )

    top_chapter = state.candidates[0].code[:2]
    result = _ask(
        ctx,
        state.line,
        "pick_code",
        {
            **_line_alone(state.line),
            "chapter_note": ctx.store.chapter_note(top_chapter),
            "candidate_codes": candidate_list(state.candidates, state.subheadings),
            "subheading_hint": ", ".join(state.subheadings) or NOTHING,
        },
        PickCode,
        PICK_TIER,
        "picking the final code",
    )
    answer = result.value
    rationale = answer.rationale.strip()
    if not rationale:
        raise ClassificationError(
            f"line {state.line.line_id}: the code pick returned no rationale. An "
            "abstention whose reason is blank tells the operator nothing, and a code "
            "whose reason is blank cannot be reviewed. There is no repair for this."
        )

    shared = {
        "material_decisive": answer.material_decisive,
        "material_assumed": answer.material_assumed.strip() or None,
        "resolving_evidence": answer.missing_evidence.strip() or None,
        "legal_basis": answer.legal_basis.strip() or None,
        "prompt_name": result.call.prompt_name,
        "prompt_version": result.call.prompt_version,
    }

    chosen = leaf_form(answer.chosen_code)
    by_code = {candidate.code: candidate for candidate in state.candidates}

    if answer.abstain or not answer.chosen_code.strip():
        return state.advance(
            "C5",
            f"abstained — {_excerpt(rationale)}",
            result.call,
            result=GraphOutcome(rationale=rationale, **shared),
        )

    if chosen is None or chosen not in by_code:
        return state.advance(
            "C5",
            f"answered {answer.chosen_code!r}, which is not one of the candidates; "
            "abstaining rather than substituting the top candidate",
            result.call,
            result=GraphOutcome(
                rationale=(
                    f"The pick named {answer.chosen_code!r}, which is not one of the "
                    f"{len(state.candidates)} codes retrieved from the nomenclature. A "
                    "code that was not retrieved has not been checked against the tree, "
                    "so it is not filed and no other candidate is substituted for it. "
                    f"The reason given was: {rationale}"
                ),
                **shared,
            ),
        )

    candidate = by_code[chosen]
    entry = ctx.store.entry(chosen)
    confidence = composite_confidence(
        similarity=candidate.similarity,
        candidates=state.candidates,
        code=chosen,
        self_report=answer.llm_confidence,
    )
    heading_agreement = agreement(state.candidates, chosen, AGREEMENT_HEADING_DIGITS)
    return state.advance(
        "C5",
        f"chose {chosen} at similarity {candidate.similarity:.4f}, self-report "
        f"{answer.llm_confidence:.2f}, composite {confidence:.4f}, heading agreement "
        f"{heading_agreement:.2f} — {_excerpt(rationale)}",
        result.call,
        result=GraphOutcome(
            code=chosen,
            confidence=confidence,
            rationale=rationale,
            needs_review=below_review_gate(
                confidence=confidence,
                heading_agreement=heading_agreement,
                confidence_floor=ctx.features.review_below_confidence,
                heading_agreement_floor=ctx.features.review_below_heading_agreement,
            ),
            supplementary_unit=entry.supplementary_unit if entry else None,
            **shared,
        ),
    )


# --- C6 ---------------------------------------------------------------------


def verify_pick(state: TraversalState, ctx: NodeContext) -> TraversalState:
    """A second opinion on the chosen code, seen alone. Veto only.

    It sees the code and its official path and *not* the alternatives, so it is asked an
    absolute question rather than the comparative one that made the original pick
    defensible. It can turn a pick into an abstention and can do nothing else.

    A veto drops the supplementary unit and keeps the material verdicts: the flow that
    asks an operator to state a material keys on those, and a veto is exactly when that
    question still needs asking.
    """
    outcome = state.result
    if outcome is None or outcome.code is None:
        return state.advance(
            "C6", "the pick abstained, so there is no code to verify and no call", None
        )

    entry = ctx.store.entry(outcome.code)
    result = _ask(
        ctx,
        state.line,
        "verify_code",
        {
            **_line_alone(state.line),
            "proposed_code": f"{outcome.code} — "
            f"{(entry.path_en if entry else None) or outcome.code}",
            "chapter_note": ctx.store.chapter_note(outcome.code[:2]),
        },
        VerifyCode,
        PICK_TIER,
        "verifying the chosen code",
    )
    answer = result.value
    if answer.correct:
        return state.advance(
            "C6",
            f"confirmed {outcome.code} — {_excerpt(answer.reason)}",
            result.call,
        )

    return state.advance(
        "C6",
        f"vetoed {outcome.code} — {_excerpt(answer.reason)}",
        result.call,
        verification_rejected=True,
        result=GraphOutcome(
            rationale=(
                f"An independent check rejected {outcome.code} "
                f"({(entry.path_en if entry else None) or 'no path available'}). "
                f"Reason: {answer.reason.strip()} The pick had been made for: "
                f"{outcome.rationale}"
            ),
            material_decisive=outcome.material_decisive,
            material_assumed=outcome.material_assumed,
            resolving_evidence=outcome.resolving_evidence,
            legal_basis=outcome.legal_basis,
            prompt_name=outcome.prompt_name,
            prompt_version=outcome.prompt_version,
        ),
    )


# --- C7 ---------------------------------------------------------------------


def reset_dead_end(state: TraversalState, ctx: NodeContext) -> TraversalState:
    """Clear the printed-code scope so the normal narrowing can run once.

    **The guard is structural, not a counter.** This node clears the very slot the entry
    branch tests, so the second pass cannot re-enter the fast path and cannot reach this
    node again. There is nothing to bound and nothing to reset a bound on.

    Every other slot the second pass needs is written unconditionally on the way through,
    so nothing else has to be cleared here. The attempted prefix survives in the step log.
    """
    attempted = state.printed_prefix
    reason = state.result.rationale if state.result is not None else "no result"
    return state.advance(
        "C7",
        f"the printed prefix {attempted} led nowhere ({_excerpt(reason)}); clearing the "
        "scope and narrowing normally, once",
        None,
        printed_prefix=None,
        verification_rejected=False,
    )


# --- shared helpers ---------------------------------------------------------


def _ask(
    ctx: NodeContext,
    line: ClassificationLine,
    prompt_name: str,
    values: dict[str, str],
    output: type[BaseModel],
    tier: ModelTier,
    what: str,
) -> ModelResult:
    """One model call. The first failure ends the line; nothing here tries again."""
    prompt = render_prompt(ctx.prompts_dir, prompt_name, values)
    try:
        return ctx.model.generate(tier=tier, prompt=prompt, output=output)
    except ModelError as exc:
        raise ClassificationError(
            f"line {line.line_id}: {what} for {line.source_name!r} failed: {exc}"
        ) from exc


def _line_with_context(line: ClassificationLine) -> dict[str, str]:
    """The line as the narrowing calls see it: with the trade context around it.

    The source language stops a foreign term being read as the English word it resembles,
    and the sibling summary tells a terse SKU line which trade it is in. Both measurably
    help chapter and heading choice.
    """
    return {
        **_line_core(line),
        "source_language": line.source_language.value,
        "sibling_lines": bullets(line.sibling_names),
    }


def _line_alone(line: ClassificationLine) -> dict[str, str]:
    """The line as the final pick and the verifier see it: on its own.

    The language tag and the sibling summary are withheld, because broad context
    measurably distracts leaf-level discrimination. The Armenian description already
    carries the correct reading of the foreign name — the description writer had the
    language tag and used it — so withholding it here costs nothing.
    """
    return _line_core(line)


def _line_core(line: ClassificationLine) -> dict[str, str]:
    return {
        "armenian_description": line.description_hy,
        "search_term": line.search_term_hy,
        "source_name": line.source_name,
        "unit_of_measure": value(line.unit),
        "trade_name": value(line.trade_name),
        "material": value(line.material),
        "printed_code": value(
            line.printed_code.value if line.printed_code else None
        ),
        "known_facts": bullets(line.grounding_facts),
    }


def _kept(
    offered: Iterable[str | None], is_known: Callable[[str], bool], limit: int
) -> tuple[str, ...]:
    """Normalized answers that name something real, deduplicated, in order, truncated.

    An answer that names nothing in the menu is dropped rather than raised on: the
    narrowing calls have no abstention, and a shortlist that came back empty degrades the
    search rather than failing the line.
    """
    kept: list[str] = []
    for code in offered:
        if code is None or code in kept or not is_known(code):
            continue
        kept.append(code)
        if len(kept) == limit:
            break
    return tuple(kept)


def _excerpt(text: str, limit: int = _TRACE_EXCERPT) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[:limit]}…"
