"""Verify a protocol, not an event.

Everything before this asks one question about one moment: an actor does a
thing, and observers are checked for its effect. A great deal of what an
application actually promises is not a moment but an order — an invitation is
sent, accepted, and only then does a game start; a turn belongs to one player
and not the other; a win ends the game for both sides at once.

A sequence is not a list of independent effects, and testing it as one hides the
failures that matter. If step four is wrong, checking only the final state
reports that somebody won and says nothing about the illegal move that got them
there. So each step is verified from every participant before the next step is
allowed to begin, and the first step that disagrees is the finding — because in
a protocol the first divergence is the cause and everything after it is
consequence.

Every participant is a real session opened before the first step, for the same
reason an audience is: a participant who joined after the invitation was sent
cannot testify about whether the invitation arrived.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from typing import Any

from .relational import Expectation, PageAction, RelationalPair, StorageState
from .witness import Witness
from .types import (
    Axis,
    Context,
    Finding,
    FindingKind,
    Outcome,
    Severity,
    Surface,
    Testimony,
)


@dataclass(frozen=True)
class Participant:
    """One session that takes part for the whole sequence."""

    name: str
    context: Context
    storage_state: StorageState = None
    surface: Surface | None = None


@dataclass(frozen=True)
class Expect:
    """What one participant must, or must not, observe after a step."""

    participant: str
    effect: Expectation
    visible: bool = True
    note: str = ""


@dataclass(frozen=True)
class Step:
    """One move in the protocol and what it must produce for everyone."""

    label: str
    actor: str
    action: PageAction
    expect: tuple[Expect, ...] = ()
    deadline_ms: int = 5_000


@dataclass(frozen=True)
class Choreography:
    """An ordered protocol played by several live sessions."""

    surface: Surface
    participants: tuple[Participant, ...]
    steps: tuple[Step, ...]
    label: str = "sequence"


@dataclass
class StepResult:
    step: Step
    satisfied: list[str] = field(default_factory=list)
    violated: list[tuple[Expect, str]] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> bool:
        return not self.violated and self.error is None


@dataclass
class ChoreographyOutcome:
    choreography: Choreography
    results: list[StepResult] = field(default_factory=list)
    error: str | None = None

    @property
    def first_failure(self) -> StepResult | None:
        return next((result for result in self.results if not result.passed), None)


class ChoreographyRun:
    """Open every participant once, then play the protocol in order."""

    def __init__(self, browser: Any, *, poll_ms: int = 60) -> None:
        self._browser = browser
        self._poll = max(1, poll_ms) / 1000

    def _session(self, participant: Participant) -> Any:
        """One session per declared participant, and exactly one.

        This used a RelationalPair, which opens two contexts because it exists
        to hold a sender and a receiver. Only the sender was ever used, so a
        four-participant protocol signed eight sessions in — and an application
        that shows who is present, or that permits one session per account,
        behaves differently under eight than under four. The harness must not be
        a participant in the thing it is measuring.
        """
        return Witness(
            replace(participant.context, varies=Axis.RELATIONAL),
            self._browser,
            storage_state=participant.storage_state,
        )

    async def play(self, choreography: Choreography) -> ChoreographyOutcome:
        outcome = ChoreographyOutcome(choreography)
        sessions = {p.name: self._session(p) for p in choreography.participants}
        if not sessions:
            return outcome
        pages: dict[str, Any] = {}
        try:
            opened = await asyncio.gather(
                *(s.open() for s in sessions.values()), return_exceptions=True
            )
            if (failure := next((r for r in opened if isinstance(r, Exception)), None)) is not None:
                raise failure
            for participant in choreography.participants:
                page = sessions[participant.name].page
                pages[participant.name] = page
                target = (participant.surface or choreography.surface).path
                await page.goto(target, wait_until="domcontentloaded", timeout=8_000)

            for step in choreography.steps:
                result = await self._play_step(step, pages)
                outcome.results.append(result)
                if not result.passed:
                    # A protocol's first divergence is its cause. Continuing
                    # would report the consequences as though they were faults
                    # of their own.
                    break
        except Exception as error:  # noqa: BLE001 - a failed run is evidence
            outcome.error = f"{type(error).__name__}: {error}"
        finally:
            await asyncio.gather(*(s.close() for s in sessions.values()), return_exceptions=True)
        return outcome

    async def _play_step(self, step: Step, pages: dict[str, Any]) -> StepResult:
        result = StepResult(step)
        actor = pages.get(step.actor)
        if actor is None:
            result.error = f"step {step.label!r} names an actor that is not a participant: {step.actor}"
            return result
        # The watchers start before the move, for the same reason an audience
        # does. Awaiting the action first and polling afterwards misses anything
        # that appears and is gone again while the action is still running — a
        # toast that auto-dismisses, a spinner, a transient permission prompt —
        # and a containment expectation against one of those was recorded as
        # satisfied because nobody was looking while it existed.
        checks_task = asyncio.gather(*(
            self._await_expectation(expect, pages, step.deadline_ms) for expect in step.expect
        ))
        try:
            outcome = step.action(actor)
            if outcome is not None and hasattr(outcome, "__await__"):
                await outcome
        except Exception as error:  # noqa: BLE001 - a refused move is the finding
            checks_task.cancel()
            await asyncio.gather(checks_task, return_exceptions=True)
            result.error = f"{step.actor} could not perform {step.label!r}: {type(error).__name__}: {error}"
            return result

        checks = await checks_task
        for expect, (observed, error) in zip(step.expect, checks):
            if error is not None:
                result.violated.append((expect, error))
            elif observed == expect.visible:
                result.satisfied.append(expect.participant)
            else:
                result.violated.append((
                    expect,
                    "never appeared" if expect.visible else "appeared when it should not have",
                ))
        return result

    async def _await_expectation(
        self, expect: Expect, pages: dict[str, Any], deadline_ms: int
    ) -> tuple[bool, str | None]:
        page = pages.get(expect.participant)
        if page is None:
            return False, f"{expect.participant} is not a participant"
        deadline = asyncio.get_running_loop().time() + deadline_ms / 1000
        try:
            while True:
                if await RelationalPair._matches(page, expect.effect):
                    return True, None
                if asyncio.get_running_loop().time() >= deadline:
                    return False, None
                await asyncio.sleep(self._poll)
        except Exception as error:  # noqa: BLE001 - an unreadable participant is evidence
            return False, f"{type(error).__name__}: {error}"


def judge(outcome: ChoreographyOutcome) -> list[Finding]:
    """Report the first step that broke, and say which participant disagreed."""
    choreography = outcome.choreography
    completed = sum(1 for result in outcome.results if result.passed)
    total = len(choreography.steps)

    if outcome.error is not None:
        return [Finding(
            kind=FindingKind.PROPAGATION_FAILURE,
            severity=Severity.HIGH,
            surface=choreography.surface,
            axis=Axis.RELATIONAL,
            summary=(
                f"'{choreography.label}' could not be played: {outcome.error} "
                f"({completed} of {total} steps completed)"
            ),
            testimonies=_witnesses(choreography),
            evidence=outcome.error,
            label=choreography.label,
        )]

    failure = outcome.first_failure
    if failure is None:
        return []

    if failure.error is not None:
        detail, who = failure.error, failure.step.actor
    else:
        expect, reason = failure.violated[0]
        who = expect.participant
        wanted = "should have seen it" if expect.visible else "should not have seen it"
        detail = f"{expect.participant} {wanted} but it {reason}"
        if expect.note:
            detail = f"{detail} — {expect.note}"

    return [Finding(
        kind=FindingKind.PROPAGATION_FAILURE,
        severity=Severity.HIGH,
        surface=choreography.surface,
        axis=Axis.RELATIONAL,
        summary=(
            f"'{choreography.label}' broke at step {completed + 1} of {total}, "
            f"'{failure.step.label}': {detail}"
        ),
        testimonies=_witnesses(choreography),
        evidence=(
            f"{completed} of {total} steps completed · "
            f"{who} disagreed · "
            + " → ".join(result.step.label for result in outcome.results)
        ),
        label=f"{choreography.label}:{failure.step.label}",
    )]


def _witnesses(choreography: Choreography) -> list[Testimony]:
    return [
        Testimony(choreography.surface, participant.context, Outcome.REACHED)
        for participant in choreography.participants
    ]
