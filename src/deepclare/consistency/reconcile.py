"""The pass itself: critic, then rewriter, then everything that says no.

    critique  ──fails──▶  the whole pass is abandoned. No flags, no changes.
        │
        ├──no issues──▶   no rewrite is requested. No model call is wasted.
        │
        ▼
    rewrite   ──fails or is discarded──▶  the flags stand, the lines do not move.
        │
        ▼
    guardrails ──per line──▶  a refused proposal is dropped; the drafted line stands.
        │
        ▼
    existence gate ──per changed code──▶  a code that is not in the nomenclature is not
                                          filed, and the drafted code stays.

Read the diagram as the module's contract rather than as its control flow: **every** exit
above leaves a filable declaration, and the only difference between them is how much of
the draft got improved. This module improves consistency; it is never the reason a run
fails.

Three rules are enforced here rather than asked for:

* **A code is never blanked and never conjured.** An empty code from the model is a
  no-op. A line where classification abstained keeps its abstention — the abstention was
  reasoned, this pass has no new evidence, and filling it from a sibling would replace a
  stated reason with a guess. The critic's finding still reaches the operator as a review
  item naming the sibling's code, so the inconsistency is not lost, only left to a human.
* **A changed code re-enters the existence gate**, the same one classification owns, and
  carries a review item. Nothing that leaves this module has skipped that check.
* **A changed code takes its supplementary unit with it.** The unit was read off the entry
  for the *previous* code, so keeping it would file a tariff unit belonging to a different
  code. This module may not read the nomenclature for anything but the existence check, so
  it clears the unit and flags it rather than looking a new one up or asking a model to
  state one.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path

from deepclare.classification import ExistenceGate, LineClassification
from deepclare.consistency.critic import ConsistencyCritic
from deepclare.consistency.errors import ConsistencyError
from deepclare.consistency.guards import collapsed_lines, refusal_for_description
from deepclare.consistency.records import (
    CONCEPT_BY_FIELD,
    SHIPMENT_CONCEPT,
    STAGE,
    ConsistencyField,
    ConsistencyOutcome,
    Critique,
    DraftedLine,
    LineChange,
    PassOutcome,
    ReconciledLine,
    RejectedRewrite,
    untouched,
)
from deepclare.consistency.rewriter import ConsistencyRewriter, LineProposal
from deepclare.domain import (
    Provenance,
    ReviewItem,
    ReviewKind,
    Traced,
    Transform,
    ValueOrigin,
)
from deepclare.models import GenerativeModel, ModelCall


class Reconciler:
    """Reconciles one shipment's drafted lines against one another.

    The existence gate arrives as an argument rather than the nomenclature store, and
    that is the module boundary made structural: reconciliation may reach the reference
    data through the same existence check classification owns, and through nothing else.
    """

    def __init__(
        self,
        *,
        existence_gate: ExistenceGate,
        model: GenerativeModel,
        prompts_dir: Path,
    ) -> None:
        self._existence_gate = existence_gate
        self._critic = ConsistencyCritic(model, prompts_dir)
        self._rewriter = ConsistencyRewriter(model, prompts_dir)

    def reconcile(self, lines: Sequence[DraftedLine]) -> ConsistencyOutcome:
        """Every line back, changed or not, with the account of what happened."""
        _refuse_a_batch_that_is_not_one_shipment(lines)

        if len(lines) < 2:
            return untouched(
                lines,
                outcome=PassOutcome.NOT_ATTEMPTED,
                detail="fewer than two goods lines: a line is consistent with itself, "
                "so no call was made.",
            )

        critique = self._critic.critique(lines)
        if critique is None:
            return untouched(
                lines,
                outcome=PassOutcome.CRITIQUE_FAILED,
                detail="the critique call did not land, so the whole pass was abandoned: "
                "no rewrite was requested, no flags were produced, and the drafted lines "
                "are filed as they were drafted.",
            )

        notes = _shipment_items(critique.shipment_notes)
        if not critique.issues:
            return untouched(
                lines,
                outcome=PassOutcome.NOTHING_TO_DO,
                detail="the critic found no inconsistency between the lines, so no "
                "rewrite was requested.",
                review_items=notes,
                shipment_notes=critique.shipment_notes,
                calls=(critique.call,),
            )

        attempt = self._rewriter.rewrite(lines, critique)
        flags = _items_for_issues(critique) + notes
        calls = tuple(call for call in (critique.call, attempt.call) if call is not None)

        if not attempt.usable:
            return untouched(
                lines,
                outcome=(
                    PassOutcome.REWRITE_FAILED
                    if attempt.call is None
                    else PassOutcome.REWRITE_DISCARDED
                ),
                detail=f"{attempt.discarded_because}. The critique's flags are kept and "
                "nothing was changed.",
                review_items=flags,
                shipment_notes=critique.shipment_notes,
                calls=calls,
            )

        return self._apply(
            lines=lines,
            critique=critique,
            proposals=attempt.proposals,
            rewrite_call=attempt.call,
            notes=notes,
            calls=calls,
        )

    # --- applying an accepted rewrite ---------------------------------------

    def _apply(
        self,
        *,
        lines: Sequence[DraftedLine],
        critique: Critique,
        proposals: Sequence[LineProposal],
        rewrite_call: ModelCall | None,
        notes: tuple[ReviewItem, ...],
        calls: tuple[ModelCall, ...],
    ) -> ConsistencyOutcome:
        by_line = {proposal.line_id: proposal for proposal in proposals}
        reasons = _reasons_by_line_and_field(critique)
        rejected: list[RejectedRewrite] = []

        texts = self._conformed_texts(lines, by_line, rejected)
        changes: list[LineChange] = []
        reconciled: list[ReconciledLine] = []

        for line in lines:
            changed: list[ConsistencyField] = []
            text = texts[line.line_id]
            if text != line.description:
                changed.append(ConsistencyField.DESCRIPTION)
                changes.append(
                    _change(
                        line.line_id,
                        ConsistencyField.DESCRIPTION,
                        "conform-description",
                        line.description,
                        text,
                        reasons,
                    )
                )

            code, unit = line.code, line.supplementary_unit
            proposed = by_line[line.line_id].code
            settled = self._settle_code(line, proposed, rewrite_call, rejected)
            if settled is not None:
                changed.append(ConsistencyField.CODE)
                changes.append(
                    _change(
                        line.line_id,
                        ConsistencyField.CODE,
                        "align-code",
                        line.code or "",
                        settled,
                        reasons,
                    )
                )
                code = settled
                if unit is not None:
                    changed.append(ConsistencyField.SUPPLEMENTARY_UNIT)
                    changes.append(
                        LineChange(
                            line_id=line.line_id,
                            field=ConsistencyField.SUPPLEMENTARY_UNIT,
                            transform=Transform(
                                operation="clear-supplementary-unit",
                                before=unit,
                                after="",
                                reason=f"the commodity code changed to {settled}, and "
                                f"{unit!r} is the tariff's unit for {line.code}",
                            ),
                        )
                    )
                    unit = None

            reconciled.append(
                ReconciledLine(
                    line_id=line.line_id,
                    description=text,
                    code=code,
                    supplementary_unit=unit,
                    changed_fields=tuple(changed),
                )
            )

        return ConsistencyOutcome(
            outcome=PassOutcome.APPLIED,
            detail=_summary(changes, rejected),
            lines=tuple(reconciled),
            changes=tuple(changes),
            rejected=tuple(rejected),
            review_items=_items(critique, changes, notes),
            shipment_notes=critique.shipment_notes,
            calls=calls,
        )

    def _conformed_texts(
        self,
        lines: Sequence[DraftedLine],
        by_line: dict[str, LineProposal],
        rejected: list[RejectedRewrite],
    ) -> dict[str, str]:
        """The final text of every line: the proposal where it survived, else the draft."""
        drafted = {line.line_id: line.description for line in lines}
        resulting = dict(drafted)

        for line in lines:
            proposed = by_line[line.line_id].description.strip()
            if not proposed or proposed == line.description:
                continue
            refusal = refusal_for_description(line, proposed)
            if refusal is not None:
                rejected.append(
                    RejectedRewrite(
                        line_id=line.line_id,
                        field=ConsistencyField.DESCRIPTION,
                        proposed=proposed,
                        reason=refusal,
                    )
                )
                continue
            resulting[line.line_id] = proposed

        for line_id in sorted(collapsed_lines(drafted, resulting)):
            rejected.append(
                RejectedRewrite(
                    line_id=line_id,
                    field=ConsistencyField.DESCRIPTION,
                    proposed=resulting[line_id],
                    reason="the rewrite would make this line read exactly like another "
                    "line that was drafted differently, and two goods the declaration "
                    "cannot tell apart are worse than two lines worded unlike each other",
                )
            )
            resulting[line_id] = drafted[line_id]

        return resulting

    def _settle_code(
        self,
        line: DraftedLine,
        proposed: str,
        rewrite_call: ModelCall | None,
        rejected: list[RejectedRewrite],
    ) -> str | None:
        """The code this line should now carry, or `None` for "leave it alone"."""
        if not proposed:
            return None
        if line.code is None:
            rejected.append(
                RejectedRewrite(
                    line_id=line.line_id,
                    field=ConsistencyField.CODE,
                    proposed=proposed,
                    reason="classification abstained on this line for a stated reason, "
                    "and reconciliation has no evidence classification did not have. "
                    "The finding is raised for a human instead",
                )
            )
            return None

        gated = self._gate(line, proposed, rewrite_call)
        if gated.code is None:
            rejected.append(
                RejectedRewrite(
                    line_id=line.line_id,
                    field=ConsistencyField.CODE,
                    proposed=proposed,
                    reason=gated.rationale,
                )
            )
            return None
        return None if gated.code.value == line.code else gated.code.value

    def _gate(
        self, line: DraftedLine, proposed: str, rewrite_call: ModelCall | None
    ) -> LineClassification:
        """Send the proposed code back through the check classification owns.

        Built as the record that check takes, rather than by calling something narrower,
        so that the 11-digit reduction and the four rejection reasons behave here exactly
        as they behave when a code is first assigned.
        """
        return self._existence_gate.check(
            LineClassification(
                line_id=line.line_id,
                code=Traced[str](
                    value=proposed,
                    provenance=Provenance(
                        origin=ValueOrigin.GENERATED,
                        stage=STAGE,
                        prompt_name=rewrite_call.prompt_name if rewrite_call else STAGE,
                        prompt_version=(
                            rewrite_call.prompt_version if rewrite_call else "unknown"
                        ),
                    ),
                ),
                needs_review=True,
                rationale=(
                    f"Cross-line reconciliation proposed {proposed} in place of "
                    f"{line.code}, to agree with the other lines of this shipment."
                ),
                decided_by=STAGE,
            )
        )


def _refuse_a_batch_that_is_not_one_shipment(lines: Sequence[DraftedLine]) -> None:
    """Two lines with one id are a caller defect, not a degradation to work around.

    Every join in this pass is by line id — the proposals, the findings, the guardrails.
    A repeated id makes all three ambiguous, and quietly picking one would attach a
    rewrite to the wrong goods.
    """
    counted = Counter(line.line_id for line in lines)
    repeated = sorted(line_id for line_id, times in counted.items() if times > 1)
    if repeated:
        raise ConsistencyError(
            f"line id(s) {', '.join(repeated)} appear more than once in the batch. "
            "Reconciliation joins the critique, the rewrite and the guardrails by line "
            "id, so a repeated id would attach one line's rewrite to another's goods."
        )


def _change(
    line_id: str,
    field: ConsistencyField,
    operation: str,
    before: str,
    after: str,
    reasons: dict[tuple[str, ConsistencyField], str],
) -> LineChange:
    return LineChange(
        line_id=line_id,
        field=field,
        transform=Transform(
            operation=operation,
            before=before,
            after=after,
            reason=reasons.get(
                (line_id, field),
                "conformed to the other lines of this shipment",
            ),
        ),
    )


def _reasons_by_line_and_field(
    critique: Critique,
) -> dict[tuple[str, ConsistencyField], str]:
    """The critic's own words for why a field was flagged, keyed the way changes are.

    First finding wins: two findings against one field of one line are two statements of
    the same problem, and a transform records one reason.
    """
    reasons: dict[tuple[str, ConsistencyField], str] = {}
    for issue in critique.issues:
        reasons.setdefault((issue.line_id, issue.field), issue.problem)
    return reasons


def _items(
    critique: Critique,
    changes: Sequence[LineChange],
    notes: tuple[ReviewItem, ...],
) -> tuple[ReviewItem, ...]:
    """One item per line and concept the pass touched or flagged.

    A change and a finding about the same field of the same line are one thing for an
    operator to look at, so the change wins: it says what the declaration now contains,
    which is what a human confirms, and it carries the finding's wording as its reason.
    """
    by_key: dict[tuple[str, str], ReviewItem] = {}
    for issue in critique.issues:
        concept = CONCEPT_BY_FIELD[issue.field]
        by_key[(issue.line_id, concept)] = ReviewItem(
            kind=ReviewKind.NEEDS_REVIEW,
            concept=concept,
            detail=f"Cross-line review flagged this against the other lines of the "
            f"shipment: {issue.problem} Nothing was changed.",
            line_id=issue.line_id,
            remedy=issue.suggested_value,
        )
    for change in changes:
        concept = CONCEPT_BY_FIELD[change.field]
        by_key[(change.line_id, concept)] = ReviewItem(
            kind=ReviewKind.NEEDS_REVIEW,
            concept=concept,
            detail=_change_detail(change),
            line_id=change.line_id,
            remedy="Confirm the change, or restore what was drafted.",
        )
    return notes + tuple(
        by_key[key] for key in sorted(by_key, key=lambda key: (int(key[0]), key[1]))
    )


def _items_for_issues(critique: Critique) -> tuple[ReviewItem, ...]:
    """The flags on their own, for the paths where no rewrite was applied."""
    return _items(critique, (), ())


def _change_detail(change: LineChange) -> str:
    transform = change.transform
    if change.field is ConsistencyField.SUPPLEMENTARY_UNIT:
        return (
            f"The supplementary unit {transform.before!r} was removed because "
            f"{transform.reason}. It is resolved again from the nomenclature entry for "
            "the new code."
        )
    was = transform.before or "nothing"
    return (
        f"Changed by cross-line review from {was!r} to {transform.after!r}, because "
        f"{transform.reason}"
    )


def _shipment_items(notes: Iterable[str]) -> tuple[ReviewItem, ...]:
    return tuple(
        ReviewItem(
            kind=ReviewKind.NEEDS_REVIEW,
            concept=SHIPMENT_CONCEPT,
            detail=note,
            line_id=None,
        )
        for note in notes
    )


def _summary(
    changes: Sequence[LineChange], rejected: Sequence[RejectedRewrite]
) -> str:
    touched = len({change.line_id for change in changes})
    return (
        f"the rewrite was accepted: {touched} line(s) changed across "
        f"{len(changes)} field(s), {len(rejected)} proposal(s) refused by a guardrail."
    )
