"""One actor, several simultaneous observers, and a verdict for each.

A relational scenario has exactly two participants because the question it asks
is "did the receiver see it". Real applications ask a harder question with the
same event: an entrance animation belongs to everyone in the room and to nobody
outside it, a profile change should reach a member and not a signed-out visitor,
a private-message setting decides who may reach you at all. Answering that needs
every observer watching the same moment, because "did B see it" and "did C not
see it" are only comparable if B and C were looking at once.

The negative half is the part that is usually left untested, and it is the half
that leaks. A tool that can only assert presence can prove a feature works; it
can never prove a feature is *contained*. `expect: "absent"` asserts that an
observer went the whole deadline without the effect appearing — which is a real
assertion, not the absence of one, because the observer is polled throughout and
a single sighting fails it.
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
class Observer:
    """One witness of the actor's event, and what it is supposed to perceive."""

    name: str
    context: Context
    effect: Expectation
    expect_visible: bool = True
    surface: Surface | None = None
    storage_state: StorageState = None


@dataclass(frozen=True)
class AudienceScenario:
    """An event performed once and judged from several vantage points at once."""

    surface: Surface
    actor: Context
    action: PageAction
    observers: tuple[Observer, ...]
    deadline_ms: int
    label: str = "event"
    actor_storage_state: StorageState = None


@dataclass
class ObserverResult:
    name: str
    expect_visible: bool
    perceived: bool
    context: Context
    error: str | None = None

    @property
    def correct(self) -> bool:
        """An observer that could not be read proves nothing, in either direction.

        Without the error check, a crashed containment observer scored
        `False == False` and was counted as proof that the event was contained —
        so the half that leaks was silently the half that passed.
        """
        if self.error is not None:
            return False
        return self.perceived == self.expect_visible


@dataclass
class AudienceOutcome:
    scenario: AudienceScenario
    results: list[ObserverResult] = field(default_factory=list)
    actor_error: str | None = None


class AudienceRun:
    """Open every session first, act once, and poll all observers together."""

    def __init__(self, browser: Any, *, poll_ms: int = 50) -> None:
        self._browser = browser
        self._poll = max(1, poll_ms) / 1000

    async def observe(self, scenario: AudienceScenario) -> AudienceOutcome:
        outcome = AudienceOutcome(scenario)
        # One pair per observer, each sharing the actor's context on the sending
        # side. Reusing the audited pair keeps navigation, storage state and
        # effect matching identical to the two-party path.
        if not scenario.observers:
            return outcome
        actor = self._actor_session(scenario)
        watchers = [self._observer_session(observer) for observer in scenario.observers]
        sessions = [actor, *watchers]
        try:
            # return_exceptions, because gather without it propagates the
            # first failure while the siblings keep opening — contexts created
            # moments later that the cleanup then skips, because close() no-ops
            # on a witness whose context was still None when the error fired.
            opened = await asyncio.gather(*(s.open() for s in sessions), return_exceptions=True)
            if (failure := next((r for r in opened if isinstance(r, Exception)), None)) is not None:
                raise failure
            await self._place(actor, watchers, scenario)
            # Every observer is watching before the event happens. Acting first
            # and opening afterwards would make a negative result meaningless.
            action_task = asyncio.create_task(self._perform(scenario.action, actor.page))
            results = await asyncio.gather(*(
                self._watch(watcher, observer, scenario.deadline_ms)
                for watcher, observer in zip(watchers, scenario.observers)
            ))
            outcome.results = list(results)
            if action_task.done():
                try:
                    action_task.result()
                except Exception as error:  # noqa: BLE001 - recorded, not raised
                    outcome.actor_error = f"{type(error).__name__}: {error}"
            else:
                # A sender still running at the deadline is indistinguishable
                # from one that finished and produced nothing, unless it says so.
                action_task.cancel()
                await asyncio.gather(action_task, return_exceptions=True)
                outcome.actor_error = (
                    f"the actor had not finished '{scenario.label}' within "
                    f"{scenario.deadline_ms}ms and was cancelled"
                )
        except Exception as error:  # noqa: BLE001 - a failed run is evidence
            outcome.actor_error = f"{type(error).__name__}: {error}"
        finally:
            await asyncio.gather(*(s.close() for s in sessions), return_exceptions=True)
        return outcome

    def _actor_session(self, scenario: AudienceScenario) -> Any:
        """The one session that acts."""
        return Witness(
            replace(scenario.actor, varies=Axis.RELATIONAL),
            self._browser,
            storage_state=scenario.actor_storage_state,
        )

    def _observer_session(self, observer: Observer) -> Any:
        """One session per observer, and no more.

        Each observer used to arrive inside a RelationalPair, which opens two
        contexts because it holds a sender and a receiver. The sending half was
        never used for anything except the first pair, so a scenario with four
        observers signed eight sessions in — and an application that shows who
        is present, or that allows one session per account, behaves differently
        under eight than under five. The harness must not become a participant
        in the thing it is measuring.
        """
        return Witness(
            replace(observer.context, varies=Axis.RELATIONAL),
            self._browser,
            storage_state=observer.storage_state,
        )

    async def _place(self, actor: Any, watchers: list[Any], scenario: AudienceScenario) -> None:
        """Put the actor and every observer on their surface before the event."""
        moves = [actor.page.goto(scenario.surface.path, wait_until="domcontentloaded", timeout=5_000)]
        for watcher, observer in zip(watchers, scenario.observers):
            target = (observer.surface or scenario.surface).path
            moves.append(watcher.page.goto(target, wait_until="domcontentloaded", timeout=5_000))
        await asyncio.gather(*moves)

    @staticmethod
    async def _perform(action: PageAction, page: Any) -> None:
        result = action(page)
        if result is not None and hasattr(result, "__await__"):
            await result

    async def _watch(
        self, watcher: Any, observer: Observer, deadline_ms: int
    ) -> ObserverResult:
        """Poll one observer for the whole deadline, whichever answer is wanted.

        A negative expectation is not checked once at the end. The observer is
        polled exactly like a positive one, so a effect that appears and is then
        removed still counts as having been seen.
        """
        deadline = asyncio.get_running_loop().time() + deadline_ms / 1000
        perceived = False
        error: str | None = None
        try:
            while True:
                if await _perceives(watcher.page, observer.effect):
                    perceived = True
                    break
                if asyncio.get_running_loop().time() >= deadline:
                    break
                await asyncio.sleep(self._poll)
        except Exception as caught:  # noqa: BLE001 - an unreadable observer is evidence
            error = f"{type(caught).__name__}: {caught}"
        return ObserverResult(observer.name, observer.expect_visible, perceived, observer.context, error)


async def _perceives(page: Any, expectation: Expectation) -> bool:
    """The same effect vocabulary the two-party path uses, kept in one place."""
    return await RelationalPair._matches(page, expectation)


def _witnesses(scenario: AudienceScenario) -> list[Testimony]:
    """One testimony per observer, so a finding names everyone who was watching."""
    return [
        Testimony(scenario.surface, observer.context, Outcome.REACHED)
        for observer in scenario.observers
    ]


def judge(outcome: AudienceOutcome) -> list[Finding]:
    """Report each observer that perceived the wrong thing, and say which way."""
    scenario = outcome.scenario
    findings: list[Finding] = []

    # The actor's own failure has to be read first. Without this, a scenario
    # whose setup threw produced no results at all and was reported as a clean
    # pass, and a scenario whose action failed — a renamed selector, say — made
    # every observer report "never perceived it" and manufactured one HIGH
    # finding per observer against an application that was never asked to do
    # anything.
    if outcome.actor_error is not None or not outcome.results:
        detail = outcome.actor_error or "the scenario produced no observations"
        return [Finding(
            kind=FindingKind.DEAD_SURFACE,
            severity=Severity.MEDIUM,
            surface=scenario.surface,
            axis=Axis.RELATIONAL,
            summary=(
                f"'{scenario.label}' could not be judged: {detail} — "
                "this is a fault in the run, not evidence about the application"
            ),
            testimonies=_witnesses(scenario),
            evidence=detail,
            label=scenario.label,
        )]
    witnesses = [
        Testimony(
            scenario.surface,
            result.context,
            Outcome.REACHED if result.error is None else Outcome.ERROR,
            note=result.error,
        )
        for result in outcome.results
    ]
    seen = ", ".join(r.name for r in outcome.results if r.perceived) or "nobody"

    for result in outcome.results:
        if result.correct:
            continue
        if result.perceived:
            # The containment failure: an observer who should have been outside
            # the event's reach was inside it.
            findings.append(Finding(
                kind=FindingKind.ESCALATION,
                severity=Severity.HIGH,
                surface=scenario.surface,
                axis=Axis.RELATIONAL,
                summary=(
                    f"{result.name} perceived '{scenario.label}' but is not an intended "
                    f"audience for it — the event reached {seen}"
                ),
                testimonies=witnesses,
                evidence=f"{result.name}=perceived · expected absent",
                label=f"{scenario.label}:{result.name}",
            ))
        else:
            findings.append(Finding(
                kind=FindingKind.PROPAGATION_FAILURE,
                severity=Severity.HIGH,
                surface=scenario.surface,
                axis=Axis.RELATIONAL,
                summary=(
                    f"{result.name} is an intended audience for '{scenario.label}' but never "
                    f"perceived it within {scenario.deadline_ms}ms — it reached {seen}"
                ),
                testimonies=witnesses,
                evidence=result.error or f"{result.name}=never perceived",
                label=f"{scenario.label}:{result.name}",
            ))
    return findings
