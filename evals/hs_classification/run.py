"""Full-corpus classification sweep: M8 description -> M9 cascade -> 10-digit code.

Makes real, billed provider calls. NOT collected by pytest. Designed to be left running
in tmux and resumed after a crash.

    .venv/bin/python -m evals.hs_classification.run --workers 8 --line-workers 8

RESUMABILITY. Every line is keyed `<case>:<line_id>` and appended to results.jsonl the
moment it finishes. On start the harness reads that file and skips what is already there,
so a crash costs at most the lines in flight. Written descriptions are cached separately
in descriptions.jsonl for the same reason: M8 output is a billed call, and
build_classification_lines() needs a description for *every* line in a case before it can
classify *any* of them -- without the cache, resuming mid-case would re-pay for the lines
already done.

CONCURRENCY. Parallel across cases, sequential within one. A case is the unit because
sibling context is built from the whole invoice, so lines of a case must be prepared
together. Two shared resources are guarded: the local Qdrant client (file-backed, not
safe for concurrent use) and the two append-only files.

RATE LIMITS. models.py deliberately does not retry -- it "translates the first
exception", which is right for a run path and wrong for a batch job. So backoff lives
here, outside the module, and only wraps transport errors. A line that still fails after
its retries is recorded with its error rather than dropped, so the results file always
accounts for every line attempted.
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

import qdrant_client

from deepclare.classification import Classifier, build_classification_lines
from deepclare.config import load_settings
from deepclare.description import DescriptionWriter, LineDescription, build_line_contexts
from deepclare.domain import (
    InvoiceGoodsLine,
    InvoiceRecord,
    Provenance,
    Traced,
    ValueOrigin,
)
from deepclare.embedding import GeminiEmbedder
from deepclare.models import ModelError, ModelTransportError
from deepclare.models import GenerativeModel
from deepclare.reference.store import NomenclatureStore

ROOT = pathlib.Path(__file__).resolve().parents[2]
CORPUS = ROOT / "evalkit" / "corpus" / "oneToOne"
EXTRACTED = Provenance(origin=ValueOrigin.EXTRACTED, source_document_id="invoice")

# Confirmed absent from the live tariff: unreachable labels, recorded but not scored.
FABRICATED = {"39069090090", "39100000090", "39269097098"}

MAX_ATTEMPTS = 5
LINE_WORKERS = 8  # concurrent lines inside one case; total = --workers x this
ALLOWED: set[str] | None = None  # when set, only these <case>:<line_id> keys run
CHAPTERS: set[str] | None = None  # when set, only gold codes in these chapters run
logger = logging.getLogger("sweep")

_qdrant_lock = threading.Lock()
_write_lock = threading.Lock()


def backoff(what: str, fn, *args, **kwargs):
    """Retry transport failures only. A refusal or a bad output is not transient."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return fn(*args, **kwargs)
        except ModelTransportError as exc:
            if attempt == MAX_ATTEMPTS:
                raise
            wait = min(60.0, 2.0**attempt) + random.uniform(0, 1.5)
            logger.warning("%s: %s -- retry %d/%d in %.1fs",
                           what, str(exc)[:120], attempt, MAX_ATTEMPTS, wait)
            time.sleep(wait)
    raise RuntimeError("unreachable")


class Sink:
    """Append-only JSONL with an in-memory index of what is already done."""

    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        self.done: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.done[row["id"]] = row

    def add(self, row: dict) -> None:
        with _write_lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            self.done[row["id"]] = row


def build_record(case: str, goods: list[dict]) -> InvoiceRecord:
    return InvoiceRecord(
        source_document_id=case,
        goods_lines=tuple(
            InvoiceGoodsLine(
                line_id=str(i + 1),
                description=Traced[str](value=g["source_name"], provenance=EXTRACTED),
                unit=Traced[str](value=str(g["unit"]), provenance=EXTRACTED),
                unit_price=Traced[Decimal](
                    value=Decimal(str(g["unit_price"])), provenance=EXTRACTED
                ),
            )
            for i, g in enumerate(goods)
        ),
    )


def run_case(case: str, writer, classifier, results: Sink, descs: Sink) -> tuple[int, int]:
    goods = json.loads((CORPUS / case / "ir.json").read_text())["goods"]
    record = build_record(case, goods)
    contexts = {c.line_id: c for c in build_line_contexts(record, ())}
    if CHAPTERS is not None:
        contexts = {k: v for k, v in contexts.items()
                    if goods[int(k) - 1]["hs_code"][:2] in CHAPTERS}
    if ALLOWED is not None:
        contexts = {k: v for k, v in contexts.items() if f'{case}:{k}' in ALLOWED}
    if not contexts:
        return 0, 0

    # M8 for every line -- classification needs the full set -- but only pay for
    # the ones not already cached from a previous run.
    # M8 per line. A line whose description is refused must not cost the whole case:
    # DescriptionError is a *correct* refusal (e.g. a figure in the text that no source
    # document states, which would be a false statement to customs), so it is recorded
    # and that one line dropped, rather than retried or allowed to abort 500 siblings.
    written: list[LineDescription] = []
    ok_ids: set[str] = set()
    failed = 0

    def one_description(item):
        line_id, context = item
        key = f"{case}:{line_id}"
        cached = descs.done.get(key)
        if cached is not None:
            return line_id, LineDescription.model_validate(cached["payload"]), None
        try:
            result = backoff(f"{key} M8", writer.write, context)
        except Exception as exc:  # noqa: BLE001 - a refusal costs one line, not the case
            return line_id, None, exc
        descs.add({"id": key, "case": case, "line_id": line_id,
                   "payload": result.model_dump(mode="json")})
        return line_id, result, None

    # Descriptions are independent per line, so fan them out. Order is restored below.
    with ThreadPoolExecutor(max_workers=LINE_WORKERS) as inner:
        prepared = list(inner.map(one_description, contexts.items()))

    for line_id, result, exc in prepared:
        key = f"{case}:{line_id}"
        if exc is not None:
            failed += 1
            if key not in results.done:
                gold = goods[int(line_id) - 1]
                results.add({"id": key, "case": case, "line_id": line_id,
                             "source_name": gold["source_name"], "gold": gold["hs_code"],
                             "stage": "M8",
                             "error": f"{type(exc).__name__}: {exc}"[:300]})
            logger.error("%s M8 FAILED %s", key, str(exc)[:160])
            continue
        written.append(result)
        ok_ids.add(line_id)

    if not ok_ids:
        return 0, failed
    # build_classification_lines() demands a description for every goods line, so the
    # record it sees must contain only the lines that have one.
    usable = InvoiceRecord(
        source_document_id=record.source_document_id,
        goods_lines=tuple(g for g in record.goods_lines if g.line_id in ok_ids),
    )
    lines = build_classification_lines(usable, written, ())
    def one_line(subject):
        # `lines` is filtered, so gold must be looked up by id, not zipped by position.
        gold = goods[int(subject.line_id) - 1]
        key = f"{case}:{subject.line_id}"
        if key in results.done:
            return 0, 0
        started = time.time()
        try:
            outcome = backoff(f"{key} M9", classifier.classify, subject)
        except ModelError as exc:
            results.add({"id": key, "case": case, "line_id": subject.line_id,
                         "source_name": gold["source_name"], "gold": gold["hs_code"],
                         "stage": "M9",
                         "error": f"{type(exc).__name__}: {exc}"[:300],
                         "elapsed_s": round(time.time() - started, 1)})
            logger.error("%s FAILED %s", key, str(exc)[:160])
            return 0, 1
        code = outcome.code.value if outcome.code else None
        want = gold["hs_code"][:-1]
        results.add({
            "id": key, "case": case, "line_id": subject.line_id,
            "source_name": gold["source_name"],
            "description_hy": subject.description_hy,
            "gold": gold["hs_code"], "gold_10": want,
            "predicted": code,
            "correct_10": code == want,
            "correct_6": bool(code) and code[:6] == want[:6],
            "correct_4": bool(code) and code[:4] == want[:4],
            "abstained": code is None,
            "unreachable_label": gold["hs_code"] in FABRICATED,
            "decided_by": str(getattr(outcome, "decided_by", "")),
            # Per-node token usage. LineClassification.steps[].call carries a full
            # ModelCall; without recording it a run cannot be costed afterwards,
            # which is exactly the gap that made the last spend unaccountable.
            "usage": [
                {"node": st.node, "model": st.call.model_id, "tier": str(st.call.tier),
                 "in": st.call.usage.prompt_tokens, "out": st.call.usage.output_tokens,
                 "reasoning": st.call.usage.reasoning_tokens}
                for st in getattr(outcome, "steps", ()) if st.call is not None
            ],
            "confidence": getattr(outcome, "confidence", None),
            "elapsed_s": round(time.time() - started, 1),
        })
        return 1, 0

    # The specification states the traversal is "per line and independent", so lines
    # of a case fan out too. Without this a 554-line case is one thread and dominates
    # the whole sweep no matter how many case workers there are.
    with ThreadPoolExecutor(max_workers=LINE_WORKERS) as inner:
        tallies = list(inner.map(one_line, lines))
    done = sum(a for a, _ in tallies)
    failed += sum(b for _, b in tallies)
    return done, failed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4, help="concurrent cases")
    ap.add_argument("--line-workers", type=int, default=8, help="concurrent lines per case")
    ap.add_argument("--lines", type=int, default=0, help="cap total lines (round-robin across cases); 0 = all")
    ap.add_argument("--chapters", default="",
                    help="comma-separated 2-digit chapters to keep. Selecting a subset by "
                         "measured performance makes the score a property of the selection: "
                         "quote it as 'precision on chapters X,Y', never as a headline.")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "sweep_out")
    ap.add_argument("--cases", type=int, default=0, help="0 = all")
    ap.add_argument("--provider", choices=("gemini", "deepseek"), default="gemini")
    ap.add_argument("--all-pro", action="store_true",
                    help="deepseek only: use v4-pro for every tier, not just strong")
    ap.add_argument("--reasoning-tiers", default="strong",
                    help="deepseek only: comma-separated tiers that reason "
                         "(cheap,standard,strong | none). Measured: 21x cost, 12x latency.")
    args = ap.parse_args()
    global LINE_WORKERS, CHAPTERS
    LINE_WORKERS = args.line_workers
    if args.chapters:
        CHAPTERS = {c.strip() for c in args.chapters.split(",") if c.strip()}

    args.out.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(args.out / "run.log"),
                  logging.StreamHandler()],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    from evals.common.manifest import build as build_manifest, write as write_manifest

    results = Sink(args.out / "results.jsonl")
    descs = Sink(args.out / "descriptions.jsonl")

    cases = sorted(p.name for p in CORPUS.glob("case-*"))
    if args.lines:
        # Round-robin across cases: taking the first N lines of case-001 would be one
        # product family and would not generalise.
        buckets = [[f"{c}:{i + 1}" for i in range(
            len(json.loads((CORPUS / c / "ir.json").read_text())["goods"]))] for c in cases]
        picked: list[str] = []
        depth = 0
        while len(picked) < args.lines and any(len(b) > depth for b in buckets):
            for bucket in buckets:
                if depth < len(bucket) and len(picked) < args.lines:
                    picked.append(bucket[depth])
            depth += 1
        global ALLOWED
        ALLOWED = set(picked)
        cases = sorted({k.split(":")[0] for k in ALLOWED})
    if args.cases:
        cases = cases[: args.cases]
    def _count(case_name: str) -> int:
        goods = json.loads((CORPUS / case_name / "ir.json").read_text())["goods"]
        if CHAPTERS is not None:
            goods = [g for g in goods if g["hs_code"][:2] in CHAPTERS]
        return len(goods)

    total = len(ALLOWED) if ALLOWED else sum(_count(c) for c in cases)
    logger.info("corpus %d cases / %d lines | already done %d | workers %d",
                len(cases), total, len(results.done), args.workers)

    settings = load_settings()
    client = qdrant_client.QdrantClient(path=str(settings.qdrant_path))
    store = NomenclatureStore(
        artifact_dir=settings.reference_dir,
        qdrant_client=client,
        collection=settings.qdrant_collection,
        embedder=GeminiEmbedder(settings),
    )
    # The local Qdrant client is file-backed; serialise every search across workers.
    raw_search = store.search
    store.search = lambda *a, **k: _locked(raw_search, *a, **k)  # type: ignore[method-assign]

    if args.provider == "deepseek":
        models = {"cheap": "deepseek/deepseek-v4-flash",
                  "standard": "deepseek/deepseek-v4-flash",
                  "strong": "deepseek/deepseek-v4-pro"}
        if args.all_pro:
            models = {k: "deepseek/deepseek-v4-pro" for k in models}
    else:
        models = {"cheap": settings.genai_model_cheap,
                  "standard": settings.genai_model_standard,
                  "strong": settings.genai_model_strong}
    write_manifest(args.out / "manifest.json", build_manifest(
        eval_name="hs_classification",
        provider=args.provider,
        models=models,
        extra={
            "reasoning_tiers": args.reasoning_tiers if args.provider == "deepseek" else "n/a",
            "workers": args.workers, "line_workers": args.line_workers,
            "lines_requested": args.lines or "all",
            "corpus": str(CORPUS.relative_to(ROOT)),
            "nomenclature_vintage": store.vintage,
            "embedding": f"{store.embedding_pairing[0]}@{store.embedding_pairing[1]}",
            "fabricated_codes_skipped": sorted(FABRICATED),
            "chapters_filter": sorted(CHAPTERS) if CHAPTERS else "all",
            "chapter_selection_rule": (
                "chapters with >=15 committed lines and >=70% exact-10 precision in "
                "runs/hs_deepseek_flash_baseline; selected on measured performance, so "
                "the resulting score is in-sample for this slice"
            ) if CHAPTERS else None,
        },
    ))

    started = time.time()
    if args.provider == "deepseek":
        import re as _re
        sys.path.insert(0, str(ROOT))
        from evals.common.deepseek_model import DeepSeekModel
        key_src = (ROOT / ".env").read_text()
        key = _re.search(r"OPENROUTER_API_KEY=(sk-or-v1-[A-Za-z0-9]+)", key_src)
        if not key:
            raise SystemExit("OPENROUTER_API_KEY not found in .env")
        from deepclare.models import ModelTier as _T
        picked = frozenset(
            _T(name.strip()) for name in args.reasoning_tiers.split(",")
            if name.strip() and name.strip() != "none"
        )
        logger.info("deepseek reasoning enabled for tiers: %s", sorted(t.value for t in picked) or "none")
        tiers = None
        if args.all_pro:
            from evals.common.deepseek_model import DEFAULT_TIERS
            tiers = {t: "deepseek/deepseek-v4-pro" for t in DEFAULT_TIERS}
        make_model = lambda: DeepSeekModel(settings, key.group(1),
                                           reasoning_tiers=picked, tiers=tiers)
    else:
        make_model = lambda: GenerativeModel(settings)

    with make_model() as model:
        writer = DescriptionWriter(model, settings.prompts_dir)
        classifier = Classifier(store=store, model=model, prompts_dir=settings.prompts_dir)
        logger.info("features %s", classifier.features.model_dump())

        completed = failures = 0
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(run_case, c, writer, classifier, results, descs): c
                for c in cases
            }
            for future in as_completed(futures):
                case = futures[future]
                try:
                    did, failed = future.result()
                except Exception as exc:  # a case-level failure must not kill the sweep
                    logger.exception("case %s aborted: %s", case, str(exc)[:200])
                    continue
                completed += did
                failures += failed
                rate = completed / max(1e-9, time.time() - started) * 60
                logger.info("case %s done (+%d, %d failed) | total done %d/%d | %.1f lines/min",
                            case, did, failed, len(results.done), total, rate)

    logger.info("sweep finished: %d newly classified, %d failed, %d in results.jsonl",
                completed, failures, len(results.done))


def _locked(fn, *args, **kwargs):
    with _qdrant_lock:
        return fn(*args, **kwargs)


if __name__ == "__main__":
    main()
