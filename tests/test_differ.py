from __future__ import annotations

import pytest

from parallax.differ import compare
from parallax.types import (
    BASELINE,
    DESKTOP,
    MOBILE,
    Axis,
    Context,
    Defect,
    DefectObservation,
    FindingKind,
    Locale,
    Outcome,
    Privilege,
    Severity,
    Surface,
    SurfaceKind,
    Testimony as WitnessTestimony,
    Theme,
    Viewport,
    derive_witnesses,
)

ADMIN = Surface(kind=SurfaceKind.ROUTE, path="/admin/payouts")


def witness(privilege=Privilege.MEMBER, **kw) -> Context:
    return Context(privilege=privilege, varies=Axis.PRIVILEGE, **kw)


def say(context: Context, outcome: Outcome, *, surface: Surface = ADMIN, **kw) -> WitnessTestimony:
    return WitnessTestimony(surface=surface, context=context, outcome=outcome, **kw)


def offered(testimony: WitnessTestimony, *surfaces: Surface) -> WitnessTestimony:
    """Attach the visible per-witness offer captured by the conductor."""
    testimony.offered_surfaces = set(surfaces)  # type: ignore[attr-defined]
    return testimony


# --------------------------------------------------------------------------
# Derivation
# --------------------------------------------------------------------------

def test_derivation_changes_exactly_one_axis_per_witness() -> None:
    witnesses = derive_witnesses()
    # baseline + 2 privilege + 1 locale + 1 theme + 2 viewport
    assert len(witnesses) == 7, "7 one-axis witnesses, not a 36-cell cross product"

    baseline = witnesses[0]
    assert baseline.varies is Axis.BASELINE

    for w in witnesses[1:]:
        differences = sum(
            [
                w.privilege != baseline.privilege,
                w.locale != baseline.locale,
                w.theme != baseline.theme,
                w.viewport != baseline.viewport,
            ]
        )
        assert differences == 1, f"{w.name} moved {differences} axes; causality would be ambiguous"


def test_only_privilege_expects_divergence() -> None:
    assert not Axis.PRIVILEGE.expects_equivalence
    for axis in (Axis.LOCALE, Axis.THEME, Axis.VIEWPORT):
        assert axis.expects_equivalence


def test_arabic_locale_implies_rtl() -> None:
    assert Context(locale=Locale.AR).direction == "rtl"
    assert Context(locale=Locale.EN).direction == "ltr"


# --------------------------------------------------------------------------
# Privilege axis — a policy violation needs evidence of a policy
# --------------------------------------------------------------------------

def test_unoffered_anonymous_reach_of_an_owner_offer_is_an_escalation_without_a_denial() -> None:
    home = Surface(kind=SurfaceKind.ROUTE, path="/")
    owner_home = offered(say(BASELINE, Outcome.REACHED, surface=home), ADMIN)
    anonymous_home = offered(say(witness(Privilege.ANON), Outcome.REACHED, surface=home))
    owner = offered(say(BASELINE, Outcome.REACHED))
    anonymous = offered(say(witness(Privilege.ANON), Outcome.REACHED))

    findings = compare([owner_home, anonymous_home, owner, anonymous])

    assert [finding.kind for finding in findings] == [FindingKind.ESCALATION]
    assert findings[0].severity is Severity.HIGH
    assert findings[0].testimonies == [owner_home, anonymous_home, anonymous]


def test_surface_offered_and_reached_by_everyone_is_not_an_escalation() -> None:
    findings = compare(
        [
            offered(say(BASELINE, Outcome.REACHED), ADMIN),
            offered(say(witness(Privilege.MEMBER), Outcome.REACHED), ADMIN),
            offered(say(witness(Privilege.ANON), Outcome.REACHED), ADMIN),
        ]
    )

    assert findings == []


def test_surface_offered_to_nobody_and_reached_by_nobody_is_dead() -> None:
    findings = compare(
        [
            offered(say(BASELINE, Outcome.BLOCKED)),
            offered(say(witness(Privilege.MEMBER), Outcome.BLOCKED)),
            offered(say(witness(Privilege.ANON), Outcome.BLOCKED)),
        ]
    )

    assert [finding.kind for finding in findings] == [FindingKind.DEAD_SURFACE]

def test_public_surface_reached_by_all_privileges_is_not_an_escalation() -> None:
    """The old shared-reach escalation assertion encoded the false-positive defect."""
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED),
            say(witness(Privilege.MEMBER), Outcome.REACHED),
            say(witness(Privilege.ANON), Outcome.REACHED),
        ]
    )
    assert findings == []


def test_anonymous_reach_while_member_is_blocked_is_high_severity_escalation() -> None:
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED),
            say(witness(Privilege.ANON), Outcome.REACHED),
            say(witness(Privilege.MEMBER), Outcome.BLOCKED),
        ]
    )
    assert [finding.kind for finding in findings] == [FindingKind.ESCALATION]
    assert findings[0].severity is Severity.HIGH, "an open-internet reach is the worst case"


def test_owner_and_member_reach_while_anon_is_blocked_is_legitimate_rbac() -> None:
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED),
            say(witness(Privilege.MEMBER), Outcome.REACHED),
            say(witness(Privilege.ANON), Outcome.BLOCKED),
        ]
    )

    assert findings == []


def test_properly_denied_surface_yields_no_finding() -> None:
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED),
            say(witness(Privilege.MEMBER), Outcome.BLOCKED),
            say(witness(Privilege.ANON), Outcome.BLOCKED),
        ]
    )
    assert findings == []


def test_owner_blocked_while_member_allowed_is_inversion() -> None:
    findings = compare(
        [
            say(BASELINE, Outcome.BLOCKED),
            say(witness(Privilege.MEMBER), Outcome.REACHED),
        ]
    )
    assert [f.kind for f in findings] == [FindingKind.POLICY_INVERSION]


def test_partial_still_counts_as_reached_for_an_observed_policy_escalation() -> None:
    """Rendering a degraded admin page is still reaching it."""
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED),
            say(witness(Privilege.ANON), Outcome.PARTIAL),
            say(witness(Privilege.MEMBER), Outcome.BLOCKED),
        ]
    )
    assert any(f.kind is FindingKind.ESCALATION for f in findings)


def test_server_error_never_evidences_an_access_policy() -> None:
    owner = say(BASELINE, Outcome.PARTIAL, http_status=500)
    anonymous = say(witness(Privilege.ANON), Outcome.PARTIAL, http_status=500)
    member = say(witness(Privilege.MEMBER), Outcome.BLOCKED, http_status=403)

    assert not owner.reached
    assert not anonymous.reached
    assert compare([owner, anonymous, member]) == []


# --------------------------------------------------------------------------
# Equivalence axes — difference is the bug
# --------------------------------------------------------------------------

def test_feature_missing_on_mobile_is_capability_drift() -> None:
    mobile = Context(viewport=MOBILE, varies=Axis.VIEWPORT)
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED),
            say(mobile, Outcome.BLOCKED),
        ]
    )
    drift = [f for f in findings if f.kind is FindingKind.CAPABILITY_DRIFT]
    assert len(drift) == 1
    assert drift[0].axis is Axis.VIEWPORT
    assert drift[0].severity is Severity.HIGH
    assert "360px" in drift[0].summary


def test_feature_missing_in_arabic_is_capability_drift() -> None:
    arabic = Context(locale=Locale.AR, varies=Axis.LOCALE)
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED),
            say(arabic, Outcome.BLOCKED),
        ]
    )
    assert [f.kind for f in findings] == [FindingKind.CAPABILITY_DRIFT]
    assert "rtl" in findings[0].summary


def test_translated_content_is_not_reported_as_divergence() -> None:
    """Arabic text SHOULD differ from English — that is the point of translation."""
    arabic = Context(locale=Locale.AR, varies=Axis.LOCALE)
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED, content_signature="english"),
            say(arabic, Outcome.REACHED, content_signature="arabic"),
        ]
    )
    assert findings == []


def test_content_changing_with_theme_is_divergence() -> None:
    """A dark theme repaints; it must not change what the page says."""
    dark = Context(theme=Theme.DARK, varies=Axis.THEME)
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED, content_signature="abc"),
            say(dark, Outcome.REACHED, content_signature="xyz"),
        ]
    )
    assert [f.kind for f in findings] == [FindingKind.CONTENT_DIVERGENCE]


# --------------------------------------------------------------------------
# Render invariants
# --------------------------------------------------------------------------

def test_single_witness_render_defect_is_a_baseline_observation() -> None:
    arabic = Context(locale=Locale.AR, varies=Axis.LOCALE)
    findings = compare([say(arabic, Outcome.REACHED, defects=[Defect.RTL_NOT_MIRRORED])])
    assert findings[0].kind is FindingKind.RENDER_DEFECT
    assert findings[0].axis is Axis.BASELINE
    assert "mirrored" in findings[0].summary


def test_offscreen_control_is_high_severity() -> None:
    mobile = Context(viewport=MOBILE, varies=Axis.VIEWPORT)
    findings = compare([say(mobile, Outcome.REACHED, defects=[Defect.OFFSCREEN_CONTROL])])
    assert findings[0].severity is Severity.HIGH


def test_render_defect_survives_without_a_baseline() -> None:
    """One witness is enough to report a page property."""
    dark = Context(theme=Theme.DARK, varies=Axis.THEME)
    findings = compare([say(dark, Outcome.REACHED, defects=[Defect.LOW_CONTRAST])])
    assert len(findings) == 1
    assert findings[0].axis is Axis.BASELINE


def test_render_defect_seen_by_every_witness_is_one_baseline_finding() -> None:
    testimonies = [
        say(context, Outcome.REACHED, defects=[Defect.LOW_CONTRAST])
        for context in derive_witnesses()
    ]
    findings = compare(testimonies)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.axis is Axis.BASELINE
    assert finding.testimonies == testimonies
    assert all(context.name not in finding.summary for context in derive_witnesses())


def test_render_defect_seen_by_one_witness_names_the_comparison_axis_and_contexts() -> None:
    witnesses = derive_witnesses()
    mobile = next(context for context in witnesses if context.varies is Axis.VIEWPORT and context.viewport is MOBILE)
    testimonies = [
        say(context, Outcome.REACHED, defects=[Defect.CLIPPED] if context is mobile else [])
        for context in witnesses
    ]
    findings = compare(testimonies)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.axis is Axis.VIEWPORT
    assert finding.testimonies == [testimonies[witnesses.index(mobile)]]
    assert mobile.name in finding.summary
    assert BASELINE.name in finding.summary
    assert "not seen by" in finding.summary


def test_render_defect_seen_on_different_axes_is_one_baseline_comparison() -> None:
    arabic = Context(locale=Locale.AR, varies=Axis.LOCALE)
    mobile = Context(viewport=MOBILE, varies=Axis.VIEWPORT)
    testimonies = [
        say(BASELINE, Outcome.REACHED),
        say(arabic, Outcome.REACHED, defects=[Defect.CLIPPED]),
        say(mobile, Outcome.REACHED, defects=[Defect.CLIPPED]),
    ]
    findings = compare(testimonies)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.axis is Axis.BASELINE
    assert finding.testimonies == testimonies[1:]
    assert arabic.name in finding.summary
    assert mobile.name in finding.summary


def test_different_render_defects_on_one_surface_stay_separate_findings() -> None:
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED, defects=[Defect.CLIPPED]),
            say(witness(), Outcome.REACHED, defects=[Defect.LOW_CONTRAST]),
        ]
    )

    assert len(findings) == 2
    assert any("clipped" in finding.summary for finding in findings)
    assert any("contrast" in finding.summary for finding in findings)


def test_same_render_defect_on_different_surfaces_stays_separate_findings() -> None:
    other = Surface(kind=SurfaceKind.ROUTE, path="/settings")
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED, defects=[Defect.CLIPPED]),
            say(BASELINE, Outcome.REACHED, surface=other, defects=[Defect.CLIPPED]),
        ]
    )

    assert len(findings) == 2
    assert {finding.surface for finding in findings} == {ADMIN, other}


def test_page_render_defect_is_not_repeated_for_each_affordance() -> None:
    route = Surface(kind=SurfaceKind.ROUTE, path="/cart")
    controls = [
        Surface(kind=SurfaceKind.AFFORDANCE, path="/cart", selector=selector, label=label)
        for selector, label in (("#decrement", "-"), ("#increment", "+"), ("#apply", "Apply"))
    ]
    observation = DefectObservation(Defect.CLIPPED, selector=".quantity", detail="measured")
    testimonies = [
        say(
            BASELINE,
            Outcome.REACHED,
            surface=surface,
            defects=[Defect.CLIPPED],
            observations=[observation],
        )
        for surface in (route, *controls)
    ]

    render_findings = [
        finding for finding in compare(testimonies)
        if finding.kind is FindingKind.RENDER_DEFECT
    ]

    assert len(render_findings) == 1
    assert render_findings[0].surface == route
    assert render_findings[0].testimonies == [testimonies[0]]
    assert render_findings[0].testimonies[0].observations == [observation]


def test_affordance_render_defect_is_suppressed_but_privilege_finding_is_kept() -> None:
    control = Surface(
        kind=SurfaceKind.AFFORDANCE,
        path="/admin/payouts",
        selector="#approve",
        label="Approve",
    )
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED, surface=control, defects=[Defect.CLIPPED]),
            say(
                witness(Privilege.MEMBER),
                Outcome.BLOCKED,
                surface=control,
                defects=[Defect.CLIPPED],
            ),
            say(
                witness(Privilege.ANON),
                Outcome.REACHED,
                surface=control,
                defects=[Defect.CLIPPED],
            ),
        ]
    )

    assert [finding.kind for finding in findings] == [FindingKind.ESCALATION]
    assert findings[0].surface == control


# --------------------------------------------------------------------------
# Evidence discipline
# --------------------------------------------------------------------------

def test_a_crashed_witness_is_never_read_as_a_denial() -> None:
    """ERROR means we learned nothing — it must not masquerade as 'blocked'."""
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED),
            say(witness(Privilege.ANON), Outcome.ERROR),
        ]
    )
    assert findings == [], "a failed witness must produce neither a pass nor a finding"


def test_error_never_evidences_a_policy_or_a_privilege_breach() -> None:
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED),
            say(witness(Privilege.ANON), Outcome.ERROR),
            say(witness(Privilege.MEMBER), Outcome.REACHED),
        ]
    )
    assert findings == []


def test_every_finding_carries_the_testimony_it_rests_on() -> None:
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED),
            say(witness(Privilege.ANON), Outcome.REACHED),
            say(witness(Privilege.MEMBER), Outcome.BLOCKED),
        ]
    )
    assert findings
    for finding in findings:
        assert finding.testimonies, "a finding with no evidence is an assertion, not a result"
        assert finding.evidence_line()


def test_surface_nobody_reached_is_reported_as_dead() -> None:
    findings = compare(
        [
            say(BASELINE, Outcome.BLOCKED),
            say(witness(Privilege.MEMBER), Outcome.BLOCKED),
        ]
    )
    assert [f.kind for f in findings] == [FindingKind.DEAD_SURFACE]
    assert findings[0].severity is Severity.INFO


def test_surface_blocked_for_every_privilege_has_no_escalation() -> None:
    findings = compare(
        [
            say(BASELINE, Outcome.BLOCKED),
            say(witness(Privilege.MEMBER), Outcome.BLOCKED),
            say(witness(Privilege.ANON), Outcome.BLOCKED),
        ]
    )
    assert [f.kind for f in findings] == [FindingKind.DEAD_SURFACE]


def test_absent_affordance_on_a_reached_page_is_not_a_dead_surface() -> None:
    """A missing control is distinct from a route that nobody could load."""
    page = Surface(kind=SurfaceKind.ROUTE, path="/room")
    control = Surface(kind=SurfaceKind.AFFORDANCE, path="/room", selector="#delete")
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED, surface=page),
            say(BASELINE, Outcome.BLOCKED, surface=control),
            say(witness(Privilege.MEMBER), Outcome.BLOCKED, surface=control),
        ]
    )
    assert findings == []


def test_findings_are_ordered_most_severe_first() -> None:
    other = Surface(kind=SurfaceKind.ROUTE, path="/settings")
    mobile = Context(viewport=MOBILE, varies=Axis.VIEWPORT)
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED),
            say(witness(Privilege.ANON), Outcome.REACHED),
            say(BASELINE, Outcome.REACHED, surface=other, content_signature="a"),
            say(mobile, Outcome.REACHED, surface=other, content_signature="b",
                defects=[Defect.CLIPPED]),
        ]
    )
    severities = [f.severity for f in findings]
    assert severities == sorted(severities, key=lambda s: [Severity.HIGH, Severity.MEDIUM,
                                                           Severity.LOW, Severity.INFO].index(s))


def test_surfaces_are_identified_independently_of_label() -> None:
    a = Surface(kind=SurfaceKind.AFFORDANCE, path="/room", selector="#delete", label="Delete")
    b = Surface(kind=SurfaceKind.AFFORDANCE, path="/room", selector="#delete", label="حذف")
    assert a.id == b.id, "the same control under two locales must be one surface"
