from __future__ import annotations

from parallax.capability import CapabilityScenario, RoleAttempt, judge
from parallax.types import (
    Axis,
    Context,
    Defect,
    DefectObservation,
    FindingKind,
    Outcome,
    Privilege,
    Severity,
    Surface,
    SurfaceKind,
)
# Aliased: pytest tries to collect any imported name starting with "Test".
from parallax.types import Testimony as WitnessTestimony


SURFACE = Surface(SurfaceKind.ROUTE, "https://app.example/threads")


def scenario(allowed: set[Privilege] | None = None) -> CapabilityScenario:
    return CapabilityScenario(
        surface=SURFACE,
        action=lambda page: None,
        effect="visible",
        roles=(Privilege.OWNER, Privilege.MEMBER, Privilege.ANON),
        allowed=frozenset(allowed if allowed is not None else {Privilege.OWNER}),
        deadline_ms=3000,
        label="delete thread",
    )


def attempt(
    role: Privilege,
    completed: bool,
    *,
    defects: list[Defect] | None = None,
    error: str | None = None,
) -> RoleAttempt:
    context = Context(privilege=role, varies=Axis.PRIVILEGE)
    observations = tuple(
        DefectObservation(defect=defect, selector="dialog", detail="measured")
        for defect in (defects or [])
    )
    return RoleAttempt(
        role=role,
        completed=completed,
        testimony=WitnessTestimony(
            SURFACE, context, Outcome.REACHED if completed else Outcome.BLOCKED
        ),
        observations=observations,
        error=error,
    )


def test_the_expected_role_alone_completing_is_not_a_finding() -> None:
    findings = judge(scenario(), [
        attempt(Privilege.OWNER, True),
        attempt(Privilege.MEMBER, False),
        attempt(Privilege.ANON, False),
    ])

    assert findings == []


def test_a_role_that_should_not_act_but_does_is_an_escalation() -> None:
    """A hidden control in front of a live endpoint is the case this exists for."""
    findings = judge(scenario(), [
        attempt(Privilege.OWNER, True),
        attempt(Privilege.MEMBER, True),
        attempt(Privilege.ANON, False),
    ])

    assert [f.kind for f in findings] == [FindingKind.ESCALATION]
    assert findings[0].severity is Severity.HIGH
    assert "member completed 'delete thread'" in findings[0].summary
    assert "hidden did not stop the action" in findings[0].summary


def test_a_role_that_holds_the_capability_and_cannot_use_it_is_reported() -> None:
    findings = judge(scenario(), [
        attempt(Privilege.OWNER, False, error="TimeoutError: no effect"),
        attempt(Privilege.MEMBER, False),
        attempt(Privilege.ANON, False),
    ])

    assert [f.kind for f in findings] == [FindingKind.CAPABILITY_DRIFT]
    assert findings[0].severity is Severity.HIGH
    assert "did not take effect within 3000ms" in findings[0].summary


def test_both_directions_at_once_keeps_the_escalation_the_louder_one() -> None:
    findings = judge(scenario(), [
        attempt(Privilege.OWNER, False),
        attempt(Privilege.MEMBER, True),
        attempt(Privilege.ANON, False),
    ])

    kinds = {f.kind: f.severity for f in findings}
    assert kinds[FindingKind.ESCALATION] is Severity.HIGH
    assert kinds[FindingKind.CAPABILITY_DRIFT] is Severity.MEDIUM


def test_defects_in_the_state_the_action_produced_are_reported() -> None:
    """The dialog a click opens is on no freshly loaded page, so nothing else measures it."""
    findings = judge(scenario(), [
        attempt(Privilege.OWNER, True, defects=[Defect.HORIZONTAL_OVERFLOW]),
        attempt(Privilege.MEMBER, False),
    ])

    assert [f.kind for f in findings] == [FindingKind.RENDER_DEFECT]
    assert findings[0].defect is Defect.HORIZONTAL_OVERFLOW
    assert "the state produced by 'delete thread'" in findings[0].summary
    assert "after the action, not at page load" in (findings[0].evidence or "")


def test_a_failed_attempt_is_never_measured_for_render_defects() -> None:
    """Nothing appeared, so there is no produced state to hold a defect against."""
    findings = judge(scenario(allowed={Privilege.OWNER, Privilege.MEMBER}), [
        attempt(Privilege.MEMBER, False, defects=[Defect.HORIZONTAL_OVERFLOW]),
    ])

    assert all(f.kind is not FindingKind.RENDER_DEFECT for f in findings)


def test_the_same_defect_is_reported_once_per_role() -> None:
    findings = judge(scenario(allowed={Privilege.OWNER, Privilege.MEMBER}), [
        attempt(Privilege.OWNER, True, defects=[Defect.LOW_CONTRAST, Defect.LOW_CONTRAST]),
        attempt(Privilege.MEMBER, True, defects=[Defect.LOW_CONTRAST]),
    ])

    render = [f for f in findings if f.kind is FindingKind.RENDER_DEFECT]
    assert len(render) == 2
    assert {"owner", "member"} == {f.evidence.split("· ")[1] for f in render if f.evidence}


def test_an_action_nobody_is_allowed_to_perform_names_that_plainly() -> None:
    findings = judge(scenario(allowed=set()), [attempt(Privilege.ANON, True)])

    assert "offered only to no role" in findings[0].summary
