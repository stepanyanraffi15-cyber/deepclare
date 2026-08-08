"""A run's trace, printed.

The structured trace is the interface; this exists so a run can be read by a person with
no client, which is the same reason the review surface ships a renderer. It decides
nothing and re-derives nothing: every line here is a projection of a record.

The pinned versions come first and the unpinned list comes with them, because a reader
who does not know what the run held constant cannot read anything below.
"""

from __future__ import annotations

from deepclare.trace.records import NodeTrace, RunTrace

DISPLAY_WIDTH = 100
"""Where a rendered line is cut for the page. Nothing to do with the capture cap: the
record still holds whatever was captured."""

TOP_ALTERNATIVES = 5


def render_trace(trace: RunTrace, *, top_alternatives: int = TOP_ALTERNATIVES) -> str:
    lines: list[str] = []
    lines.extend(_header(trace))
    lines.extend(_manifest(trace))
    lines.extend(_policies(trace))
    lines.extend(_stages(trace, top_alternatives))
    lines.extend(_artifacts(trace))
    lines.extend(_notes(trace))
    lines.extend(_totals(trace))
    return "\n".join(lines)


def _header(trace: RunTrace) -> list[str]:
    finished = trace.finished_at.isoformat() if trace.finished_at else "(unfinished)"
    return [
        "=" * DISPLAY_WIDTH,
        f"RUN {trace.run_id}",
        f"case {trace.case_id}",
        f"started {trace.started_at.isoformat()}   finished {finished}",
        "=" * DISPLAY_WIDTH,
        "",
    ]


def _manifest(trace: RunTrace) -> list[str]:
    manifest = trace.manifest
    data = manifest.data
    lines = [
        "PINNED VERSIONS — what this run held constant",
        "-" * DISPLAY_WIDTH,
        f"  nomenclature vintage        : {data.nomenclature_vintage}",
        f"  nomenclature source         : {data.nomenclature_source}",
        f"  index build                 : {data.index_build_id}",
        f"  embedding                   : {data.embedding_model} @ {data.embedding_dimensions}d",
        f"  canonical text structure    : {data.canonical_text_structure_version}",
        f"  build                       : {manifest.code.build_identifier}",
    ]
    for pin in data.code_lists:
        lines.append(f"  code list {pin.name:<18}: {pin.value}")

    lines.append("  models per stage:")
    for stage in manifest.models.stages:
        served = f" (served by {stage.model_version})" if stage.model_version else ""
        decoding = (
            f" temp={stage.decoding.temperature} top_p={stage.decoding.top_p} "
            f"top_k={stage.decoding.top_k} seed={stage.decoding.seed}"
            if stage.decoding
            else " decoding NOT PINNED"
        )
        lines.append(
            f"    {stage.stage:<26}: {stage.model_id} [{stage.tier}]{served}{decoding}"
        )

    lines.append("  prompts:")
    for prompt in manifest.prompts:
        digest = prompt.content_hash or "no content hash"
        stage = f" @ {prompt.stage}" if prompt.stage else ""
        lines.append(f"    {prompt.name:<26}: v{prompt.version}{stage} ({digest})")

    lines.append("  configuration in force:")
    for pin in manifest.configuration.settings:
        lines.append(f"    {pin.name:<26}: {pin.value}")

    if manifest.environment.seeds:
        lines.append("  seeds:")
        for pin in manifest.environment.seeds:
            lines.append(f"    {pin.name:<26}: {pin.value}")
    for note in manifest.environment.notes:
        lines.append(f"  environment note: {note}")

    if manifest.evaluation:
        evaluation = manifest.evaluation
        lines.append("  evaluation:")
        lines.append(f"    golden set                : {evaluation.golden_set_version} / {evaluation.golden_set_partition}")
        lines.append(f"    label set                 : {evaluation.label_set_version}")
        lines.append(f"    canonicalization          : {evaluation.canonicalization_version}")
        lines.append(f"    metric definitions        : {evaluation.metric_definition_version}")

    lines.append("")
    lines.append("  axis fingerprints:")
    for axis, digest in manifest.fingerprints().items():
        lines.append(f"    {axis:<26}: {digest}")

    unpinned = manifest.unpinned()
    lines.append("")
    if unpinned:
        lines.append(f"  UNPINNED ({len(unpinned)}) — a comparison establishes nothing about these:")
        for item in unpinned:
            lines.append(f"    - {item}")
    else:
        lines.append("  UNPINNED: none")

    drift = trace.pin_drift()
    if drift:
        lines.append("")
        lines.append(f"  PIN DRIFT ({len(drift)}) — what answered is not what was pinned:")
        for item in drift:
            lines.append(f"    ! {item}")
    lines.append("")
    return lines


def _policies(trace: RunTrace) -> list[str]:
    return [
        "POLICIES",
        "-" * DISPLAY_WIDTH,
        f"  {trace.capture.statement()}",
        f"  {trace.retention.statement()}",
        "",
    ]


def _stages(trace: RunTrace, top_alternatives: int) -> list[str]:
    lines = ["STAGES", "-" * DISPLAY_WIDTH]
    if not trace.nodes:
        lines.append("  no node records — capture level is off")
        lines.append("")
        return lines

    for stage in trace.stages:
        tokens = stage.tokens
        lines.append(
            f"  {stage.stage}  —  {len(stage.nodes)} node(s), {stage.wall_clock_ms:.0f} ms, "
            f"{tokens.calls} model call(s), {tokens.total_tokens} tokens"
        )
        for node in stage.nodes:
            lines.extend(_node(node, top_alternatives))
        lines.append("")
    return lines


def _node(node: NodeTrace, top_alternatives: int) -> list[str]:
    line = node.line_id or "-"
    head = (
        f"    #{node.sequence:<4} {node.node:<24} line {line:<4} "
        f"{node.outcome.value:<9} {node.wall_clock_ms:7.1f} ms"
    )
    if node.attempt > 1:
        head += f"  attempt {node.attempt}"
    if not node.sampled:
        head += "  [content sampled away]"
    lines = [head]

    if node.decision:
        lines.append(f"           decision   : {_cut(node.decision)}")
    if node.abstention:
        lines.append(f"           abstention : {node.abstention.value}")
    if node.degradation:
        lines.append(f"           degraded   : {_cut(node.degradation)}")
    if node.error:
        lines.append(f"           error      : {_cut(node.error)}")
    if node.call:
        call = node.call
        usage = call.usage
        lines.append(
            f"           model      : {call.model_id} [{call.tier.value}] "
            f"prompt {call.prompt_name} v{call.prompt_version}"
        )
        lines.append(
            f"           tokens     : in {usage.prompt_tokens} out {usage.output_tokens} "
            f"reasoning {usage.reasoning_tokens} total {usage.total_tokens}"
        )
    if node.retrieval:
        lines.extend(_retrieval(node, top_alternatives))
    for superseded in node.superseded:
        lines.append(
            f"           superseded : {superseded.slot} held {superseded.previous!r} "
            f"— {superseded.reason}"
        )
    if node.entry_state:
        lines.append(f"           entry      : {_cut(str(node.entry_state))}")
    if node.exit_state:
        lines.append(f"           exit       : {_cut(str(node.exit_state))}")
    if node.payload:
        for label, text in (("prompt", node.payload.prompt), ("response", node.payload.response)):
            if text is not None:
                mark = " (truncated)" if node.payload.truncated else ""
                lines.append(f"           {label:<10} : {_cut(text)}{mark}")
    return lines


def _retrieval(node: NodeTrace, top_alternatives: int) -> list[str]:
    retrieval = node.retrieval
    assert retrieval is not None
    scope = retrieval.scope or "unscoped"
    lines = [
        f"           retrieval  : {len(retrieval.alternatives)} candidate(s), scope {scope}, "
        f"query {_cut(retrieval.query, 60)!r}"
    ]
    if retrieval.dropped_unknown_codes:
        lines.append(
            f"                        {retrieval.dropped_unknown_codes} hit(s) dropped — "
            "the index halves disagree"
        )
    if retrieval.known_correct_code:
        rank = retrieval.correct_rank
        where = f"rank {rank}" if rank else "NOT RETRIEVED"
        lines.append(
            f"                        correct code {retrieval.known_correct_code}: {where}"
        )
    for alternative in retrieval.alternatives[:top_alternatives]:
        mark = "*" if alternative.chosen else " "
        lines.append(
            f"                      {mark} {alternative.rank:>3}. {alternative.code}  "
            f"{alternative.score:.4f}"
        )
    remaining = len(retrieval.alternatives) - top_alternatives
    if remaining > 0:
        lines.append(f"                        … {remaining} more")
    return lines


def _artifacts(trace: RunTrace) -> list[str]:
    if not trace.artifacts:
        return []
    lines = ["RETAINED ARTIFACTS", "-" * DISPLAY_WIDTH]
    for artifact in trace.artifacts:
        lines.append(
            f"  {artifact.kind.value:<24} {artifact.name:<32} {artifact.byte_count:>9} B  "
            f"manifest {artifact.manifest_fingerprint}"
        )
    lines.append("")
    return lines


def _notes(trace: RunTrace) -> list[str]:
    if not trace.notes:
        return []
    return ["NOTES", "-" * DISPLAY_WIDTH, *(f"  {note}" for note in trace.notes), ""]


def _totals(trace: RunTrace) -> list[str]:
    tokens = trace.tokens
    return [
        "TOTALS",
        "-" * DISPLAY_WIDTH,
        f"  nodes         : {len(trace.nodes)}",
        f"  model calls   : {tokens.calls}",
        f"  tokens        : in {tokens.prompt_tokens}, out {tokens.output_tokens}, "
        f"reasoning {tokens.reasoning_tokens}, total {tokens.total_tokens}",
        f"  wall clock    : {trace.wall_clock_ms:.0f} ms across nodes",
        "",
    ]


def _cut(text: str, width: int = DISPLAY_WIDTH - 24) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= width else f"{collapsed[:width]}…"
