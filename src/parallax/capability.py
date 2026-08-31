"""Exercise a declared action as each role, then measure what it produced.

Every other check in Parallax asks what a role can *see*. This one asks what a
role can *do*, and then what the doing looked like. The two questions come apart
in the case that matters most: a control hidden with CSS in front of an endpoint
that still accepts the request is not a visibility bug, it is an authorisation
bug, and a witness that only looks at the rendered page will call that surface
clean.

The second half is the part no snapshot tool reaches at all. A dialog, a drawer,
a confirmation panel — none of them exist on a freshly loaded page, so a checker
that measures page load never measures them. Here the same probe that measures a
page runs again on the state the action produced, so the dialog gets the same
overflow, contrast, tap-target and mirroring checks the page behind it got.

Safety is the same contract as the rest of the relational vocabulary and is not
relaxed for this: nothing is discovered and clicked. The caller declares the
action in the validated `submit_form` grammar, or Gemini proposes one and the
observed-evidence guard filters it. Parallax never invents an action to perform.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .relational import Expectation, PageAction, RelationalPair, StorageState
from .types import (
    Axis,
    Context,
    Defect,
    DefectObservation,
    Finding,
    FindingKind,
    Outcome,
    Privilege,
    Severity,
    Surface,
    Testimony,
)


@dataclass(frozen=True)
class CapabilityScenario:
    """One declared action, the roles to try it as, and who should succeed."""

    surface: Surface
    action: PageAction
    effect: Expectation
    roles: tuple[Privilege, ...]
    allowed: frozenset[Privilege]
    deadline_ms: int
    label: str = "action"


@dataclass(frozen=True)
class RoleAttempt:
    """What one role's attempt did, and what the resulting state measured."""

    role: Privilege
    completed: bool
    testimony: Testimony
    observations: tuple[DefectObservation, ...] = ()
    error: str | None = None


class CapabilityRun:
    """Replay one declared action once per role on isolated sessions."""

    def __init__(
        self,
        browser: Any,
        *,
        storage_states: dict[Privilege | str, StorageState] | None = None,
    ) -> None:
        self._browser = browser
        self._states = storage_states or {}

    def _state_for(self, role: Privilege) -> StorageState:
        # `.get(...) or .get(...)` treated an explicitly empty session — `{}`,
        # which Playwright accepts — as absent and silently downgraded the role
        # to anonymous. The conductor already uses the default form; this now
        # matches it.
        return self._states.get(role, self._states.get(role.value))

    def _pair(self, context: Context, role: Privilege) -> Any:
        """One seam for the session pair, matching the audience and choreography runs."""
        state = self._state_for(role)
        return RelationalPair(
            context, context, self._browser,
            sender_storage_state=state, receiver_storage_state=state,
        )

    async def attempt(self, scenario: CapabilityScenario, role: Privilege) -> RoleAttempt:
        """Perform the action as one role and measure the state it produced.

        Both sides of the pair are the same role on purpose. The relational
        machinery already performs an action in one session and polls another
        for the effect; pointing both at the same role turns "did the receiver
        see it" into "did it work for the actor", with no new execution path to
        get wrong.
        """
        context = Context(privilege=role, varies=Axis.PRIVILEGE)
        pair = self._pair(context, role)
        measured: Testimony | None = None

        async def measure_produced_state() -> None:
            """Measure the state the action produced, while it still exists.

            This has to happen inside `observe`, not after it: `observe` closes
            both witnesses in its own `finally`, so a measurement taken on the
            way out reads a page that is already gone. It was written after the
            call and the guard `pair.sender.page is not None` was therefore
            never true — the dialog, drawer or panel this feature exists to
            measure was silently never measured at all.
            """
            nonlocal measured
            page = pair.sender.page
            if page is None:
                return
            try:
                measured = await pair.sender.measure(scenario.surface)
            except Exception:  # noqa: BLE001 - the attempt's own result still stands
                measured = None

        try:
            result = await pair.observe(
                scenario.action, scenario.effect, scenario.deadline_ms,
                surface=scenario.surface, on_effect=measure_produced_state,
            )
            completed = not isinstance(result, Finding)
            testimony = (
                result[0]
                if isinstance(result, list) and result
                else Testimony(scenario.surface, context, Outcome.BLOCKED)
            )
            observations: tuple[DefectObservation, ...] = ()
            if completed and measured is not None:
                observations = tuple(measured.observations)
                testimony = measured
            return RoleAttempt(role, completed, testimony, observations)
        except Exception as error:  # noqa: BLE001 - a failed attempt is evidence, not a crash
            return RoleAttempt(
                role,
                False,
                Testimony(scenario.surface, context, Outcome.ERROR, note=str(error)),
                error=f"{type(error).__name__}: {error}",
            )
        finally:
            await pair.close()


def judge(scenario: CapabilityScenario, attempts: list[RoleAttempt]) -> list[Finding]:
    """Turn who completed the action into findings, then judge what appeared."""
    findings: list[Finding] = []
    by_role = {attempt.role: attempt for attempt in attempts}
    unauthorised = [a for a in attempts if a.completed and a.role not in scenario.allowed]
    denied_holders = [a for a in attempts if not a.completed and a.role in scenario.allowed]

    for attempt in unauthorised:
        holders = ", ".join(sorted(role.value for role in scenario.allowed)) or "no role"
        findings.append(Finding(
            kind=FindingKind.ESCALATION,
            severity=Severity.HIGH,
            surface=scenario.surface,
            axis=Axis.PRIVILEGE,
            summary=(
                f"{attempt.role.value} completed '{scenario.label}' on "
                f"{scenario.surface.describe()}, which is offered only to {holders} — "
                "the control being hidden did not stop the action"
            ),
            testimonies=[attempt.testimony] + [
                by_role[role].testimony for role in scenario.allowed if role in by_role
            ],
            evidence=f"{attempt.role.value}=completed",
            label=f"{scenario.label}:{attempt.role.value}",
        ))

    # A role that holds the capability and cannot use it is the plain functional
    # failure the same replay detects: the feature is broken, not merely ugly.
    for attempt in denied_holders:
        findings.append(Finding(
            kind=FindingKind.CAPABILITY_DRIFT,
            severity=Severity.HIGH if not unauthorised else Severity.MEDIUM,
            surface=scenario.surface,
            axis=Axis.PRIVILEGE,
            summary=(
                f"{attempt.role.value} holds '{scenario.label}' on "
                f"{scenario.surface.describe()} but the action did not take effect "
                f"within {scenario.deadline_ms}ms"
            ),
            testimonies=[attempt.testimony],
            evidence=attempt.error or f"{attempt.role.value}=no effect",
            label=f"{scenario.label}:{attempt.role.value}",
        ))

    findings.extend(_render_findings(scenario, attempts))
    return findings


def _render_findings(scenario: CapabilityScenario, attempts: list[RoleAttempt]) -> list[Finding]:
    """Report defects measured in the state the action produced.

    These are the same measurements the page-load probe makes. What is new is
    when they are taken: a dialog that overflows a 360px viewport is invisible
    to every check that only ever measures a freshly loaded page.
    """
    findings: list[Finding] = []
    seen: set[tuple[Privilege, Defect]] = set()
    for attempt in attempts:
        if not attempt.completed:
            continue
        for observation in attempt.observations:
            key = (attempt.role, observation.defect)
            if key in seen:
                continue
            seen.add(key)
            findings.append(Finding(
                kind=FindingKind.RENDER_DEFECT,
                severity=Severity.MEDIUM,
                surface=scenario.surface,
                axis=Axis.PRIVILEGE,
                summary=(
                    f"{scenario.surface.describe()}: the state produced by "
                    f"'{scenario.label}' has {observation.defect.value.replace('_', ' ')} "
                    f"for {attempt.role.value}"
                ),
                testimonies=[attempt.testimony],
                defect=observation.defect,
                evidence=f"measured after the action, not at page load · {attempt.role.value}",
                label=f"{scenario.label}:{attempt.role.value}:{observation.defect.value}",
            ))
    return findings
