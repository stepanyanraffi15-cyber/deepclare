"""Conformance: everything about the document that can be judged before it is filed.

The external system's diagnostics are a wrong-format rejection naming no field, a hang at
100% with no message, and a silent value drop. None of the three is diagnosable from the
response, which is why every check that can be made offline is made here.

This is deliberately **not** schema validation. The vendored schema set is version 5.0.7
and the documents the portal accepts are 5.10.0: standard validation against it produces
false errors on genuinely valid files, and the emitter legitimately writes elements the
vendored schema does not define. The schemas transfer as a facet dictionary and a
structural reference, never as an acceptance oracle. So this module checks the leaf-type
facets that are stable across versions — integer, decimal, date, length, pattern — plus
the ordering, pairing and representation rules the specification states outright.

The result is **per rule**, not a verdict. A bare pass/fail cannot express the thing that
matters most here: several rules are neither satisfied nor violated but *unverifiable*,
because the evidence that would settle them is a corpus of real accepted filings that did
not transfer. Those come back as `UNCONFIRMED`, and a document is only `filable` when
nothing is failing **and** nothing is unconfirmed.

Five blind spots are inherited from the predecessor's version of this check as explicit
requirements, each one a measured weakness:

* an empty or whitespace-only element is checked, not exempted;
* an element the vendored schema does not define is checked, not skipped;
* digit-count facets are checked, not merely collected;
* a finding carries the element's **path and value**, so tolerating one occurrence never
  tolerates every occurrence of that name forever;
* elements sharing a name at different paths are resolved **by parent** — `Rate` is a
  decimal in one place and a two-letter code in another.

And the sixth, which is why several rules below count what they examined: **"nothing to
check" fails.** A rule that found no subjects has not passed.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from deepclare.filing import contract as c
from deepclare.filing.document import INDENT, PROLOG, Element, Located, walk

_INTEGER_TEXT = re.compile(r"^(0|[1-9][0-9]*)$")
_DECIMAL_TEXT = re.compile(r"^(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$")
_DATE_TEXT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_SELF_CLOSING = re.compile(r"<[^<>]*/>")


class RuleStatus(StrEnum):
    """What one rule concluded."""

    PASS = "pass"
    FAIL = "fail"
    UNCONFIRMED = "unconfirmed"
    """The rule cannot be decided from what this repository holds. Names what would
    settle it. Never quietly counted as a pass."""

    NOT_APPLICABLE = "not_applicable"


class Finding(BaseModel):
    """One place a rule has something to say about."""

    model_config = ConfigDict(frozen=True)

    path: str
    value: str | None
    detail: str


class RuleOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule: str
    status: RuleStatus
    detail: str
    checked: int = 0
    """How many elements the rule actually examined. Zero is a result, not a silence."""

    findings: tuple[Finding, ...] = ()


class ConformanceResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcomes: tuple[RuleOutcome, ...]

    @property
    def failures(self) -> tuple[RuleOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status is RuleStatus.FAIL)

    @property
    def unconfirmed(self) -> tuple[RuleOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status is RuleStatus.UNCONFIRMED)

    @property
    def conforms(self) -> bool:
        """No rule this repository can decide is violated."""
        return not self.failures

    @property
    def filable(self) -> bool:
        """Nothing failing and nothing unverified. Today this is never true — see
        `contract`'s docstring on the element names the specification never states."""
        return self.conforms and not self.unconfirmed

    def report(self) -> str:
        """One line per rule, then the findings. For a human reading a run."""
        lines: list[str] = []
        for outcome in self.outcomes:
            lines.append(
                f"[{outcome.status.value:>13}] {outcome.rule:<24} "
                f"checked={outcome.checked:<4} {outcome.detail}"
            )
            for finding in outcome.findings:
                value = "" if finding.value is None else f" = {finding.value!r}"
                lines.append(f"                    {finding.path}{value}: {finding.detail}")
        return "\n".join(lines)


def check(root: Element, xml: str) -> ConformanceResult:
    """Judge one emitted document against every rule this module knows."""
    located = list(walk(root))
    return ConformanceResult(
        outcomes=(
            _element_name_evidence(located),
            _namespace_assignment(root),
            _child_order(located),
            _child_order_evidence(located),
            _no_empty_elements(located),
            _placeholder_confinement(located),
            _leaf_facets(located),
            _fixed_width_codes(located),
            _preference_marker(located),
            _code_name_pairing(located),
            _goods_quantity_present(located),
            _goods_numbering(root, located),
            _never_emitted(located),
            _description_length(located),
            _shipment_cost_elements(located),
            _nesting_depth(located),
            _serialization_shape(xml),
            _file_size(xml),
        )
    )


def _leaves(located: list[Located]) -> list[Located]:
    return [item for item in located if not item.element.children]


def _element_name_evidence(located: list[Located]) -> RuleOutcome:
    findings = tuple(
        Finding(
            path=item.path,
            value=None,
            detail="the specification never states this element's name",
        )
        for item in located
        if item.element.name in c.UNCONFIRMED_ELEMENT_NAMES
    )
    if not findings:
        return RuleOutcome(
            rule="element-name-evidence",
            status=RuleStatus.PASS,
            detail="every element name is one the specification states verbatim",
            checked=len(located),
        )
    distinct = sorted({f.path.rsplit("/", 1)[-1] for f in findings})
    return RuleOutcome(
        rule="element-name-evidence",
        status=RuleStatus.UNCONFIRMED,
        detail=f"{len(distinct)} element names are placeholders, not contract: "
        f"{', '.join(distinct)}. Settled by one real accepted filing, or by the "
        "authority's 5.10.0 schema set.",
        checked=len(located),
        findings=findings,
    )


def _namespace_assignment(root: Element) -> RuleOutcome:
    declared = dict(root.attributes).get("xmlns")
    return RuleOutcome(
        rule="namespace-assignment",
        status=RuleStatus.UNCONFIRMED,
        detail=f"the whole document is written in one default namespace ({declared}). "
        "Filed declarations carry three distinct prefixes and nothing records which "
        "elements sit in which namespace. Settled by one real accepted filing.",
        checked=1,
    )


def _child_order(located: list[Located]) -> RuleOutcome:
    findings: list[Finding] = []
    checked = 0
    for item in located:
        if not item.element.children:
            continue
        sequence = c.SEQUENCES.get(item.element.name)
        if sequence is None:
            findings.append(
                Finding(
                    path=item.path,
                    value=None,
                    detail="no child sequence is declared for this container",
                )
            )
            continue
        checked += 1
        highest = -1
        for child in item.element.children:
            if child.name not in sequence:
                findings.append(
                    Finding(
                        path=f"{item.path}/{child.name}",
                        value=None,
                        detail=f"not a declared child of {item.element.name}",
                    )
                )
                continue
            position = sequence.index(child.name)
            if position < highest:
                findings.append(
                    Finding(
                        path=f"{item.path}/{child.name}",
                        value=None,
                        detail=f"out of sequence: must precede {sequence[highest]}",
                    )
                )
            highest = max(highest, position)
    if checked == 0:
        return RuleOutcome(
            rule="child-order",
            status=RuleStatus.FAIL,
            detail="no container was checked at all",
            checked=0,
            findings=tuple(findings),
        )
    if findings:
        return RuleOutcome(
            rule="child-order",
            status=RuleStatus.FAIL,
            detail="a wrong child order is rejected as wrong format with no field named",
            checked=checked,
            findings=tuple(findings),
        )
    return RuleOutcome(
        rule="child-order",
        status=RuleStatus.PASS,
        detail="every container's children follow the declared sequence",
        checked=checked,
    )


def _child_order_evidence(located: list[Located]) -> RuleOutcome:
    inferred = sorted(
        {
            item.element.name
            for item in located
            if item.element.children and item.element.name in c.UNCONFIRMED_SEQUENCES
        }
    )
    if not inferred:
        return RuleOutcome(
            rule="child-order-evidence",
            status=RuleStatus.PASS,
            detail="every sequence used is one the specification states outright",
            checked=len(located),
        )
    return RuleOutcome(
        rule="child-order-evidence",
        status=RuleStatus.UNCONFIRMED,
        detail=f"{len(inferred)} sequences are read off the specification's section and "
        f"table order rather than stated as an order: {', '.join(inferred)}. The goods "
        "item, its packaging, preferences and procedure are stated and are not among "
        "them.",
        checked=len(located),
    )


def _no_empty_elements(located: list[Located]) -> RuleOutcome:
    findings = tuple(
        Finding(
            path=item.path,
            value=item.element.text,
            detail="an element with no children and no content; absence is expressed by "
            "omitting the element",
        )
        for item in located
        if not item.element.children and not (item.element.text or "").strip()
    )
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="no-empty-elements",
        status=status,
        detail="all 311 accepted filings contain zero empty and zero self-closing elements",
        checked=len(located),
        findings=findings,
    )


def _placeholder_confinement(located: list[Located]) -> RuleOutcome:
    findings = tuple(
        Finding(
            path=item.path,
            value=item.element.text,
            detail="a placeholder in a leaf that is not one of the two permitted "
            "organization names; a typed leaf carrying it rejects the whole file",
        )
        for item in located
        if (item.element.text or "").strip() == c.ABSENT_ORGANIZATION_NAME
        and item.path not in c.PLACEHOLDER_PERMITTED_PATHS
    )
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="placeholder-confinement",
        status=status,
        detail="exactly two elements in the document may carry a placeholder",
        checked=len(located),
        findings=findings,
    )


def _leaf_facets(located: list[Located]) -> RuleOutcome:
    findings: list[Finding] = []
    leaves = _leaves(located)
    for item in leaves:
        facet = c.facet_for(item.parent_name, item.element.name)
        text = item.element.text or ""
        if facet is None:
            findings.append(
                Finding(
                    path=item.path,
                    value=text,
                    detail="no facet is declared for this leaf, so nothing checked it",
                )
            )
            continue
        detail = _facet_violation(facet, text)
        if detail is not None:
            findings.append(Finding(path=item.path, value=text, detail=detail))
    if not leaves:
        return RuleOutcome(
            rule="leaf-facets",
            status=RuleStatus.FAIL,
            detail="the document carries no leaf values at all",
            checked=0,
        )
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="leaf-facets",
        status=status,
        detail="integer, decimal, date, length and pattern — the layer that is stable "
        "across schema versions",
        checked=len(leaves),
        findings=tuple(findings),
    )


def _facet_violation(facet: c.Facet, text: str) -> str | None:
    if facet.fixed is not None and text != facet.fixed:
        return f"must be exactly {facet.fixed!r}"
    if facet.allowed is not None and text not in facet.allowed:
        return f"must be one of {', '.join(facet.allowed)}"
    if facet.pattern is not None and not re.match(facet.pattern, text):
        return f"does not match {facet.pattern}"
    if facet.max_length is not None and len(text) > facet.max_length:
        return (
            f"is {len(text)} characters against a hard cap of {facet.max_length}; one "
            "over-long leaf rejects the whole file"
        )
    if facet.kind is c.FacetKind.INTEGER and not _INTEGER_TEXT.match(text):
        return "is not an integer written without a decimal point"
    if facet.kind is c.FacetKind.DECIMAL and not _DECIMAL_TEXT.match(text):
        return (
            "is not a decimal in the filed form: period separator, no thousands "
            "separator, no sign, no trailing zeros"
        )
    if facet.kind is c.FacetKind.DATE:
        if not _DATE_TEXT.match(text):
            return "is not an ISO YYYY-MM-DD date"
        try:
            date.fromisoformat(text)
        except ValueError:
            return "is not a real calendar date"
    return None


def _fixed_width_codes(located: list[Located]) -> RuleOutcome:
    """Left-zero-padded tokens, checked as characters.

    Nothing but literal discipline holds these widths: a code that has been through an
    integer arrives with its padding gone, and `055` becomes `55` with no error anywhere.
    """
    findings: list[Finding] = []
    checked = 0
    for item in _leaves(located):
        facet = c.facet_for(item.parent_name, item.element.name)
        if facet is None or facet.digits is None:
            continue
        checked += 1
        text = item.element.text or ""
        if len(text) != facet.digits or not text.isdigit():
            findings.append(
                Finding(
                    path=item.path,
                    value=text,
                    detail=f"must be exactly {facet.digits} digits, zero-padded",
                )
            )
    if checked == 0:
        return RuleOutcome(
            rule="fixed-width-codes",
            status=RuleStatus.FAIL,
            detail="the document carries no fixed-width code at all, which no real "
            "declaration does",
            checked=0,
        )
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="fixed-width-codes",
        status=status,
        detail="zero-padded tokens keep their width",
        checked=checked,
        findings=tuple(findings),
    )


def _preference_marker(located: list[Located]) -> RuleOutcome:
    """The no-privilege marker is two ASCII letter O, byte-checked, never digit zero."""
    findings: list[Finding] = []
    checked = 0
    for item in _leaves(located):
        if item.parent_name != c.PREFERENCES:
            continue
        checked += 1
        text = item.element.text or ""
        if text != c.NO_PREFERENCE:
            findings.append(
                Finding(
                    path=item.path,
                    value=text,
                    detail="must be two ASCII letter O — code points "
                    f"{[ord(ch) for ch in c.NO_PREFERENCE]}, not "
                    f"{[ord(ch) for ch in text]}",
                )
            )
    if checked == 0:
        return RuleOutcome(
            rule="preference-marker",
            status=RuleStatus.FAIL,
            detail="no preference block was written; box 36 is never missing",
            checked=0,
        )
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="preference-marker",
        status=status,
        detail="box 36 carries the letter marker, and no duty preference is ever claimed",
        checked=checked,
        findings=tuple(findings),
    )


def _code_name_pairing(located: list[Located]) -> RuleOutcome:
    findings: list[Finding] = []
    checked = 0
    for item in located:
        if not item.element.children:
            continue
        present = {child.name for child in item.element.children}
        for parent, code_name, name_name in c.CODE_NAME_PAIRS:
            if item.element.name != parent:
                continue
            has_code = code_name in present
            has_name = name_name in present
            if not has_code and not has_name:
                continue
            checked += 1
            if has_name and not has_code:
                findings.append(
                    Finding(
                        path=f"{item.path}/{name_name}",
                        value=None,
                        detail=f"written without {code_name}; the portal keys on the "
                        "code and drops the name silently on import",
                    )
                )
            elif has_code and not has_name:
                findings.append(
                    Finding(
                        path=f"{item.path}/{code_name}",
                        value=None,
                        detail=f"written without {name_name}; the pair is all-or-nothing",
                    )
                )
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="code-name-pairing",
        status=status,
        detail="six code and name pairs are emitted together or not at all",
        checked=checked,
        findings=tuple(findings),
    )


def _goods_quantity_present(located: list[Located]) -> RuleOutcome:
    """The hang. A goods line with no supplementary quantity stalls the import at 100%
    with no message at all, and the same shipment with a quantity on every line imports."""
    findings: list[Finding] = []
    items = [item for item in located if item.element.name == c.GOODS_ITEM]
    for item in items:
        block = next(
            (child for child in item.element.children if child.name == c.SUPPLEMENTARY_QUANTITY),
            None,
        )
        if block is None:
            findings.append(
                Finding(
                    path=item.path,
                    value=None,
                    detail="no supplementary quantity block; this hangs the portal's "
                    "import at 100% with no message",
                )
            )
            continue
        if not any(child.name == c.GOODS_QUANTITY for child in block.children):
            findings.append(
                Finding(
                    path=f"{item.path}/{c.SUPPLEMENTARY_QUANTITY}",
                    value=None,
                    detail="the block carries no quantity figure",
                )
            )
    if not items:
        return RuleOutcome(
            rule="goods-quantity-present",
            status=RuleStatus.FAIL,
            detail="the document carries no goods item at all",
            checked=0,
        )
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="goods-quantity-present",
        status=status,
        detail="every goods line carries a figure in box 41",
        checked=len(items),
        findings=tuple(findings),
    )


def _goods_numbering(root: Element, located: list[Located]) -> RuleOutcome:
    """Item numbers run 1..N and the shipment's own count agrees with them."""
    findings: list[Finding] = []
    items = [item for item in located if item.element.name == c.GOODS_ITEM]
    for position, item in enumerate(items, start=1):
        numeric = next(
            (child for child in item.element.children if child.name == c.GOODS_NUMERIC), None
        )
        written = None if numeric is None else numeric.text
        if written != str(position):
            findings.append(
                Finding(
                    path=f"{item.path}/{c.GOODS_NUMERIC}",
                    value=written,
                    detail=f"goods items must be numbered 1..N in order; expected {position}",
                )
            )
    total = next(
        (child.text for child in root.children if child.name == c.TOTAL_GOODS_NUMBER), None
    )
    if total != str(len(items)):
        findings.append(
            Finding(
                path=f"{c.ROOT}/{c.TOTAL_GOODS_NUMBER}",
                value=total,
                detail=f"disagrees with the {len(items)} goods blocks in the document",
            )
        )
    if not items:
        return RuleOutcome(
            rule="goods-numbering",
            status=RuleStatus.FAIL,
            detail="the document carries no goods item at all",
            checked=0,
        )
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="goods-numbering",
        status=status,
        detail="item numbers are contiguous and the shipment total agrees",
        checked=len(items),
        findings=tuple(findings),
    )


def _never_emitted(located: list[Located]) -> RuleOutcome:
    findings = tuple(
        Finding(
            path=item.path,
            value=item.element.text,
            detail="this element is assigned by the portal, unresolved, or a post-filing "
            "artifact; nothing here writes it",
        )
        for item in located
        if item.element.name in c.NEVER_EMITTED
    )
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="never-emitted",
        status=status,
        detail="elements the portal owns are left to the portal",
        checked=len(located),
        findings=findings,
    )


def _description_length(located: list[Located]) -> RuleOutcome:
    """The 250-character cap the schema states and real accepted filings exceed."""
    findings: list[Finding] = []
    checked = 0
    for item in _leaves(located):
        facet = c.facet_for(item.parent_name, item.element.name)
        if facet is None or facet.advisory_max_length is None:
            continue
        checked += 1
        text = item.element.text or ""
        if len(text) > facet.advisory_max_length:
            findings.append(
                Finding(
                    path=item.path,
                    value=text,
                    detail=f"is {len(text)} characters against a stated cap of "
                    f"{facet.advisory_max_length}",
                )
            )
    if not findings:
        return RuleOutcome(
            rule="advisory-lengths",
            status=RuleStatus.PASS,
            detail="no leaf exceeds a cap the schema states",
            checked=checked,
        )
    return RuleOutcome(
        rule="advisory-lengths",
        status=RuleStatus.UNCONFIRMED,
        detail="filed declarations do overrun these caps and were accepted, and the "
        "schema permits a split across siblings that nothing here performs. Whether the "
        "live importer enforces them is undetermined.",
        checked=checked,
        findings=tuple(findings),
    )


def _shipment_cost_elements(located: list[Located]) -> RuleOutcome:
    """The two elements present in every accepted filing and never written here."""
    written = {item.element.name for item in located}
    missing = sorted({"TotalCustCost", "CustCostCurrencyCode"} - written)
    if not missing:
        return RuleOutcome(
            rule="shipment-cost-elements",
            status=RuleStatus.PASS,
            detail="both shipment-level cost elements are present",
            checked=2,
        )
    return RuleOutcome(
        rule="shipment-cost-elements",
        status=RuleStatus.UNCONFIRMED,
        detail=f"{', '.join(missing)} are nominally optional, present in 311 of 311 "
        "accepted filings, and not written. Whether their absence is tolerated is the "
        "strongest untested importer requirement in the corpus.",
        checked=2,
    )


def _nesting_depth(located: list[Located]) -> RuleOutcome:
    deepest = max(item.depth for item in located)
    findings = tuple(
        Finding(path=item.path, value=None, detail=f"sits at depth {item.depth}")
        for item in located
        if item.depth > c.MAX_NESTING_DEPTH
    )
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="nesting-depth",
        status=status,
        detail=f"deepest element is at level {deepest}; the format nests five deep",
        checked=len(located),
        findings=findings,
    )


def _serialization_shape(xml: str) -> RuleOutcome:
    """The physical form of the file, which no XML library produces by default."""
    findings: list[Finding] = []
    lines = xml.split("\n")
    if not xml.startswith(f"{PROLOG}<{c.ROOT}"):
        findings.append(
            Finding(
                path="(file)",
                value=lines[0][:80],
                detail="the prolog must be double-quoted with uppercase UTF-8, and the "
                "root element must open on the same physical line",
            )
        )
    if not xml.endswith("\n"):
        findings.append(
            Finding(path="(file)", value=None, detail="the file does not end in a newline")
        )
    for number, line in enumerate(lines[1:], start=2):
        if not line:
            continue
        indent = len(line) - len(line.lstrip())
        if indent % len(INDENT) or line[:indent] != " " * indent:
            findings.append(
                Finding(
                    path=f"(line {number})",
                    value=line[:80],
                    detail="indentation must be a whole number of two-space steps, and "
                    "spaces only",
                )
            )
        if line.count("<") > 2:
            findings.append(
                Finding(
                    path=f"(line {number})",
                    value=line[:80],
                    detail="more than one element on a line",
                )
            )
        if _SELF_CLOSING.search(line):
            findings.append(
                Finding(
                    path=f"(line {number})",
                    value=line[:80],
                    detail="self-closing syntax appears in zero filed declarations",
                )
            )
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="serialization-shape",
        status=status,
        detail=f"{len(lines) - 1} lines, one element each, two-space indent",
        checked=len(lines),
        findings=tuple(findings),
    )


def _file_size(xml: str) -> RuleOutcome:
    size = len(xml.encode("utf-8"))
    status = RuleStatus.PASS if size <= c.MAX_FILE_BYTES else RuleStatus.FAIL
    return RuleOutcome(
        rule="file-size",
        status=status,
        detail=f"{size} bytes against the portal's recorded {c.MAX_FILE_BYTES}-byte limit",
        checked=1,
    )


def element_census(root: Element) -> Counter[str]:
    """How many of each element the document carries. For diffing against a real filing,
    which is the one thing that would confirm the names this module has to guess."""
    return Counter(item.element.name for item in walk(root))
