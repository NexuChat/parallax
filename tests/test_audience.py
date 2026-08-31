from __future__ import annotations

import asyncio

import pytest

from parallax.audience import (
    AudienceOutcome,
    AudienceRun,
    AudienceScenario,
    Observer,
    ObserverResult,
    judge,
)
from parallax.types import (
    Axis,
    Context,
    FindingKind,
    Privilege,
    Severity,
    Surface,
    SurfaceKind,
)


ROOM = Surface(SurfaceKind.ROUTE, "https://chat.example/rooms/1")


def observer(name: str, expect_visible: bool, privilege: Privilege = Privilege.MEMBER) -> Observer:
    return Observer(
        name=name,
        context=Context(privilege=privilege, varies=Axis.RELATIONAL),
        effect=".entrance-effect",
        expect_visible=expect_visible,
    )


def scenario(*observers: Observer) -> AudienceScenario:
    return AudienceScenario(
        surface=ROOM,
        actor=Context(privilege=Privilege.OWNER, varies=Axis.RELATIONAL),
        action=lambda page: None,
        observers=tuple(observers),
        deadline_ms=3000,
        label="legendary entrance",
    )


def outcome(spec: AudienceScenario, **perceived: bool) -> AudienceOutcome:
    result = AudienceOutcome(spec)
    result.results = [
        ObserverResult(o.name, o.expect_visible, perceived[o.name], o.context)
        for o in spec.observers
    ]
    return result


def test_everyone_perceiving_what_they_should_is_not_a_finding() -> None:
    spec = scenario(
        observer("member in the room", True),
        observer("visitor in another room", False),
    )

    assert judge(outcome(spec, **{
        "member in the room": True,
        "visitor in another room": False,
    })) == []


def test_an_observer_outside_the_audience_who_perceives_it_is_a_leak() -> None:
    """The containment half: proving a feature works never proves it is contained."""
    spec = scenario(
        observer("member in the room", True),
        observer("member in another room", False),
    )

    findings = judge(outcome(spec, **{
        "member in the room": True,
        "member in another room": True,
    }))

    assert [f.kind for f in findings] == [FindingKind.ESCALATION]
    assert findings[0].severity is Severity.HIGH
    assert "is not an intended audience" in findings[0].summary
    assert "expected absent" in (findings[0].evidence or "")


def test_an_intended_observer_who_misses_it_is_a_propagation_failure() -> None:
    spec = scenario(
        observer("member in the room", True),
        observer("visitor in another room", False),
    )

    findings = judge(outcome(spec, **{
        "member in the room": False,
        "visitor in another room": False,
    }))

    assert [f.kind for f in findings] == [FindingKind.PROPAGATION_FAILURE]
    assert "never perceived it within 3000ms" in findings[0].summary


def test_a_leak_and_a_miss_in_the_same_event_are_both_reported() -> None:
    spec = scenario(
        observer("member in the room", True),
        observer("guest in another room", False),
    )

    findings = judge(outcome(spec, **{
        "member in the room": False,
        "guest in another room": True,
    }))

    assert {f.kind for f in findings} == {
        FindingKind.ESCALATION,
        FindingKind.PROPAGATION_FAILURE,
    }


def test_the_summary_names_who_actually_perceived_it() -> None:
    spec = scenario(
        observer("legendary rank", True),
        observer("plain member", True),
        observer("signed-out visitor", False),
    )

    findings = judge(outcome(spec, **{
        "legendary rank": True,
        "plain member": False,
        "signed-out visitor": False,
    }))

    assert "it reached legendary rank" in findings[0].summary


def test_every_observer_watches_before_the_event_happens() -> None:
    """A negative result is meaningless if the observer arrived after the event."""
    order: list[str] = []

    class FakePage:
        def __init__(self, name: str) -> None:
            self.name = name

        async def goto(self, *_args, **_kwargs) -> None:
            order.append(f"placed:{self.name}")

        def locator(self, _selector: str) -> "FakePage":
            return self

        async def is_visible(self) -> bool:
            return False

    class FakeWitness:
        def __init__(self, name: str) -> None:
            self.page = FakePage(name)

    class FakePair:
        def __init__(self, name: str) -> None:
            self.sender = FakeWitness(f"actor-{name}")
            self.receiver = FakeWitness(name)

        async def open(self) -> None:
            order.append(f"opened:{self.receiver.page.name}")

        async def close(self) -> None:
            pass

    spec = scenario(observer("a", True), observer("b", False))
    spec = AudienceScenario(
        surface=spec.surface,
        actor=spec.actor,
        action=lambda page: order.append("acted"),
        observers=spec.observers,
        deadline_ms=10,
        label=spec.label,
    )

    pairs = iter([FakePair("a"), FakePair("b")])

    class Runner(AudienceRun):
        def _pair(self, _scenario, _observer):
            return next(pairs)

    asyncio.run(Runner(browser=None, poll_ms=1).observe(spec))

    assert order.index("acted") > order.index("placed:a")
    assert order.index("acted") > order.index("placed:b")


def test_an_observer_that_could_not_be_read_is_never_counted_as_containment() -> None:
    """The half that leaks was silently the half that passed.

    A containment observer expects to perceive nothing. When its page threw,
    `perceived` was False and `expect_visible` was False, so the comparison
    said "correct" and the run reported the event as properly contained — on
    the strength of an observer that was never readable.
    """
    spec = scenario(observer("member in another room", False))
    result = ChoreographyLikeResult = ObserverResult(
        "member in another room", False, False, spec.observers[0].context,
        error="TargetClosedError: page closed",
    )
    outcome_with_error = AudienceOutcome(spec)
    outcome_with_error.results = [result]

    assert result.correct is False
    findings = judge(outcome_with_error)
    assert len(findings) == 1
    assert "never perceived it" in findings[0].summary


def test_a_readable_observer_that_perceives_nothing_still_confirms_containment() -> None:
    spec = scenario(observer("visitor in another room", False))

    assert judge(outcome(spec, **{"visitor in another room": False})) == []
