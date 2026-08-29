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
    FindingKind,
    Locale,
    Outcome,
    Privilege,
    Severity,
    Surface,
    SurfaceKind,
    Testimony,
    Theme,
    Viewport,
    derive_witnesses,
)

ADMIN = Surface(kind=SurfaceKind.ROUTE, path="/admin/payouts")


def witness(privilege=Privilege.MEMBER, **kw) -> Context:
    return Context(privilege=privilege, varies=Axis.PRIVILEGE, **kw)


def say(context: Context, outcome: Outcome, *, surface: Surface = ADMIN, **kw) -> Testimony:
    return Testimony(surface=surface, context=context, outcome=outcome, **kw)


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


def test_anonymous_escalation_outranks_member_escalation() -> None:
    findings = compare(
        [
            say(BASELINE, Outcome.REACHED),
            say(witness(Privilege.ANON), Outcome.REACHED),
            say(witness(Privilege.MEMBER), Outcome.BLOCKED),
        ]
    )
    assert findings[0].severity is Severity.HIGH, "an open-internet reach is the worst case"


def test_blocked_anon_and_reached_member_produce_one_escalation_with_both_witnesses() -> None:
    anonymous = say(witness(Privilege.ANON), Outcome.BLOCKED)
    member = say(witness(Privilege.MEMBER), Outcome.REACHED)
    findings = compare([say(BASELINE, Outcome.REACHED), anonymous, member])

    assert len(findings) == 1
    escalation = findings[0]
    assert escalation.kind is FindingKind.ESCALATION
    assert escalation.testimonies == [anonymous, member]
    assert escalation.evidence_line() == "anon-en-light-desktop=blocked · member-en-light-desktop=reached"


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

def test_rtl_defect_is_attributed_to_the_locale_axis() -> None:
    arabic = Context(locale=Locale.AR, varies=Axis.LOCALE)
    findings = compare([say(arabic, Outcome.REACHED, defects=[Defect.RTL_NOT_MIRRORED])])
    assert findings[0].kind is FindingKind.RENDER_DEFECT
    assert findings[0].axis is Axis.LOCALE
    assert "mirrored" in findings[0].summary


def test_offscreen_control_is_high_severity() -> None:
    mobile = Context(viewport=MOBILE, varies=Axis.VIEWPORT)
    findings = compare([say(mobile, Outcome.REACHED, defects=[Defect.OFFSCREEN_CONTROL])])
    assert findings[0].severity is Severity.HIGH


def test_render_defects_survive_without_a_baseline() -> None:
    """Invariants need no second witness; they must still be reported."""
    dark = Context(theme=Theme.DARK, varies=Axis.THEME)
    findings = compare([say(dark, Outcome.REACHED, defects=[Defect.LOW_CONTRAST])])
    assert len(findings) == 1
    assert findings[0].axis is Axis.THEME


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
            say(witness(Privilege.ANON), Outcome.BLOCKED),
            say(witness(Privilege.MEMBER), Outcome.REACHED),
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
