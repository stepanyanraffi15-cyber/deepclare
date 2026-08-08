"""Conformance: everything about the document that can be judged before it is filed.

The external system's diagnostics are a wrong-format rejection naming no field, a hang at
100% with no message, and a silent value drop. None of the three is diagnosable from the
response, which is why every check that can be made offline is made here.

This is deliberately **not** schema validation. The vendored schema set is version 5.0.7
and the documents the portal accepts are 5.10.0: standard validation against it produces
false errors on genuinely valid files. What replaces it is the evidence: `observed` gives
every element name, the namespace prefix each one is written under, the child order of
every container and the one element that may repeat, all read off 71 ground-truth
declarations. Those four rules are decided against the evidence, not against a schema and
not against a reading of prose.

The result is **per rule**, not a verdict. A bare pass/fail cannot express the one thing
that matters here: a rule can be neither satisfied nor violated but *unverifiable*.
Exactly one rule is in that position now — the empty-container question dossier 03 §6
records as unknown and the evidence base leaves open, carrying two such containers in 71
filings. Everything the specification once left unconfirmed about names, sequences and
namespaces is now attested, and those rules decide.

Six blind spots are inherited from the predecessor's version of this check as explicit
requirements, each one a measured weakness:

* an empty or whitespace-only element is checked, not exempted;
* an element the vendored schema does not define is checked, not skipped;
* digit-count facets are checked, not merely collected;
* a finding carries the element's **path and value**, so tolerating one occurrence never
  tolerates every occurrence of that name forever;
* elements sharing a name at different paths are resolved **by parent** — `Rate` is a
  decimal in one place and a two-letter code in another;
* **"nothing to check" fails.** A rule that found no subjects has not passed, which is
  why several rules below count what they examined.
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
_OPENS_ELEMENT = re.compile(r"^ *<")


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
        """Nothing failing and nothing unverified."""
        return self.conforms and not self.unconfirmed

    def report(self) -> str:
        """One line per rule, then the findings. For a human reading a run."""
        lines: list[str] = []
        for outcome in self.outcomes:
            lines.append(
                f"[{outcome.status.value:>13}] {outcome.rule:<24} "
                f"checked={outcome.checked:<5} {outcome.detail}"
            )
            for finding in outcome.findings:
                value = "" if finding.value is None else f" = {finding.value!r}"
                lines.append(f"                    {finding.path}{value}: {finding.detail}")
        return "\n".join(lines)


def check(root: Element, xml: str) -> ConformanceResult:
    """Judge one document against every rule this module knows.

    Works on any filed declaration, not only one this repository wrote: `document`'s
    parser produces the same tree from a file read off disk, which is what makes a real
    accepted filing checkable against the same rules as our own output.
    """
    located = list(walk(root))
    return ConformanceResult(
        outcomes=(
            _element_names(located),
            _namespace_prefixes(located),
            _document_envelope(root),
            _child_order(located),
            _element_repetition(located),
            _no_empty_leaves(located),
            _empty_containers(located),
            _placeholder_confinement(located),
            _leaf_facets(located),
            _fixed_width_codes(located),
            _preference_marker(located),
            _code_name_pairing(located),
            _goods_quantity_present(located),
            _goods_numbering(located),
            _advisory_lengths(located),
            _nesting_depth(located),
            _serialization_shape(xml),
            _file_size(xml),
        )
    )


def _leaves(located: list[Located]) -> list[Located]:
    return [item for item in located if not item.element.children]


# --- the evidence rules ---------------------------------------------------------------


def _element_names(located: list[Located]) -> RuleOutcome:
    """Every element name is one a real filing carries.

    An element the importer does not know is rejected as wrong format, naming nothing.
    The evidence base holds 68 names and this document may use no other.
    """
    findings = tuple(
        Finding(
            path=item.path,
            value=item.element.text,
            detail=f"no filing in the evidence base carries an element named "
            f"{item.element.name!r}",
        )
        for item in located
        if item.element.name not in c.NAMESPACE_PREFIX_BY_NAME
    )
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="element-names",
        status=status,
        detail=f"every name is one of the {len(c.NAMESPACE_PREFIX_BY_NAME)} the "
        f"{c.EVIDENCE_CASE_COUNT} ground-truth declarations attest",
        checked=len(located),
        findings=findings,
    )


def _namespace_prefixes(located: list[Located]) -> RuleOutcome:
    """The prefix is per element and is not derivable from the element's meaning.

    `SupplementaryGoodsQuantity` sits under the root schema's prefix and all three of its
    children sit under the common-types prefix. Each name appears under exactly one
    prefix across the whole evidence base, so this is decidable element by element.
    """
    findings: list[Finding] = []
    checked = 0
    for item in located:
        expected = c.NAMESPACE_PREFIX_BY_NAME.get(item.element.name)
        if expected is None:
            continue  # reported by element-names; nothing to compare against
        checked += 1
        if item.element.prefix != expected:
            findings.append(
                Finding(
                    path=item.path,
                    value=item.element.prefix,
                    detail=f"is written under {item.element.prefix!r} and every filing in "
                    f"the evidence base writes it under {expected!r}",
                )
            )
    if checked == 0:
        return RuleOutcome(
            rule="namespace-prefixes",
            status=RuleStatus.FAIL,
            detail="no element could be resolved to a prefix at all",
            checked=0,
        )
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="namespace-prefixes",
        status=status,
        detail="each element sits under the one prefix the evidence base puts it under",
        checked=checked,
        findings=tuple(findings),
    )


def _document_envelope(root: Element) -> RuleOutcome:
    """The root element and its attributes, as the ground truths write them."""
    findings: list[Finding] = []
    if root.name != c.ROOT or root.prefix != c.prefix_for(c.ROOT):
        findings.append(
            Finding(
                path=root.qualified_name,
                value=None,
                detail=f"the root element must be {c.prefix_for(c.ROOT)}:{c.ROOT}",
            )
        )
    written = dict(root.attributes)
    for name, value in c.ROOT_ATTRIBUTES:
        if name not in written:
            findings.append(
                Finding(path=f"{root.name}/@{name}", value=None, detail="is not declared")
            )
        elif written[name] != value:
            findings.append(
                Finding(
                    path=f"{root.name}/@{name}",
                    value=written[name],
                    detail=f"must be {value!r}",
                )
            )
    surplus = sorted(set(written) - {name for name, _ in c.ROOT_ATTRIBUTES})
    findings.extend(
        Finding(
            path=f"{root.name}/@{name}",
            value=written[name],
            detail="no filing in the evidence base carries this root attribute",
        )
        for name in surplus
    )
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="document-envelope",
        status=status,
        detail="three namespace declarations, the schema-instance declaration, the "
        "document mode identifier and the schema location",
        checked=len(c.ROOT_ATTRIBUTES) + 1,
        findings=tuple(findings),
    )


def _child_order(located: list[Located]) -> RuleOutcome:
    """A wrong child order is rejected as wrong format, with no element named.

    Optionality does not relax order: a child may be absent, and the ones present must
    still run in the evidence's sequence.
    """
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
                    detail="no filing in the evidence base carries children under this "
                    "element, so no order is attested for it",
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
                        detail=f"no filing carries it as a child of {item.element.name}",
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
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="child-order",
        status=status,
        detail=f"every container follows the sequence the {c.EVIDENCE_CASE_COUNT} ground "
        "truths agree on",
        checked=checked,
        findings=tuple(findings),
    )


def _element_repetition(located: list[Located]) -> RuleOutcome:
    """One element repeats legitimately. Everything else twice under one parent is a bug.

    The idiom that makes this worth checking is repetition by renaming: a second value is
    filed as a numerically-suffixed sibling rather than a repeated element, so a genuine
    repeat is the exception and not the pattern.
    """
    findings: list[Finding] = []
    checked = 0
    for item in located:
        if not item.element.children:
            continue
        checked += 1
        counts = Counter(child.name for child in item.element.children)
        for name, count in counts.items():
            if count > 1 and name not in c.REPEATABLE:
                findings.append(
                    Finding(
                        path=f"{item.path}/{name}",
                        value=str(count),
                        detail=f"appears {count} times under one {item.element.name}; the "
                        f"evidence base repeats only {', '.join(sorted(c.REPEATABLE))}",
                    )
                )
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="element-repetition",
        status=status,
        detail=f"only {', '.join(sorted(c.REPEATABLE))} appears more than once under one "
        "parent",
        checked=checked,
        findings=tuple(findings),
    )


# --- representation rules -------------------------------------------------------------


def _no_empty_leaves(located: list[Located]) -> RuleOutcome:
    """A leaf present and blank is a third state the contract does not have."""
    findings = tuple(
        Finding(
            path=item.path,
            value=item.element.text,
            detail="a value element with no content; absence is expressed by omitting "
            "the element",
        )
        for item in located
        if not item.element.children
        and item.element.name not in c.CONTAINERS
        and not (item.element.text or "").strip()
    )
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="no-empty-leaves",
        status=status,
        detail=f"zero of the {c.EVIDENCE_CASE_COUNT} ground truths carry an empty value "
        "element",
        checked=len(located),
        findings=findings,
    )


def _empty_containers(located: list[Located]) -> RuleOutcome:
    """The one question the evidence leaves open.

    Dossier 03 §6 states that absence is always omission and records self-closing empty
    containers as unattested and as the predecessor's highest-risk unexamined behaviour.
    Two of the 71 ground truths carry an empty consignor address, so the evidence base
    neither confirms the prohibition nor establishes that the importer tolerates one.
    This adapter writes none — `container` returns nothing when every child is absent —
    and reports one it reads rather than deciding a question the evidence does not settle.
    """
    findings = tuple(
        Finding(
            path=item.path,
            value=None,
            detail="a container with no children; it serializes self-closing and dossier "
            "03 §9 records importer tolerance of that as unknown",
        )
        for item in located
        if not item.element.children and item.element.name in c.CONTAINERS
    )
    if not findings:
        return RuleOutcome(
            rule="empty-containers",
            status=RuleStatus.PASS,
            detail="no container was written empty",
            checked=len(located),
        )
    return RuleOutcome(
        rule="empty-containers",
        status=RuleStatus.UNCONFIRMED,
        detail=f"{len(findings)} container(s) carry no children. 2 of the "
        f"{c.EVIDENCE_CASE_COUNT} ground truths do the same, so this is neither ruled "
        "out nor established. Settled by a filing rejected or accepted on this alone.",
        checked=len(located),
        findings=findings,
    )


def _placeholder_confinement(located: list[Located]) -> RuleOutcome:
    findings = tuple(
        Finding(
            path=item.path,
            value=item.element.text,
            detail="a placeholder in a leaf that is not one of the four permitted "
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
        detail="exactly four elements in the document may carry a placeholder",
        checked=len(located),
        findings=findings,
    )


def _leaf_facets(located: list[Located]) -> RuleOutcome:
    findings: list[Finding] = []
    leaves = [item for item in _leaves(located) if item.element.name not in c.CONTAINERS]
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
    The evidence base carries `055` on 23 goods items.
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
        detail=f"{len(c.CODE_NAME_PAIRS)} code and name pairs are emitted together or not "
        "at all",
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
            (
                child
                for child in item.element.children
                if child.name == c.SUPPLEMENTARY_QUANTITY
            ),
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


def _goods_numbering(located: list[Located]) -> RuleOutcome:
    """Item numbers run 1..N and the shipment's own count agrees with them."""
    findings: list[Finding] = []
    items = [item for item in located if item.element.name == c.GOODS_ITEM]
    for position, item in enumerate(items, start=1):
        numeric = next(
            (child for child in item.element.children if child.name == c.GOODS_NUMERIC),
            None,
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
    shipment = next(
        (item for item in located if item.element.name == c.SHIPMENT), None
    )
    total = None
    if shipment is not None:
        total = next(
            (
                child.text
                for child in shipment.element.children
                if child.name == c.TOTAL_GOODS_NUMBER
            ),
            None,
        )
    if total != str(len(items)):
        findings.append(
            Finding(
                path=f"{c.ROOT}/{c.SHIPMENT}/{c.TOTAL_GOODS_NUMBER}",
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
            findings=tuple(findings),
        )
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="goods-numbering",
        status=status,
        detail="item numbers are contiguous and the shipment total agrees",
        checked=len(items),
        findings=tuple(findings),
    )


def _advisory_lengths(located: list[Located]) -> RuleOutcome:
    """Caps the schema states that no filing in the evidence base has yet overrun.

    The goods description is deliberately not among them any more: the schema states 250
    and the evidence base carries 603 in an accepted-shaped filing, so carrying it as a
    cap would fail a real declaration.
    """
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
        detail="the schema states these caps and nothing in the evidence base overruns "
        "them, so whether the live importer enforces them is undetermined.",
        checked=checked,
        findings=tuple(findings),
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
        detail=f"deepest element is at level {deepest}; the evidence base nests "
        f"{c.MAX_NESTING_DEPTH} deep",
        checked=len(located),
        findings=findings,
    )


def _serialization_shape(xml: str) -> RuleOutcome:
    """The physical form of the file, which no XML library produces by default.

    Line checks apply to lines that open an element. A goods description may carry a
    literal line break — 130 leaves in the evidence base do — and its continuation lines
    are text, not markup, so indenting them would change the value.
    """
    findings: list[Finding] = []
    lines = xml.split("\n")
    if not xml.startswith(f"{PROLOG}<"):
        findings.append(
            Finding(
                path="(file)",
                value=lines[0][:80],
                detail="the prolog must be double-quoted with uppercase UTF-8, and the "
                "root element must open on the same physical line",
            )
        )
    if xml.endswith("\n"):
        findings.append(
            Finding(
                path="(file)",
                value=None,
                detail="the file ends in a newline; every ground truth ends at the root's "
                "closing bracket",
            )
        )
    for number, line in enumerate(lines[1:], start=2):
        if not line or not _OPENS_ELEMENT.match(line):
            continue
        indent = len(line) - len(line.lstrip())
        if indent % len(INDENT):
            findings.append(
                Finding(
                    path=f"(line {number})",
                    value=line[:80],
                    detail="indentation must be a whole number of two-space steps",
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
    status = RuleStatus.FAIL if findings else RuleStatus.PASS
    return RuleOutcome(
        rule="serialization-shape",
        status=status,
        detail=f"{len(lines)} lines, one element each, two-space indent, no trailing "
        "newline",
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
    """How many of each element the document carries, by local name."""
    return Counter(item.element.name for item in walk(root))
