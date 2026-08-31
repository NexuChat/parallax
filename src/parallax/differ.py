"""The differ: turns testimonies into findings.

Every witness differs from the baseline in exactly one axis, and each axis carries
an expectation:

  * privilege  — access is *supposed* to change. We hunt for sameness.
  * everything — locale, theme, viewport must not change what you can reach.
    else         We hunt for difference.

So a finding is always a broken expectation, and because only one axis moved, the
cause is never ambiguous. That is the whole reason for one-axis-at-a-time
derivation: it buys causal attribution, not just a smaller run.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from .semantics import (
    EMBEDDING_MODEL,
    SEMANTIC_EQUIVALENCE_THRESHOLD,
    SemanticComparator,
    SemanticPair,
    SemanticPairKind,
    SemanticResult,
)
from .types import (
    Axis,
    Context,
    Defect,
    Finding,
    FindingKind,
    Outcome,
    Privilege,
    Severity,
    Surface,
    SurfaceKind,
    Testimony,
)

# Reaching a privileged surface unauthenticated is worse than reaching it as a
# logged-in member: the blast radius is the open internet.
_ESCALATION_SEVERITY = {
    Privilege.ANON: Severity.HIGH,
    Privilege.MEMBER: Severity.MEDIUM,
}

# Render defects differ in how badly they hurt a real user.
_DEFECT_SEVERITY = {
    Defect.OFFSCREEN_CONTROL: Severity.HIGH,      # the user simply cannot act
    Defect.HORIZONTAL_OVERFLOW: Severity.MEDIUM,
    Defect.RTL_NOT_MIRRORED: Severity.MEDIUM,
    Defect.THEME_LAYOUT_SHIFT: Severity.MEDIUM,
    Defect.UNTRANSLATED: Severity.MEDIUM,
    Defect.LOW_CONTRAST: Severity.MEDIUM,
    Defect.SMALL_TAP_TARGET: Severity.MEDIUM,    # only ever raised where fingers are used
    Defect.CLIPPED: Severity.LOW,
}

_DEFECT_PHRASING = {
    Defect.HORIZONTAL_OVERFLOW: "content overflows horizontally",
    Defect.RTL_NOT_MIRRORED: "layout is not mirrored for a right-to-left locale",
    Defect.THEME_LAYOUT_SHIFT: "the layout moved when only the theme changed",
    Defect.UNTRANSLATED: "untranslated or raw i18n strings are visible",
    Defect.LOW_CONTRAST: "text contrast falls below WCAG AA",
    Defect.CLIPPED: "text or a control is clipped",
    Defect.OFFSCREEN_CONTROL: "an actionable control sits outside the viewport",
    Defect.SMALL_TAP_TARGET: "a tap target is smaller than the 44px minimum",
}

_SEVERITY_ORDER = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2, Severity.INFO: 3}
_MAX_REGION_CHARS = 1_000

_configured_semantics: SemanticComparator | None = None


@dataclass(frozen=True)
class _SemanticCandidate:
    pair: SemanticPair
    baseline: Testimony
    variant: Testimony


def configure_semantics(comparator: SemanticComparator | None) -> None:
    """Set the run-owned comparator whose usage the CLI will report."""
    global _configured_semantics
    _configured_semantics = comparator


def _axis_cause(context: Context) -> str:
    """Name the single thing that changed, for the report."""
    return {
        Axis.PRIVILEGE: f"privilege={context.privilege.value}",
        Axis.LOCALE: f"locale={context.locale.value} ({context.direction})",
        Axis.THEME: f"theme={context.theme.value}",
        Axis.VIEWPORT: f"viewport={context.viewport.name} ({context.viewport.width}px)",
        Axis.BASELINE: "baseline",
    }[context.varies]


def _group_by_surface(testimonies: Iterable[Testimony]) -> dict[str, list[Testimony]]:
    grouped: dict[str, list[Testimony]] = defaultdict(list)
    for t in testimonies:
        if t.is_evidence:  # a crashed witness is silence, not a denial
            grouped[t.surface.id].append(t)
    return grouped


def _offered_surfaces(testimony: Testimony) -> set[Surface]:
    """Return the visible navigation offer recorded beside this testimony.

    The conductor attaches this run-local evidence without expanding Testimony's
    persisted contract.  Hand-built testimonies and old recordings simply have
    no offer evidence, so they retain the blocked-witness oracle below.
    """
    offered = getattr(testimony, "offered_surfaces", set())
    return {surface for surface in offered if isinstance(surface, Surface)}


def _privilege_findings(
    surface: Surface, baseline: Testimony, variants: list[Testimony], all_testimonies: Iterable[Testimony]
) -> list[Finding]:
    """Report lower-privilege reaches that contradict the application's own UI policy.

    A blocked witness is useful evidence that an access policy exists, but it is
    not a complete oracle: after a check is removed, every witness reaches the
    page and there is nobody left to be blocked.  The application also expresses
    its policy through navigation.  If an owner's rendered view offers a surface
    and a lower-privilege witness's rendered view does not, that lower witness
    reaching the surface is an escalation even with no denial to compare against.

    A surface offered to everyone remains silent: shared navigation and shared
    reach describe a public page, not a privilege breach.
    """
    findings: list[Finding] = []
    blocked_variants = [t for t in variants if t.outcome is Outcome.BLOCKED]
    for t in variants:
        policy_witness = next(
            (
                candidate
                for candidate in blocked_variants
                if candidate.context.privilege.rank > t.context.privilege.rank
            ),
            None,
        )
        owner_offer = next(
            (
                candidate
                for candidate in all_testimonies
                if candidate.is_evidence
                and candidate.context.privilege is baseline.context.privilege
                and surface in _offered_surfaces(candidate)
            ),
            None,
        )
        lower_offer_view = next(
            (
                candidate
                for candidate in all_testimonies
                if candidate.is_evidence
                and candidate.context.privilege is t.context.privilege
                and candidate.surface == owner_offer.surface
                and surface not in _offered_surfaces(candidate)
            ),
            None,
        ) if owner_offer is not None else None
        offer_bypassed = (
            baseline.reached
            and t.reached
            and lower_offer_view is not None
        )
        if offer_bypassed:
            evidence = [owner_offer]
            for witness in (lower_offer_view, t):
                if all(witness is not present for present in evidence):
                    evidence.append(witness)
            findings.append(
                Finding(
                    kind=FindingKind.ESCALATION,
                    severity=_ESCALATION_SEVERITY.get(t.context.privilege, Severity.MEDIUM),
                    surface=surface,
                    axis=Axis.PRIVILEGE,
                    summary=(
                        f"{t.context.privilege.value} reached {surface.describe()}, "
                        f"although it was offered only to {owner_offer.context.privilege.value} — "
                        f"access policy was bypassed"
                    ),
                    testimonies=evidence,
                )
            )
        elif baseline.reached and t.reached and policy_witness is not None:
            findings.append(
                Finding(
                    kind=FindingKind.ESCALATION,
                    severity=_ESCALATION_SEVERITY.get(t.context.privilege, Severity.MEDIUM),
                    surface=surface,
                    axis=Axis.PRIVILEGE,
                    summary=(
                        f"{t.context.privilege.value} reached {surface.describe()}, "
                        f"although {policy_witness.context.privilege.value} was blocked — "
                        f"access policy was bypassed"
                    ),
                    testimonies=[policy_witness, t],
                )
            )
        elif not baseline.reached and t.reached:
            findings.append(
                Finding(
                    kind=FindingKind.POLICY_INVERSION,
                    severity=Severity.MEDIUM,
                    surface=surface,
                    axis=Axis.PRIVILEGE,
                    summary=(
                        f"owner was blocked from {surface.describe()} while "
                        f"{t.context.privilege.value} reached it"
                    ),
                    testimonies=[baseline, t],
                )
            )
    return findings


def _render_findings(surface: Surface, group: list[Testimony]) -> list[Finding]:
    """Compare each render defect across all witnesses with evidence."""
    if surface.kind is SurfaceKind.AFFORDANCE:
        return []

    by_defect: dict[Defect, list[Testimony]] = defaultdict(list)
    for testimony in group:
        for defect in dict.fromkeys(testimony.defects):
            # The browser's key/Latin scan is raw evidence only. Locale meaning
            # now belongs to the Translation plus embedding comparison below.
            if defect is Defect.UNTRANSLATED:
                continue
            by_defect[defect].append(testimony)

    findings: list[Finding] = []
    for defect, affected in by_defect.items():
        affected_ids = {id(testimony) for testimony in affected}
        unaffected = [testimony for testimony in group if id(testimony) not in affected_ids]
        phrasing = _DEFECT_PHRASING.get(defect, defect.value)
        evidence = affected
        if defect in (Defect.RTL_NOT_MIRRORED, Defect.THEME_LAYOUT_SHIFT):
            baseline = next((item for item in group if item.context.varies is Axis.BASELINE), None)
            if baseline is not None and baseline not in affected:
                evidence = [baseline, *affected]

        if not unaffected:
            findings.append(
                Finding(
                    kind=FindingKind.RENDER_DEFECT,
                    severity=_DEFECT_SEVERITY.get(defect, Severity.LOW),
                    surface=surface,
                    axis=Axis.BASELINE,
                    summary=f"{surface.describe()}: {phrasing}",
                    testimonies=evidence,
                    defect=defect,
                )
            )
            continue

        affected_axes = {testimony.context.varies for testimony in affected}
        axis = affected_axes.pop() if len(affected_axes) == 1 else Axis.BASELINE
        seen_by = ", ".join(testimony.context.name for testimony in affected)
        not_seen_by = ", ".join(testimony.context.name for testimony in unaffected)
        findings.append(
            Finding(
                kind=FindingKind.RENDER_DEFECT,
                # Comparison makes this report more useful, not intrinsically more harmful:
                # retain the defect's severity so universal and discriminating cases agree.
                severity=_DEFECT_SEVERITY.get(defect, Severity.LOW),
                surface=surface,
                axis=axis,
                summary=(
                    f"{surface.describe()}: {phrasing}; seen by {seen_by}, "
                    f"not seen by {not_seen_by}"
                ),
                testimonies=evidence,
                defect=defect,
            )
        )
    return findings


def _analyse(
    surface: Surface, group: list[Testimony], reached_route_paths: set[str], all_testimonies: Iterable[Testimony]
) -> list[Finding]:
    findings = _render_findings(surface, group)

    baseline = next((t for t in group if t.context.varies is Axis.BASELINE), None)
    if baseline is None:
        # Without a baseline there is nothing to compare against; the render
        # invariants above still stand on their own.
        return findings

    privilege_variants = [t for t in group if t.context.varies is Axis.PRIVILEGE]
    # RELATIONAL is excluded on purpose: a sender/receiver pair is not a one-axis
    # derivation, so comparing it against the baseline would manufacture drift
    # findings out of two witnesses that were never supposed to match.
    findings += _privilege_findings(surface, baseline, privilege_variants, all_testimonies)

    # A control absent from an otherwise reached page is not a dead route: it
    # may represent a hidden or unavailable affordance, a distinct claim that
    # must not be mislabeled as "nobody could reach this surface."
    is_absent_affordance_on_reached_page = (
        surface.kind is SurfaceKind.AFFORDANCE and surface.path in reached_route_paths
    )
    if not any(t.reached for t in group) and not is_absent_affordance_on_reached_page:
        findings.append(
            Finding(
                kind=FindingKind.DEAD_SURFACE,
                severity=Severity.INFO,
                surface=surface,
                axis=Axis.BASELINE,
                summary=f"no witness could reach {surface.describe()}",
                testimonies=group,
            )
        )
    return findings


def _semantic_equivalence_findings(
    groups: Iterable[list[Testimony]], semantics: SemanticComparator
) -> list[Finding]:
    """Make one bounded semantic judgement batch for all equivalence candidates."""
    findings: list[Finding] = []
    candidates: list[_SemanticCandidate] = []
    for group in sorted(groups, key=lambda item: item[0].surface.id):
        baseline = next((item for item in group if item.context.varies is Axis.BASELINE), None)
        if baseline is None:
            continue
        variants = [
            item for item in group
            if item.context.varies not in (Axis.BASELINE, Axis.PRIVILEGE, Axis.RELATIONAL)
        ]
        for variant in variants:
            cause = _axis_cause(variant.context)
            if baseline.reached != variant.reached:
                gained, lost = (variant, baseline) if variant.reached else (baseline, variant)
                findings.append(
                    Finding(
                        kind=FindingKind.CAPABILITY_DRIFT,
                        severity=Severity.HIGH,
                        surface=baseline.surface,
                        axis=variant.context.varies,
                        summary=(
                            f"{baseline.surface.describe()} is reachable at {gained.context.name} "
                            f"but not at {lost.context.name} — changing {cause} must not "
                            f"change what a user can reach"
                        ),
                        testimonies=[baseline, variant],
                    )
                )
                continue
            if not (
                baseline.reached
                and variant.reached
                and baseline.content_signature
                and variant.content_signature
                and baseline.content_signature != variant.content_signature
            ):
                continue
            if variant.context.varies not in (Axis.LOCALE, Axis.THEME, Axis.VIEWPORT):
                continue
            region = _changed_region(baseline, variant)
            if region is None:
                findings.extend(_missing_region_fallback(baseline, variant, cause))
                continue
            baseline_text, variant_text = region
            candidates.append(_SemanticCandidate(
                SemanticPair(
                    _semantic_key(baseline, variant),
                    SemanticPairKind.LOCALE if variant.context.varies is Axis.LOCALE else SemanticPairKind.CONTENT,
                    baseline_text,
                    variant_text,
                    baseline.context.locale.value,
                    variant.context.locale.value,
                ),
                baseline,
                variant,
            ))

    results = {result.key: result for result in semantics.evaluate([item.pair for item in candidates])}
    for candidate in candidates:
        result = results[candidate.pair.key]
        findings.extend(_finding_from_semantics(candidate, result))
    return findings


def _changed_region(baseline: Testimony, variant: Testimony) -> tuple[str, str] | None:
    """Return only changed landmark text, never the page's unbounded innerText."""
    def landmarks(testimony: Testimony) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in testimony.geometry:
            selector, text = item.get("selector"), item.get("text")
            if isinstance(selector, str) and isinstance(text, str) and text.strip():
                result.setdefault(selector, text.strip())
        return result

    left, right = landmarks(baseline), landmarks(variant)
    changed = [
        selector for selector in sorted(left.keys() | right.keys())
        if left.get(selector) != right.get(selector)
    ]
    if not changed:
        return None
    baseline_parts = [left[selector] for selector in changed if selector in left]
    variant_parts = [right[selector] for selector in changed if selector in right]
    baseline_text, variant_text = "\n".join(baseline_parts), "\n".join(variant_parts)
    if not baseline_text or not variant_text:
        return None
    return baseline_text[:_MAX_REGION_CHARS], variant_text[:_MAX_REGION_CHARS]


def _missing_region_fallback(baseline: Testimony, variant: Testimony, cause: str) -> list[Finding]:
    evidence = "semantic comparison degraded: changed visible region was not captured"
    if variant.context.varies in (Axis.THEME, Axis.VIEWPORT):
        return [
            Finding(
                FindingKind.CONTENT_DIVERGENCE,
                Severity.LOW,
                baseline.surface,
                variant.context.varies,
                f"{baseline.surface.describe()} shows different content when {cause} — "
                "content is not expected to depend on this axis",
                [baseline, variant],
                evidence=evidence + "; falling back to hash mismatch",
            )
        ]
    if Defect.UNTRANSLATED in variant.defects:
        return [_untranslated_finding(baseline, variant, evidence + "; deterministic raw-text fallback")]
    return []


def _finding_from_semantics(candidate: _SemanticCandidate, result: SemanticResult) -> list[Finding]:
    baseline, variant = candidate.baseline, candidate.variant
    cause = _axis_cause(variant.context)
    if result.similarity is None:
        detail = result.degraded_reason or "semantic comparison did not return a score"
        if candidate.pair.kind is SemanticPairKind.CONTENT:
            return [
                Finding(
                    FindingKind.CONTENT_DIVERGENCE,
                    Severity.LOW,
                    baseline.surface,
                    variant.context.varies,
                    f"{baseline.surface.describe()} shows different content when {cause} — "
                    "content is not expected to depend on this axis",
                    [baseline, variant],
                    evidence=f"{detail}; falling back to hash mismatch",
                )
            ]
        if Defect.UNTRANSLATED in variant.defects:
            return [_untranslated_finding(baseline, variant, detail + "; deterministic raw-text fallback")]
        return []
    evidence = (
        f"{EMBEDDING_MODEL} similarity={result.similarity:.3f}; "
        f"equivalence threshold={SEMANTIC_EQUIVALENCE_THRESHOLD:.2f}"
    )
    if candidate.pair.kind is SemanticPairKind.LOCALE:
        # Untranslated text is the baseline's own text, so it scores as
        # *equivalent* — the one verdict that would clear it if the score were
        # trusted alone. The deterministic check therefore decides that case and
        # the score only corroborates it.
        if Defect.UNTRANSLATED in variant.defects:
            return [_untranslated_finding(baseline, variant, evidence)]
        # A page that *is* translated, into text whose meaning is unrelated to
        # the baseline, is a defect no deterministic check can see: the script is
        # right, the strings are different, and nothing is missing. It is
        # reported here only because the model can now separate the two cases —
        # measured at 0.970-0.987 for correct translations against 0.702-0.836
        # for wrong ones. The model this replaced could not, and the claim was
        # withdrawn rather than left standing on a threshold that did not exist.
        if result.equivalent:
            return []
        return [
            Finding(
                FindingKind.CONTENT_DIVERGENCE,
                Severity.MEDIUM,
                baseline.surface,
                variant.context.varies,
                f"{baseline.surface.describe()} is translated, but its meaning does not "
                f"match the baseline when {cause}",
                [baseline, variant],
                evidence=evidence,
            )
        ]
    if result.equivalent:
        return []
    return [
        Finding(
            FindingKind.CONTENT_DIVERGENCE,
            Severity.LOW,
            baseline.surface,
            variant.context.varies,
            f"{baseline.surface.describe()} shows materially different content when {cause}",
            [baseline, variant],
            evidence=evidence,
        )
    ]


def _untranslated_finding(baseline: Testimony, variant: Testimony, evidence: str) -> Finding:
    return Finding(
        FindingKind.RENDER_DEFECT,
        _DEFECT_SEVERITY[Defect.UNTRANSLATED],
        baseline.surface,
        Axis.LOCALE,
        f"{baseline.surface.describe()} is unrelated to the "
        f"{variant.context.locale.value} translation of its baseline text",
        [baseline, variant],
        defect=Defect.UNTRANSLATED,
        evidence=evidence,
    )


def _semantic_key(baseline: Testimony, variant: Testimony) -> str:
    return f"{baseline.surface.id}:{variant.context.name}:{variant.context.varies.value}"


def compare(testimonies: Iterable[Testimony], *, semantics: SemanticComparator | None = None) -> list[Finding]:
    """Compare all testimonies and return findings, most severe first."""
    findings: list[Finding] = []
    all_testimonies = list(testimonies)
    groups = _group_by_surface(all_testimonies)
    reached_route_paths = {
        group[0].surface.path
        for group in groups.values()
        if group[0].surface.kind is SurfaceKind.ROUTE and any(t.reached for t in group)
    }
    for group in groups.values():
        findings.extend(_analyse(group[0].surface, group, reached_route_paths, all_testimonies))
    comparator = semantics or _configured_semantics or SemanticComparator()
    findings.extend(_semantic_equivalence_findings(groups.values(), comparator))
    findings.sort(key=lambda f: (_SEVERITY_ORDER[f.severity], f.surface.path, f.kind.value))
    return findings
