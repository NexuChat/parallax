from __future__ import annotations

import asyncio

from parallax.choreography import (
    Choreography,
    ChoreographyOutcome,
    ChoreographyRun,
    Expect,
    Participant,
    Step,
    StepResult,
    judge,
)
from parallax.types import Axis, Context, FindingKind, Privilege, Severity, Surface, SurfaceKind


ARENA = Surface(SurfaceKind.ROUTE, "https://arena.example/game")


def player(name: str) -> Participant:
    return Participant(name, Context(privilege=Privilege.MEMBER, varies=Axis.RELATIONAL))


def step(label: str, actor: str = "amira", *expects: Expect) -> Step:
    return Step(label, actor, lambda page: None, tuple(expects))


def game(*steps: Step) -> Choreography:
    return Choreography(ARENA, (player("amira"), player("samir")), steps, label="invite and play")


def outcome(spec: Choreography, *results: StepResult) -> ChoreographyOutcome:
    result = ChoreographyOutcome(spec)
    result.results = list(results)
    return result


def test_a_protocol_that_holds_reports_nothing() -> None:
    spec = game(step("invite"), step("accept", "samir"))

    assert judge(outcome(spec, StepResult(spec.steps[0]), StepResult(spec.steps[1]))) == []


def test_the_finding_names_the_step_that_broke_and_who_disagreed() -> None:
    """In a protocol the first divergence is the cause; the rest is consequence."""
    expect = Expect("samir", "#invite", True, "the invitation must reach its recipient")
    spec = game(step("amira enters"), step("amira invites", "amira", expect), step("samir accepts", "samir"))
    broken = StepResult(spec.steps[1], violated=[(expect, "never appeared")])

    findings = judge(outcome(spec, StepResult(spec.steps[0]), broken))

    assert [f.kind for f in findings] == [FindingKind.PROPAGATION_FAILURE]
    assert findings[0].severity is Severity.HIGH
    assert "broke at step 2 of 3, 'amira invites'" in findings[0].summary
    assert "samir should have seen it but it never appeared" in findings[0].summary
    assert "the invitation must reach its recipient" in findings[0].summary
    assert "1 of 3 steps completed" in (findings[0].evidence or "")


def test_a_negative_expectation_that_fires_reads_as_a_leak_not_a_miss() -> None:
    expect = Expect("amira", "#invite", False, "and must not be shown to the sender")
    spec = game(step("amira invites", "amira", expect))
    broken = StepResult(spec.steps[0], violated=[(expect, "appeared when it should not have")])

    findings = judge(outcome(spec, broken))

    assert "amira should not have seen it but it appeared when it should not have" in findings[0].summary


def test_a_refused_move_is_reported_against_the_player_who_tried_it() -> None:
    spec = game(step("samir moves out of turn", "samir"))
    broken = StepResult(spec.steps[0], error="samir could not perform 'samir moves out of turn': Error: 409")

    findings = judge(outcome(spec, broken))

    assert "could not perform" in findings[0].summary
    assert "samir disagreed" in (findings[0].evidence or "")


def test_a_run_that_never_started_says_how_far_it_got() -> None:
    spec = game(step("one"), step("two"))
    result = ChoreographyOutcome(spec, error="TimeoutError: the arena never loaded")

    findings = judge(result)

    assert "could not be played" in findings[0].summary
    assert "0 of 2 steps completed" in findings[0].summary


def test_an_actor_who_is_not_a_participant_is_refused_before_acting() -> None:
    acted: list[str] = []

    class FakePage:
        async def goto(self, *_args, **_kwargs) -> None:
            return None

    spec = game(Step("ghost moves", "ghost", lambda page: acted.append("ghost")))
    run = ChoreographyRun(browser=None)

    result = asyncio.run(run._play_step(spec.steps[0], {"amira": FakePage()}))

    assert acted == []
    assert result.error is not None and "not a participant" in result.error


def test_every_participant_is_open_before_the_first_step_runs() -> None:
    """A player who joined after the invitation cannot testify that it arrived."""
    order: list[str] = []

    class FakePage:
        def __init__(self, name: str) -> None:
            self.name = name

        async def goto(self, *_args, **_kwargs) -> None:
            order.append(f"placed:{self.name}")

        def locator(self, _selector: str) -> "FakePage":
            return self

        async def is_visible(self) -> bool:
            return True

    class FakeSession:
        """One session per participant — a pair opened two and used one."""

        def __init__(self, name: str) -> None:
            self.page = FakePage(name)

        async def open(self) -> None:
            order.append(f"opened:{self.page.name}")

        async def close(self) -> None:
            return None

    spec = game(Step("amira invites", "amira", lambda page: order.append("acted")))
    sessions = {"amira": FakeSession("amira"), "samir": FakeSession("samir")}

    class Runner(ChoreographyRun):
        def _session(self, participant):
            return sessions[participant.name]

    asyncio.run(Runner(browser=None, poll_ms=1).play(spec))

    assert order.index("acted") > order.index("placed:samir")
    assert order.index("opened:samir") < order.index("acted")


def test_the_sequence_stops_at_the_first_divergence() -> None:
    """Continuing would report consequences as though they were faults."""
    ran: list[str] = []

    class FakePage:
        async def goto(self, *_args, **_kwargs) -> None:
            return None

        def locator(self, _selector: str) -> "FakePage":
            return self

        async def is_visible(self) -> bool:
            return False

    class FakeSession:
        def __init__(self) -> None:
            self.page = FakePage()

        async def open(self) -> None:
            return None

        async def close(self) -> None:
            return None

    spec = game(
        Step("first", "amira", lambda page: ran.append("first"),
             (Expect("amira", "#never", True),), deadline_ms=1),
        Step("second", "amira", lambda page: ran.append("second")),
    )

    class Runner(ChoreographyRun):
        def _session(self, _participant):
            return FakeSession()

    result = asyncio.run(Runner(browser=None, poll_ms=1).play(spec))

    assert ran == ["first"]
    assert len(result.results) == 1
    assert judge(result)[0].summary.startswith("'invite and play' broke at step 1 of 2")


def test_an_effect_that_appears_and_vanishes_during_the_move_is_still_seen() -> None:
    """Polling only after the action returns misses anything transient.

    A toast that auto-dismisses, a spinner, a permission prompt — each exists
    only while the action is running. A containment expectation against one was
    recorded as satisfied because nobody was looking while it existed.
    """
    visible = {"now": False}

    class FakePage:
        async def goto(self, *_args, **_kwargs) -> None:
            return None

        def locator(self, _selector: str) -> "FakePage":
            return self

        async def is_visible(self) -> bool:
            return visible["now"]

    class FakeSession:
        def __init__(self) -> None:
            self.page = FakePage()

        async def open(self) -> None:
            return None

        async def close(self) -> None:
            return None

    async def flashes(_page):
        visible["now"] = True          # the toast appears
        await asyncio.sleep(0.05)
        visible["now"] = False         # and is gone before the action returns

    spec = Choreography(
        ARENA, (player("amira"),),
        (Step("amira invites", "amira", flashes,
              (Expect("amira", "#toast", True, "the toast must be seen"),), deadline_ms=400),),
        label="transient",
    )

    class Runner(ChoreographyRun):
        def _session(self, _participant):
            return FakeSession()

    result = asyncio.run(Runner(browser=None, poll_ms=1).play(spec))

    assert result.results[0].passed, "the watcher must be running while the action is"
    assert judge(result) == []
