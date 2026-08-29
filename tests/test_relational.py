from __future__ import annotations

import asyncio

import pytest

from parallax.relational import RelationalPair
from parallax.types import Axis, Context, Finding, FindingKind, Outcome, Privilege
from test_witness import FakeBrowser


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def pair(browser: FakeBrowser, clock: Clock) -> RelationalPair:
    return RelationalPair(
        Context(privilege=Privilege.OWNER),
        Context(privilege=Privilege.MEMBER),
        browser,
        sender_storage_state={"cookies": [{"name": "sender"}]},
        receiver_storage_state={"cookies": [{"name": "receiver"}]},
        clock=clock,
        sleep=clock.sleep,
        poll_interval_ms=10,
    )


def test_effect_arriving_before_deadline_returns_relational_testimonies() -> None:
    async def check() -> None:
        browser = FakeBrowser()
        clock = Clock()
        relational = pair(browser, clock)

        async def send(sender: object) -> None:
            browser.contexts[1].page.behavior["visible"] = True

        testimonies = await relational.observe(send, "#message", deadline_ms=30)

        assert not isinstance(testimonies, Finding)
        assert [testimony.outcome for testimony in testimonies] == [Outcome.REACHED, Outcome.REACHED]
        assert all(testimony.context.varies is Axis.RELATIONAL for testimony in testimonies)
        assert browser.context_options[0]["storage_state"] != browser.context_options[1]["storage_state"]

    asyncio.run(check())


def test_missing_effect_returns_one_propagation_finding_naming_both_sides() -> None:
    async def check() -> None:
        browser = FakeBrowser([{}, {"visible": False}])
        relational = pair(browser, Clock())

        async def submit(_sender: object) -> None:
            pass

        result = await relational.observe(submit, "#inbox-message", deadline_ms=30)

        assert isinstance(result, Finding)
        assert result.kind is FindingKind.PROPAGATION_FAILURE
        assert result.axis is Axis.RELATIONAL
        assert "submit" in result.summary
        assert "#inbox-message" in result.summary
        assert "30ms" in result.summary
        assert len(result.testimonies) == 2

    asyncio.run(check())


def test_both_sessions_are_open_while_the_sender_acts() -> None:
    async def check() -> None:
        browser = FakeBrowser()
        relational = pair(browser, Clock())
        overlap: list[bool] = []

        async def send(_sender: object) -> None:
            overlap.append(
                len(browser.contexts) == 2
                and all(not context.closed for context in browser.contexts)
            )
            browser.contexts[1].page.behavior["visible"] = True

        await relational.observe(send, "#message", deadline_ms=30)

        assert overlap == [True]
        assert all(context.closed for context in browser.contexts)

    asyncio.run(check())


def test_sender_error_is_evidence_and_receiver_is_still_observed() -> None:
    async def check() -> None:
        browser = FakeBrowser()
        relational = pair(browser, Clock())

        async def broken_send(_sender: object) -> None:
            browser.contexts[1].page.behavior["visible"] = True
            raise RuntimeError("send failed")

        result = await relational.observe(broken_send, "#message", deadline_ms=30)

        assert not isinstance(result, Finding)
        sender, receiver = result
        assert sender.outcome is Outcome.ERROR
        assert "send failed" in sender.note
        assert receiver.outcome is Outcome.REACHED

    asyncio.run(check())


def test_deadline_uses_injected_time_without_real_sleeping() -> None:
    async def check() -> None:
        browser = FakeBrowser([{}, {"visible": False}])
        clock = Clock()
        relational = pair(browser, clock)

        result = await relational.observe(lambda _sender: None, "#never", deadline_ms=25)

        assert isinstance(result, Finding)
        assert clock.now == 0.025
        assert clock.sleeps == pytest.approx([0.01, 0.01, 0.005])

    asyncio.run(check())
