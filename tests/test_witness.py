from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from typing import Any

from parallax.differ import compare
from parallax.types import (
    Axis,
    Context,
    Defect,
    DefectObservation,
    FindingKind,
    Locale,
    Outcome,
    Privilege,
    Surface,
    SurfaceKind,
    Theme,
)
from parallax.witness import Witness, run_witnesses


SITE = "https://app.example.test"
SURFACE = Surface(SurfaceKind.ROUTE, f"{SITE}/admin")


@dataclass
class FakeResponse:
    status: int = 200


class FakeCDPSession:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any] | None]] = []
        self.handlers: dict[str, Any] = {}
        self.detached = False

    def on(self, name: str, handler: Any) -> None:
        self.handlers[name] = handler

    def remove_listener(self, name: str, handler: Any) -> None:
        if self.handlers.get(name) is handler:
            del self.handlers[name]

    async def send(self, name: str, params: dict[str, Any] | None = None) -> None:
        self.sent.append((name, params))

    async def detach(self) -> None:
        self.detached = True

    def emit(self, name: str, event: dict[str, Any]) -> None:
        handler = self.handlers.get(name)
        if handler:
            handler(event)


class FakePage:
    def __init__(self, behavior: dict[str, Any]) -> None:
        self.behavior = behavior
        self.url = SITE + behavior.get("final_path", "/admin")
        self.evaluated: list[str] = []
        self.goto_targets: list[str] = []

    async def goto(self, url: str, **_kwargs: Any) -> FakeResponse:
        self.goto_targets.append(url)
        error = self.behavior.get("navigation_error")
        if error:
            raise error
        return FakeResponse(self.behavior.get("status", 200))

    async def wait_for_load_state(self, _state: str, **_kwargs: Any) -> None:
        if self.behavior.get("load_error"):
            raise self.behavior["load_error"]

    async def evaluate(self, source: str) -> dict[str, Any]:
        self.evaluated.append(source)
        error = self.behavior.get("probe_error")
        if error:
            raise error
        return self.behavior.get(
            "probe",
            {"defects": [], "contentSignature": "same-content", "layoutSignature": "same-layout"},
        )

    def locator(self, _selector: str) -> "FakeLocator":
        if self.behavior.get("locator_error"):
            raise self.behavior["locator_error"]
        return FakeLocator(self.behavior.get("visible", True))


class FakeLocator:
    def __init__(self, visible: bool) -> None:
        self.visible = visible

    async def is_visible(self) -> bool:
        return self.visible


class FakeBrowserContext:
    def __init__(self, behavior: dict[str, Any]) -> None:
        self.behavior = behavior
        self.init_scripts: list[str] = []
        self.page = FakePage(behavior)
        self.cdp = FakeCDPSession()
        self.closed = False

    async def add_init_script(self, script: str) -> None:
        self.init_scripts.append(script)

    async def new_page(self) -> FakePage:
        return self.page

    async def new_cdp_session(self, _page: FakePage) -> FakeCDPSession:
        return self.cdp

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, behaviors: list[dict[str, Any]] | None = None) -> None:
        self.behaviors = list(behaviors or [])
        self.contexts: list[FakeBrowserContext] = []
        self.context_options: list[dict[str, Any]] = []
        self.closed = False

    async def new_context(self, **options: Any) -> FakeBrowserContext:
        self.context_options.append(options)
        behavior = self.behaviors.pop(0) if self.behaviors else {}
        context = FakeBrowserContext(behavior)
        self.contexts.append(context)
        return context

    async def close(self) -> None:
        self.closed = True


def test_all_derived_contexts_share_one_browser_and_evaluate_probe_from_disk() -> None:
    async def check() -> None:
        browser = FakeBrowser()
        testimonies = await run_witnesses(SURFACE, browser=browser)

        assert len(testimonies) == 7
        assert {testimony.outcome for testimony in testimonies} == {Outcome.REACHED}
        assert len(browser.contexts) == 7
        assert not browser.closed
        assert all(context.closed for context in browser.contexts)
        probe_sources = [context.page.evaluated for context in browser.contexts]
        assert all(len(sources) == 1 for sources in probe_sources)
        assert len({sources[0] for sources in probe_sources}) == 1
        assert "The deterministic probe" in probe_sources[0][0]
        # One init script, and only one: the media instrumentation, which has to
        # run before any application code to see the connections it creates. It
        # records them and alters nothing, which is why a witness can carry it
        # without becoming a participant in what it observes.
        assert all(len(context.init_scripts) == 1 for context in browser.contexts)
        assert all("__parallaxMedia" in context.init_scripts[0] for context in browser.contexts)
        assert browser.context_options[3]["locale"] == Locale.AR.value
        assert browser.context_options[4]["color_scheme"] == Theme.DARK.value

    asyncio.run(check())


def test_visit_contextualizes_existing_query_parameters_only_for_the_varied_axis() -> None:
    async def target_for(context: Context, path: str) -> str:
        browser = FakeBrowser()
        await Witness(context, browser).visit(Surface(SurfaceKind.ROUTE, path))
        return browser.contexts[0].page.goto_targets[0]

    async def check() -> None:
        path = f"{SITE}/admin?lang=en&theme=light&return=%2Fadmin#panel"

        assert await target_for(
            Context(locale=Locale.AR, varies=Axis.LOCALE), path
        ) == f"{SITE}/admin?lang=ar&theme=light&return=%2Fadmin#panel"
        assert await target_for(
            Context(theme=Theme.DARK, varies=Axis.THEME), path
        ) == f"{SITE}/admin?lang=en&theme=dark&return=%2Fadmin#panel"
        assert await target_for(
            Context(varies=Axis.VIEWPORT), path
        ) == path

    asyncio.run(check())


def test_visit_contextualizes_locale_and_color_scheme_aliases_without_adding_queries() -> None:
    async def target_for(context: Context, path: str) -> str:
        browser = FakeBrowser()
        await Witness(context, browser).visit(Surface(SurfaceKind.ROUTE, path))
        return browser.contexts[0].page.goto_targets[0]

    async def check() -> None:
        aliases = f"{SITE}/admin?locale=en&color-scheme=light"

        assert await target_for(
            Context(locale=Locale.AR, varies=Axis.LOCALE), aliases
        ) == f"{SITE}/admin?locale=ar&color-scheme=light"
        assert await target_for(
            Context(theme=Theme.DARK, varies=Axis.THEME), aliases
        ) == f"{SITE}/admin?locale=en&color-scheme=dark"
        assert await target_for(
            Context(locale=Locale.AR, varies=Axis.LOCALE), f"{SITE}/admin?theme=light"
        ) == f"{SITE}/admin?theme=light"
        assert await target_for(
            Context(theme=Theme.DARK, varies=Axis.THEME), f"{SITE}/admin?lang=en"
        ) == f"{SITE}/admin?lang=en"

    asyncio.run(check())


def test_http_statuses_distinguish_denial_absence_and_server_degradation() -> None:
    async def check() -> None:
        redirect = FakeBrowser([{"final_path": "/login"}])
        witness = Witness(Context(privilege=Privilege.ANON), redirect)
        redirected = await witness.visit(SURFACE)
        await witness.close()

        forbidden = FakeBrowser([{"status": 403}])
        witness = Witness(Context(privilege=Privilege.ANON), forbidden)
        denied = await witness.visit(SURFACE)
        await witness.close()

        absent = FakeBrowser([{"status": 404}, {"status": 404}])
        testimonies = await run_witnesses(
            SURFACE,
            browser=absent,
            contexts=[Context(), Context(privilege=Privilege.ANON, varies=Axis.PRIVILEGE)],
        )

        server_error = await Witness(Context(), FakeBrowser([{"status": 500}])).visit(SURFACE)

        assert redirected.outcome is Outcome.BLOCKED
        assert redirected.final_path == "/login"
        assert denied.outcome is Outcome.BLOCKED
        assert denied.http_status == 403
        assert all(testimony.outcome is Outcome.BLOCKED for testimony in testimonies)
        assert all("absent" in testimony.note for testimony in testimonies)
        assert not any(finding.kind is FindingKind.ESCALATION for finding in compare(testimonies))
        assert server_error.outcome is Outcome.PARTIAL
        assert server_error.outcome is not Outcome.ERROR
        assert server_error.note == "HTTP 500 server error"

    asyncio.run(check())


def test_affordance_lookup_failure_is_witness_error_not_a_policy_denial() -> None:
    async def check() -> None:
        control = Surface(SurfaceKind.AFFORDANCE, f"{SITE}/admin", "[broken")
        testimony = await Witness(
            Context(), FakeBrowser([{"locator_error": RuntimeError("invalid selector")}])
        ).visit(control)

        assert testimony.outcome is Outcome.ERROR
        assert testimony.note.startswith("affordance failed:")

    asyncio.run(check())


def test_probe_defects_map_to_domain_defects() -> None:
    async def check() -> None:
        browser = FakeBrowser(
            [{"probe": {"defects": [
                {
                    "type": "horizontal_overflow",
                    "selector": "main > a:nth-of-type(1)",
                    "detail": "40px wider than its container",
                },
                {"type": "unknown", "selector": "body"},
            ]}}]
        )
        testimony = await Witness(Context(), browser).visit(SURFACE)

        assert testimony.outcome is Outcome.PARTIAL
        assert testimony.defects == [Defect.HORIZONTAL_OVERFLOW]
        assert testimony.observations == [DefectObservation(
            Defect.HORIZONTAL_OVERFLOW,
            "main > a:nth-of-type(1)",
            "40px wider than its container",
        )]

    asyncio.run(check())


def test_screencast_delivers_jpegs_without_blocking_and_stops_cleanly() -> None:
    async def check() -> None:
        browser = FakeBrowser()
        witness = Witness(Context(), browser)
        received: list[tuple[bytes, dict[str, Any]]] = []

        async def consume(frame: bytes, metadata: dict[str, Any]) -> None:
            await asyncio.sleep(0)
            received.append((frame, metadata))

        await witness.start_screencast(consume)
        session = browser.contexts[0].cdp
        session.emit(
            "Page.screencastFrame",
            {"data": base64.b64encode(b"\\xff\\xd8jpeg").decode(), "metadata": {"timestamp": 1}, "sessionId": 9},
        )
        await asyncio.sleep(0.01)
        await witness.stop_screencast()
        session.emit(
            "Page.screencastFrame",
            {"data": base64.b64encode(b"later").decode(), "metadata": {}, "sessionId": 10},
        )

        assert received == [(b"\\xff\\xd8jpeg", {"timestamp": 1})]
        assert ("Page.startScreencast", {"format": "jpeg", "quality": 60}) in session.sent
        assert ("Page.stopScreencast", None) in session.sent
        assert ("Page.screencastFrameAck", {"sessionId": 9}) in session.sent
        assert witness.screencast_ack_count == 1
        assert session.detached
        await witness.close()

    asyncio.run(check())


def test_witnesses_visit_concurrently_rather_than_one_after_another() -> None:
    """Simultaneity is the thesis, not an optimisation.

    A sequential run cannot observe the relational axis at all: by the time the
    receiver looks, the sender's session is already closed.
    """
    live = 0
    peak = 0

    class ConcurrentPage(FakePage):
        async def goto(self, url: str, **kwargs: Any) -> FakeResponse:
            nonlocal live, peak
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.01)
            live -= 1
            return await super().goto(url, **kwargs)

    class ConcurrentBrowser(FakeBrowser):
        async def new_context(self, **options: Any) -> FakeBrowserContext:
            self.context_options.append(options)
            context = FakeBrowserContext({})
            context.page = ConcurrentPage({})
            self.contexts.append(context)
            return context

    async def check() -> None:
        browser = ConcurrentBrowser()
        testimonies = await run_witnesses(SURFACE, browser=browser)

        assert len(testimonies) == 7
        assert peak == 7   # all seven in flight at the same instant

    asyncio.run(check())


def test_probe_geometry_and_layout_signature_reach_the_testimony() -> None:
    """Dropping these makes the mirror test and the theme invariant unobservable."""
    async def check() -> None:
        browser = FakeBrowser([{
            "probe": {
                "defects": [],
                "contentSignature": "content",
                "layoutSignature": "layout-1",
                "geometry": [{"selector": "#nav", "tag": "nav", "x": 20, "y": 10, "w": 200, "h": 40, "text": ""}],
            }
        }])
        testimony = await Witness(Context(), browser).visit(SURFACE)

        assert testimony.layout_signature == "layout-1"
        assert testimony.geometry == [
            {"selector": "#nav", "tag": "nav", "x": 20, "y": 10, "w": 200, "h": 40, "text": ""}
        ]

    asyncio.run(check())


def test_navigation_or_probe_failure_becomes_recorded_error() -> None:
    async def check() -> None:
        navigation = await Witness(
            Context(), FakeBrowser([{"navigation_error": RuntimeError("offline")}])
        ).visit(SURFACE)
        probe = await Witness(
            Context(), FakeBrowser([{"probe_error": RuntimeError("bad probe")}])
        ).visit(SURFACE)

        assert navigation.outcome is Outcome.ERROR
        assert navigation.note.startswith("navigation failed:")
        assert probe.outcome is Outcome.ERROR
        assert probe.note.startswith("probe failed:")

    asyncio.run(check())


def test_a_control_that_is_absent_is_not_reported_as_a_redirect() -> None:
    """The page was served and stayed put; only the control was missing.

    `_note_for` fell through both 4xx branches with status 200 and an unchanged
    path, and returned "redirected to /threads/1" — a false statement about
    what happened that reaches every consumer of the note, including the
    emitted spec.
    """
    from parallax.witness import Witness

    note = Witness._note_for(Outcome.BLOCKED, 200, "/threads/1", [], affordance="button#delete")

    assert "redirected" not in note
    assert "button#delete" in note and "not rendered" in note


def test_a_real_redirect_still_reads_as_one() -> None:
    from parallax.witness import Witness

    assert Witness._note_for(Outcome.BLOCKED, 200, "/login", []) == "redirected to /login"
    assert Witness._note_for(Outcome.BLOCKED, 404, "/gone", []) == "HTTP 404: absent"
