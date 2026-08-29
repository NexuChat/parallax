"""The relational axis: two distinct witnesses coupled in time."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

from .types import Axis, Context, Finding, FindingKind, Outcome, Severity, Surface, SurfaceKind, Testimony
from .witness import StorageState, Witness


PageAction = Callable[[Any], Awaitable[None] | None]
Expectation = str | Callable[[Any], Awaitable[bool] | bool]
Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]


class RelationalPair:
    """Two isolated sessions on one browser, kept open for a shared event."""

    def __init__(
        self,
        sender_context: Context,
        receiver_context: Context,
        browser: Any,
        *,
        sender_storage_state: StorageState = None,
        receiver_storage_state: StorageState = None,
        clock: Clock | None = None,
        sleep: Sleep | None = None,
        poll_interval_ms: int = 50,
    ) -> None:
        relational = lambda context: replace(context, varies=Axis.RELATIONAL)
        self.sender = Witness(relational(sender_context), browser, storage_state=sender_storage_state)
        self.receiver = Witness(relational(receiver_context), browser, storage_state=receiver_storage_state)
        self._clock = clock or __import__("time").monotonic
        self._sleep = sleep or asyncio.sleep
        self._poll_interval = poll_interval_ms / 1_000

    async def open(self) -> None:
        """Open both private contexts before either participant can act."""
        await asyncio.gather(self.sender.open(), self.receiver.open())

    async def close(self) -> None:
        await asyncio.gather(self.sender.close(), self.receiver.close())

    async def observe(
        self,
        action: PageAction,
        expectation: Expectation,
        deadline_ms: int,
        *,
        surface: Surface | None = None,
    ) -> list[Testimony] | Finding:
        """Act as one witness while the other polls for the resulting effect.

        The action runs in its own task, so an awaiting sender can never stop
        the receiver from observing within the supplied deadline.
        """
        action_name = self._describe(action, "sender action")
        expectation_name = self._describe(expectation, "receiver effect")
        deadline = self._clock() + deadline_ms / 1_000
        sender_error: Exception | None = None
        receiver_error: Exception | None = None
        received = False
        action_task: asyncio.Task[None] | None = None

        try:
            try:
                await self.open()
            except Exception as error:
                sender_error = error
                receiver_error = error
            else:
                assert self.sender.page is not None
                if surface is not None:
                    try:
                        await asyncio.gather(
                            self.sender.page.goto(surface.path, wait_until="domcontentloaded", timeout=5_000),
                            self.receiver.page.goto(surface.path, wait_until="domcontentloaded", timeout=5_000),
                        )
                    except Exception as error:
                        sender_error = error
                        receiver_error = error
                if sender_error is None:
                    action_task = asyncio.create_task(self._perform(action, self.sender.page))
                # Let the action enter the event loop before the first probe.
                # This is a scheduler yield, not deadline waiting.
                if action_task is not None:
                    await asyncio.sleep(0)
                while action_task is not None and self._clock() <= deadline:
                    try:
                        assert self.receiver.page is not None
                        received = await self._matches(self.receiver.page, expectation)
                    except Exception as error:
                        receiver_error = error
                        break
                    if received:
                        break
                    remaining = deadline - self._clock()
                    if remaining <= 0:
                        break
                    await self._sleep(min(self._poll_interval, remaining))

                if action_task is None:
                    pass
                elif action_task.done():
                    try:
                        action_task.result()
                    except Exception as error:
                        sender_error = error
                else:
                    action_task.cancel()
                    await asyncio.gather(action_task, return_exceptions=True)
                    sender_error = TimeoutError("sender action did not finish before the deadline")
        finally:
            if action_task is not None and not action_task.done():
                action_task.cancel()
                await asyncio.gather(action_task, return_exceptions=True)

            testimonies = [
                self._testimony(self.sender, sender_error, "action"),
                self._testimony(self.receiver, receiver_error, "expectation"),
            ]
            await self.close()

        if received:
            return testimonies
        return Finding(
            kind=FindingKind.PROPAGATION_FAILURE,
            severity=Severity.HIGH,
            surface=testimonies[1].surface,
            axis=Axis.RELATIONAL,
            summary=(
                f"Sender {action_name} did not produce receiver effect "
                f"{expectation_name} within {deadline_ms}ms"
            ),
            testimonies=testimonies,
        )

    @staticmethod
    async def _perform(action: PageAction, page: Any) -> None:
        result = action(page)
        if inspect.isawaitable(result):
            await result

    @staticmethod
    async def _matches(page: Any, expectation: Expectation) -> bool:
        if isinstance(expectation, str):
            return bool(await page.locator(expectation).is_visible())
        result = expectation(page)
        return bool(await result) if inspect.isawaitable(result) else bool(result)

    @staticmethod
    def _describe(value: object, fallback: str) -> str:
        if isinstance(value, str):
            return value
        name = getattr(value, "__name__", None)
        return name if name and name != "<lambda>" else fallback

    @staticmethod
    def _testimony(witness: Witness, error: Exception | None, stage: str) -> Testimony:
        page_url = str(getattr(witness.page, "url", "/"))
        surface = Surface(SurfaceKind.ROUTE, page_url)
        if error is not None:
            return Testimony(
                surface=surface,
                context=witness.context,
                outcome=Outcome.ERROR,
                note=f"{stage} failed: {Witness._short_error(error)}",
            )
        return Testimony(surface=surface, context=witness.context, outcome=Outcome.REACHED)
