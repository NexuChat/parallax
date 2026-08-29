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


def _privilege_findings(
    surface: Surface, baseline: Testimony, variants: list[Testimony]
) -> list[Finding]:
    """Report privilege breaches only where a blocked witness shows a policy exists."""
    findings: list[Finding] = []
    blocked_variants = [t for t in variants if t.outcome is Outcome.BLOCKED]
    for t in variants:
        if baseline.reached and t.reached and blocked_variants:
            policy_witness = blocked_variants[0]
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


def _equivalence_findings(
    surface: Surface, baseline: Testimony, variants: list[Testimony]
) -> list[Finding]:
    """Locale, theme, viewport: access must not move. Difference is the bug."""
    findings: list[Finding] = []
    for t in variants:
        cause = _axis_cause(t.context)

        if baseline.reached != t.reached:
            gained, lost = (t, baseline) if t.reached else (baseline, t)
            findings.append(
                Finding(
                    kind=FindingKind.CAPABILITY_DRIFT,
                    severity=Severity.HIGH,
                    surface=surface,
                    axis=t.context.varies,
                    summary=(
                        f"{surface.describe()} is reachable at {gained.context.name} "
                        f"but not at {lost.context.name} — changing {cause} must not "
                        f"change what a user can reach"
                    ),
                    testimonies=[baseline, t],
                )
            )
            continue

        # Both reached it: the content itself should still correspond.
        if (
            baseline.reached
            and baseline.content_signature
            and t.content_signature
            and baseline.content_signature != t.content_signature
            and t.context.varies in (Axis.THEME, Axis.VIEWPORT)
        ):
            # Locale is excluded on purpose: translated text *should* differ.
            findings.append(
                Finding(
                    kind=FindingKind.CONTENT_DIVERGENCE,
                    severity=Severity.LOW,
                    surface=surface,
                    axis=t.context.varies,
                    summary=(
                        f"{surface.describe()} shows different content when {cause} — "
                        f"content is not expected to depend on this axis"
                    ),
                    testimonies=[baseline, t],
                )
            )
    return findings


def _render_findings(surface: Surface, group: list[Testimony]) -> list[Finding]:
    """Compare each render defect across all witnesses with evidence."""
    by_defect: dict[Defect, list[Testimony]] = defaultdict(list)
    for testimony in group:
        for defect in dict.fromkeys(testimony.defects):
            by_defect[defect].append(testimony)

    findings: list[Finding] = []
    for defect, affected in by_defect.items():
        affected_ids = {id(testimony) for testimony in affected}
        unaffected = [testimony for testimony in group if id(testimony) not in affected_ids]
        phrasing = _DEFECT_PHRASING.get(defect, defect.value)

        if not unaffected:
            findings.append(
                Finding(
                    kind=FindingKind.RENDER_DEFECT,
                    severity=_DEFECT_SEVERITY.get(defect, Severity.LOW),
                    surface=surface,
                    axis=Axis.BASELINE,
                    summary=f"{surface.describe()}: {phrasing}",
                    testimonies=affected,
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
                testimonies=affected,
            )
        )
    return findings


def _analyse(
    surface: Surface, group: list[Testimony], reached_route_paths: set[str]
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
    equivalence_variants = [
        t for t in group
        if t.context.varies not in (Axis.BASELINE, Axis.PRIVILEGE, Axis.RELATIONAL)
    ]

    findings += _privilege_findings(surface, baseline, privilege_variants)
    findings += _equivalence_findings(surface, baseline, equivalence_variants)

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


def compare(testimonies: Iterable[Testimony]) -> list[Finding]:
    """Compare all testimonies and return findings, most severe first."""
    findings: list[Finding] = []
    groups = _group_by_surface(testimonies)
    reached_route_paths = {
        group[0].surface.path
        for group in groups.values()
        if group[0].surface.kind is SurfaceKind.ROUTE and any(t.reached for t in group)
    }
    for group in groups.values():
        findings.extend(_analyse(group[0].surface, group, reached_route_paths))
    findings.sort(key=lambda f: (_SEVERITY_ORDER[f.severity], f.surface.path, f.kind.value))
    return findings
