"""The relational axis: two distinct witnesses coupled in time."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

from .types import (
    Axis,
    Context,
    Finding,
    FindingKind,
    Outcome,
    RevocationLag,
    RevocationPlane,
    RevocationPlanes,
    Severity,
    Surface,
    SurfaceKind,
    Testimony,
)
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
        on_effect: Callable[[], Awaitable[None]] | None = None,
    ) -> list[Testimony] | Finding:
        """Act as one witness while the other polls for the resulting effect.

        The action runs in its own task, so an awaiting sender can never stop
        the receiver from observing within the supplied deadline.

        `on_effect` runs the moment the effect is first seen and before either
        session is closed. A caller that wants to measure the state the action
        produced has no other opportunity: this method closes both witnesses in
        its own `finally`, so anything it inspects afterwards is a page that no
        longer exists.
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
                        if on_effect is not None:
                            try:
                                await on_effect()
                            except Exception:  # noqa: BLE001 - the observation still stands
                                pass
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

    async def measure_revocation_lag(
        self,
        action: PageAction,
        expectation: Expectation,
        deadline_ms: int,
        *,
        max_lag_ms: int = 0,
        surface: Surface | None = None,
        distribution: Expectation | None = None,
        enforcement: Expectation | None = None,
    ) -> Finding:
        """Measure how long an already-open session keeps revoked authority."""
        action_name = self._describe(action, "revoker action")
        sender_error: Exception | None = None
        receiver_error: Exception | None = None
        action_task: asyncio.Task[None] | None = None
        probes: list[str] = []
        lag_ms: int | None = None
        setup_error: str | None = None
        measurement_error: str | None = None
        planes = RevocationPlanes(None, None, None, None)

        try:
            try:
                await self.open()
                assert self.sender.page is not None
                assert self.receiver.page is not None
                if surface is not None:
                    await asyncio.gather(
                        self.sender.page.goto(surface.path, wait_until="domcontentloaded", timeout=5_000),
                        self.receiver.page.goto(surface.path, wait_until="domcontentloaded", timeout=5_000),
                    )
            except Exception as error:
                sender_error = error
                receiver_error = error
                setup_error = f"could not open revocation sessions: {Witness._short_error(error)}"
            else:
                assert self.receiver.page is not None
                try:
                    held = await self._matches(self.receiver.page, expectation)
                except Exception as error:
                    receiver_error = error
                    setup_error = f"could not establish revokee authority: {Witness._short_error(error)}"
                else:
                    if not held:
                        setup_error = "revokee expectation did not hold before revocation"
                    else:
                        action_task = asyncio.create_task(self._perform(action, self.sender.page))
                        try:
                            await action_task
                        except Exception as error:
                            sender_error = error
                            planes = RevocationPlanes(False, None, None, None)
                        else:
                            action_completed = self._clock()
                            try:
                                distribution_passed = await self._revocation_plane(distribution)
                            except Exception as error:
                                distribution_passed = None
                                measurement_error = (
                                    f"could not measure distribution: {Witness._short_error(error)}"
                                )
                            try:
                                enforcement_passed = await self._revocation_plane(enforcement)
                            except Exception as error:
                                enforcement_passed = None
                                enforcement_error = (
                                    f"could not measure enforcement: {Witness._short_error(error)}"
                                )
                                measurement_error = "; ".join(
                                    part for part in (measurement_error, enforcement_error) if part
                                )
                            planes = RevocationPlanes(
                                True,
                                distribution_passed,
                                enforcement_passed,
                                None,
                            )
                            deadline = action_completed + deadline_ms / 1_000
                            while self._clock() <= deadline:
                                try:
                                    still_held = await self._matches(self.receiver.page, expectation)
                                except Exception as error:
                                    receiver_error = error
                                    effects_error = (
                                        f"could not measure authority cessation: {Witness._short_error(error)}"
                                    )
                                    measurement_error = "; ".join(
                                        part for part in (measurement_error, effects_error) if part
                                    )
                                    break
                                if not still_held:
                                    lag_ms = round((self._clock() - action_completed) * 1_000)
                                    planes = RevocationPlanes(
                                        planes.decision,
                                        planes.distribution,
                                        planes.enforcement,
                                        lag_ms <= max_lag_ms,
                                    )
                                    break
                                probes.append("effects")
                                remaining = deadline - self._clock()
                                if remaining <= 0:
                                    break
                                await self._sleep(min(self._poll_interval, remaining))
                            if lag_ms is None and measurement_error is None:
                                planes = RevocationPlanes(
                                    planes.decision,
                                    planes.distribution,
                                    planes.enforcement,
                                    False,
                                )
        finally:
            if action_task is not None and not action_task.done():
                action_task.cancel()
                await asyncio.gather(action_task, return_exceptions=True)
            testimonies = [
                self._testimony(self.sender, sender_error, "revocation action"),
                self._testimony(self.receiver, receiver_error, "revocation expectation"),
            ]
            await self.close()

        revocation = RevocationLag(
            lag_ms=lag_ms,
            deadline_ms=deadline_ms,
            max_lag_ms=max_lag_ms,
            probes=tuple(probes),
            planes=planes,
            effect_selector=expectation if isinstance(expectation, str) else None,
            setup_error=setup_error,
            measurement_error=measurement_error,
        )
        if setup_error:
            summary = f"Revocation setup error: {setup_error}"
        elif sender_error:
            summary = f"Revocation action {action_name} failed; authority could not be measured"
        elif measurement_error:
            summary = f"Revocation authority could not be measured: {measurement_error}"
        elif lag_ms is None:
            summary = f"Revocation authority did not cease within {deadline_ms}ms (lag >= {deadline_ms}ms)"
        else:
            summary = f"Revocation authority ceased after {lag_ms}ms (acceptable <= {max_lag_ms}ms)"
        failed = ", ".join(plane.value for plane in planes.failed)
        if failed:
            summary = f"{summary}; failed plane: {failed}"
        unmeasured = ", ".join(plane.value for plane in planes.unmeasured)
        if unmeasured:
            summary = f"{summary}; unmeasured plane: {unmeasured}"
        return Finding(
            kind=FindingKind.REVOCATION_LAG,
            severity=Severity.HIGH if RevocationPlane.EFFECTS in planes.failed else Severity.INFO,
            surface=testimonies[1].surface,
            axis=Axis.RELATIONAL,
            summary=summary,
            testimonies=testimonies,
            revocation=revocation,
        )

    async def _revocation_plane(self, expectation: Expectation | None) -> bool | None:
        if expectation is None:
            return None
        assert self.receiver.page is not None
        return not await self._matches(self.receiver.page, expectation)

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
