from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from parallax.conductor import Conductor, RelationalScenario
from parallax.types import Axis, Context, Defect, Finding, FindingKind, Outcome, Privilege, Severity, Surface, SurfaceKind


SITE = "https://app.example.test"


def jpeg(color: tuple[int, int, int]) -> bytes:
    data = BytesIO()
    Image.new("RGB", (12, 8), color).save(data, format="JPEG")
    return data.getvalue()


@dataclass
class FakeResponse:
    status: int = 200


class FakeCDPSession:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any] | None]] = []
        self.handlers: dict[str, Any] = {}

    def on(self, name: str, handler: Any) -> None:
        self.handlers[name] = handler

    def remove_listener(self, name: str, handler: Any) -> None:
        if self.handlers.get(name) is handler:
            del self.handlers[name]

    async def send(self, name: str, params: dict[str, Any] | None = None) -> None:
        self.sent.append((name, params))
        if name == "Page.startScreencast":
            handler = self.handlers["Page.screencastFrame"]
            for seq, color in enumerate(((10, 10, 10), (200, 200, 200)), 1):
                handler({"data": base64.b64encode(jpeg(color)).decode(), "metadata": {}, "sessionId": seq})

    async def detach(self) -> None:
        pass


class FakeLocator:
    def __init__(self, visible: bool = True) -> None:
        self.visible = visible

    async def is_visible(self) -> bool:
        return self.visible


class FakePage:
    def __init__(self, browser: "FakeBrowser", behavior: dict[str, Any]) -> None:
        self.browser = browser
        self.behavior = behavior
        self.url = SITE + "/"

    async def goto(self, url: str, **_kwargs: Any) -> FakeResponse:
        self.url = url
        self.browser.live += 1
        self.browser.peak = max(self.browser.peak, self.browser.live)
        await asyncio.sleep(0.005)
        self.browser.live -= 1
        if self.behavior.get("error"):
            raise RuntimeError("offline")
        return FakeResponse()

    async def wait_for_load_state(self, _state: str, **_kwargs: Any) -> None:
        pass

    async def evaluate(self, source: str) -> dict[str, Any]:
        if "PARALLAX_DISCOVERY" in source:
            return self.behavior.get("discovery", {}).get(self.url, {"links": [], "affordances": []})
        return self.behavior.get("probe", {
            "defects": [], "contentSignature": "same", "layoutSignature": "same",
            "geometry": [{"selector": "#nav", "tag": "nav", "x": 20, "y": 10, "w": 200, "h": 40, "text": ""}],
        })

    def locator(self, _selector: str) -> FakeLocator:
        return FakeLocator(self.behavior.get("visible", True))


class FakeBrowserContext:
    def __init__(self, browser: "FakeBrowser", behavior: dict[str, Any]) -> None:
        self.page = FakePage(browser, behavior)
        self.cdp = FakeCDPSession()
        self.closed = False

    async def add_init_script(self, _script: str) -> None:
        pass

    async def new_page(self) -> FakePage:
        return self.page

    async def new_cdp_session(self, _page: FakePage) -> FakeCDPSession:
        return self.cdp

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, behaviors: list[dict[str, Any]]) -> None:
        self.behaviors = list(behaviors)
        self.contexts: list[FakeBrowserContext] = []
        self.live = 0
        self.peak = 0

    async def new_context(self, **_options: Any) -> FakeBrowserContext:
        behavior = self.behaviors.pop(0) if self.behaviors else {}
        context = FakeBrowserContext(self, behavior)
        self.contexts.append(context)
        return context


class Specialist:
    name = "test-lens"

    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    def judge(self, moments: object, testimonies: object) -> list[Finding]:
        self.calls.append((moments, testimonies))
        testimony = list(testimonies)[0]
        return [Finding(FindingKind.RENDER_DEFECT, Severity.LOW, testimony.surface, Axis.BASELINE, "specialist", [testimony])]


def test_conductor_discovers_bounds_runs_concurrently_and_publishes(tmp_path: Path) -> None:
    async def check() -> None:
        discovery = {
            f"{SITE}/": {"links": ["/inside", "https://elsewhere.test/nope"], "affordances": [{"selector": "#menu", "label": "Menu"}]},
            f"{SITE}/inside": {"links": ["/third"], "affordances": []},
        }
        baseline = {"discovery": discovery}
        # first context is discovery; subsequent seven are the first surface.
        browser = FakeBrowser([baseline] + [{} for _ in range(28)])
        specialist = Specialist()
        result = await Conductor(
            f"{SITE}/", tmp_path, browser=browser, specialists=[specialist], max_surfaces=3, settle_ms=0
        ).conduct()

        assert len(result.surfaces) == 3
        assert all(surface.path.startswith(SITE) for surface in result.surfaces)
        assert browser.peak >= 7
        assert len(result.testimonies) == 21
        assert specialist.calls and specialist.calls[0][0] and specialist.calls[0][1]
        assert any(finding.summary == "specialist" for finding in result.findings)
        assert result.spec_paths and all(path.exists() for path in result.spec_paths)

        events = [json.loads(line) for line in result.feed_path.read_text().splitlines()]
        assert {event["kind"] for event in events} >= {"status", "mosaic", "finding"}
        mosaic = next(event for event in events if event["kind"] == "mosaic")
        image = tmp_path / mosaic["payload"]["image"]
        assert image.exists() and not mosaic["payload"]["image"].startswith("data:")

    asyncio.run(check())


def test_discovery_stays_within_the_start_path_and_origin(tmp_path: Path) -> None:
    async def check() -> None:
        for start in (f"{SITE}/shop", f"{SITE}/shop/"):
            discovery = {
                f"{SITE}/shop": {"links": ["/shop/inside", "/sibling", "https://elsewhere.test/nope"], "affordances": []},
                f"{SITE}/shop/inside": {"links": [], "affordances": []},
            }
            browser = FakeBrowser([{"discovery": discovery}])
            conductor = Conductor(start, tmp_path, browser=browser)

            surfaces = await conductor._discover()

            assert [surface.path for surface in surfaces] == [f"{SITE}/shop", f"{SITE}/shop/inside"]

    asyncio.run(check())


def test_discovery_reaches_a_second_level_route_before_first_page_affordances(tmp_path: Path) -> None:
    async def check() -> None:
        discovery = {
            f"{SITE}/": {
                "links": ["/member"],
                "affordances": [{"selector": "#profile", "label": "Profile"}],
            },
            f"{SITE}/member": {"links": ["/audit"], "affordances": []},
            f"{SITE}/audit": {"links": [], "affordances": []},
        }
        surfaces = await Conductor(
            f"{SITE}/", tmp_path, browser=FakeBrowser([{"discovery": discovery}]), max_surfaces=3
        )._discover()

        assert [surface.path for surface in surfaces] == [f"{SITE}/", f"{SITE}/member", f"{SITE}/audit"]

    asyncio.run(check())


def test_discovery_normalizes_duplicate_route_links_and_trailing_slashes(tmp_path: Path) -> None:
    async def check() -> None:
        discovery = {
            f"{SITE}/": {
                "links": ["/audit", "/audit/", "audit", "/audit?b=2&a=1", "/audit?a=1&b=2"],
                "affordances": [],
            },
            f"{SITE}/audit": {"links": [], "affordances": []},
            f"{SITE}/audit?a=1&b=2": {"links": [], "affordances": []},
        }
        surfaces = await Conductor(
            f"{SITE}/", tmp_path, browser=FakeBrowser([{"discovery": discovery}]), max_surfaces=4
        )._discover()

        assert [surface.path for surface in surfaces] == [
            f"{SITE}/",
            f"{SITE}/audit",
            f"{SITE}/audit?a=1&b=2",
        ]

    asyncio.run(check())


def test_discovery_prioritizes_unrepresented_routes_over_affordances(tmp_path: Path) -> None:
    async def check() -> None:
        discovery = {
            f"{SITE}/": {
                "links": ["/account", "/audit"],
                "affordances": [
                    {"selector": "#sign-out", "label": "Sign out"},
                    {"selector": "#settings", "label": "Settings"},
                ],
            },
            f"{SITE}/account": {"links": [], "affordances": []},
            f"{SITE}/audit": {"links": [], "affordances": []},
        }
        surfaces = await Conductor(
            f"{SITE}/", tmp_path, browser=FakeBrowser([{"discovery": discovery}]), max_surfaces=3
        )._discover()

        assert [(surface.kind.value, surface.path) for surface in surfaces] == [
            ("route", f"{SITE}/"),
            ("route", f"{SITE}/account"),
            ("route", f"{SITE}/audit"),
        ]

    asyncio.run(check())


def test_moments_are_harvested_while_the_witnesses_are_still_working(tmp_path: Path) -> None:
    """Ticking once after everyone finishes would leave only an end-state snapshot."""

    class StreamingCDPSession(FakeCDPSession):
        def __init__(self) -> None:
            super().__init__()
            self.stream: asyncio.Task[None] | None = None

        async def send(self, name: str, params: dict[str, Any] | None = None) -> None:
            self.sent.append((name, params))
            if name != "Page.startScreencast":
                return
            handler = self.handlers["Page.screencastFrame"]

            async def emit() -> None:
                for seq in range(1, 9):
                    handler({"data": base64.b64encode(jpeg((seq * 25, 10, 10))).decode(), "metadata": {}, "sessionId": seq})
                    await asyncio.sleep(0.006)

            self.stream = asyncio.create_task(emit())

        async def detach(self) -> None:
            if self.stream is not None:
                self.stream.cancel()

    class SlowPage(FakePage):
        async def goto(self, url: str, **_kwargs: Any) -> FakeResponse:
            self.url = url
            await asyncio.sleep(0.08)   # long enough for the wall to change under us
            return FakeResponse()

    class StreamingBrowser(FakeBrowser):
        async def new_context(self, **_options: Any) -> FakeBrowserContext:
            behavior = self.behaviors.pop(0) if self.behaviors else {}
            context = FakeBrowserContext(self, behavior)
            context.page = SlowPage(self, behavior)
            context.cdp = StreamingCDPSession()
            self.contexts.append(context)
            return context

    async def check() -> None:
        browser = StreamingBrowser(
            [{"discovery": {f"{SITE}/": {"links": [], "affordances": []}}}] + [{} for _ in range(8)]
        )
        result = await Conductor(
            f"{SITE}/", tmp_path, browser=browser, max_surfaces=1, settle_ms=0, poll_ms=1
        ).conduct()

        events = [json.loads(line) for line in result.feed_path.read_text().splitlines()]
        mosaics = [event for event in events if event["kind"] == "mosaic"]
        assert len(mosaics) >= 2

    asyncio.run(check())


def test_final_flush_never_publishes_a_wall_with_an_unpainted_context(tmp_path: Path) -> None:
    class NoFrameCDPSession(FakeCDPSession):
        async def send(self, name: str, params: dict[str, Any] | None = None) -> None:
            self.sent.append((name, params))

    class OneSilentWitnessBrowser(FakeBrowser):
        async def new_context(self, **options: Any) -> FakeBrowserContext:
            context = await super().new_context(**options)
            # Discovery takes the first context; the seventh witness is silent.
            if len(self.contexts) == 8:
                context.cdp = NoFrameCDPSession()
            return context

    async def check() -> None:
        browser = OneSilentWitnessBrowser(
            [{"discovery": {f"{SITE}/": {"links": [], "affordances": []}}}] + [{} for _ in range(7)]
        )
        result = await Conductor(
            f"{SITE}/", tmp_path, browser=browser, max_surfaces=1, settle_ms=0, poll_ms=1
        ).conduct()

        events = [json.loads(line) for line in result.feed_path.read_text().splitlines()]
        assert not [event for event in events if event["kind"] == "mosaic"]

    asyncio.run(check())


def test_mirror_defects_are_present_when_differ_runs_and_errors_do_not_abort(tmp_path: Path, monkeypatch: Any) -> None:
    async def check() -> None:
        import parallax.conductor as conductor_module

        seen: list[list[object]] = []
        original_compare = conductor_module.compare

        def capture(testimonies: object) -> list[Finding]:
            items = list(testimonies)
            seen.append(items)
            return original_compare(items)

        monkeypatch.setattr(conductor_module, "compare", capture)
        geometry = [{"selector": "#nav", "tag": "nav", "x": 20, "y": 10, "w": 200, "h": 40, "text": ""}]
        arabic = [{"selector": "#nav", "tag": "nav", "x": 20, "y": 10, "w": 200, "h": 40, "text": ""}]
        behaviors = [{"discovery": {f"{SITE}/": {"links": [], "affordances": []}}}]
        for index in range(7):
            probe = {"defects": [], "contentSignature": "same", "layoutSignature": "same", "geometry": arabic if index == 3 else geometry}
            behaviors.append({"probe": probe, "error": index == 6})
        result = await Conductor(f"{SITE}/", tmp_path, browser=FakeBrowser(behaviors), settle_ms=0).conduct()

        assert len(result.testimonies) == 7
        assert any(testimony.note.startswith("navigation failed") for testimony in result.testimonies)
        assert seen
        locale = next(testimony for testimony in seen[0] if testimony.context.varies is Axis.LOCALE)
        assert Defect.RTL_NOT_MIRRORED in locale.defects

    asyncio.run(check())


def _relational_scenario(action: Any, effect: str = "#message") -> RelationalScenario:
    return RelationalScenario(
        Surface(SurfaceKind.ROUTE, f"{SITE}/threads"),
        sender=Context(privilege=Privilege.OWNER),
        receiver=Context(privilege=Privilege.MEMBER),
        action=action,
        effect=effect,
        deadline_ms=30,
    )


def test_sweep_without_relational_scenarios_preserves_ordinary_findings(tmp_path: Path) -> None:
    async def check() -> None:
        discovery = {f"{SITE}/": {"links": [], "affordances": []}}
        first = await Conductor(
            f"{SITE}/", tmp_path / "first", browser=FakeBrowser([{"discovery": discovery}] + [{} for _ in range(7)]), settle_ms=0
        ).conduct()
        second = await Conductor(
            f"{SITE}/", tmp_path / "second", browser=FakeBrowser([{"discovery": discovery}] + [{} for _ in range(7)]), settle_ms=0,
            relational_scenarios=[],
        ).conduct()

        assert [(finding.kind, finding.axis, finding.summary, finding.evidence_line()) for finding in first.findings] == [
            (finding.kind, finding.axis, finding.summary, finding.evidence_line()) for finding in second.findings
        ]
        assert len(first.testimonies) == len(second.testimonies) == 7

    asyncio.run(check())


def test_relational_failure_is_published_emitted_and_keeps_sessions_overlapping(tmp_path: Path) -> None:
    async def check() -> None:
        discovery = {f"{SITE}/": {"links": [], "affordances": []}}
        browser = FakeBrowser([{"discovery": discovery}] + [{} for _ in range(7)] + [{}, {"visible": False}])
        overlap: list[bool] = []

        async def send(_page: object) -> None:
            overlap.append(len(browser.contexts) >= 10 and all(not context.closed for context in browser.contexts[-2:]))

        result = await Conductor(
            f"{SITE}/", tmp_path, browser=browser, settle_ms=0, poll_ms=1,
            relational_scenarios=[_relational_scenario(send)],
        ).conduct()

        findings = [finding for finding in result.findings if finding.kind is FindingKind.PROPAGATION_FAILURE]
        assert len(findings) == 1
        finding = findings[0]
        assert finding.axis is Axis.RELATIONAL
        assert {testimony.context.privilege for testimony in finding.testimonies} == {Privilege.OWNER, Privilege.MEMBER}
        assert overlap == [True]
        events = [json.loads(line) for line in result.feed_path.read_text().splitlines()]
        assert any(event["kind"] == "finding" for event in events)
        assert any(event["kind"] == "mosaic" for event in events)
        assert any("propagation-relational" in path.name and path.exists() for path in result.spec_paths)

    asyncio.run(check())


def test_relational_effect_before_deadline_yields_no_propagation_finding(tmp_path: Path) -> None:
    async def check() -> None:
        discovery = {f"{SITE}/": {"links": [], "affordances": []}}
        browser = FakeBrowser([{"discovery": discovery}] + [{} for _ in range(7)] + [{}, {"visible": False}])

        async def send(_page: object) -> None:
            browser.contexts[-1].page.behavior["visible"] = True

        result = await Conductor(
            f"{SITE}/", tmp_path, browser=browser, settle_ms=0,
            relational_scenarios=[_relational_scenario(send)],
        ).conduct()

        assert not [finding for finding in result.findings if finding.kind is FindingKind.PROPAGATION_FAILURE]

    asyncio.run(check())


def test_relational_action_error_is_evidence_without_aborting_the_sweep(tmp_path: Path) -> None:
    async def check() -> None:
        discovery = {f"{SITE}/": {"links": [], "affordances": []}}
        browser = FakeBrowser([{"discovery": discovery}] + [{} for _ in range(7)] + [{}, {"visible": False}])

        async def broken_send(_page: object) -> None:
            raise RuntimeError("send failed")

        result = await Conductor(
            f"{SITE}/", tmp_path, browser=browser, settle_ms=0,
            relational_scenarios=[_relational_scenario(broken_send)],
        ).conduct()

        relational = [testimony for testimony in result.testimonies if testimony.context.varies is Axis.RELATIONAL]
        assert len(relational) == 2
        assert any(testimony.outcome is Outcome.ERROR and "send failed" in testimony.note for testimony in relational)
        assert result.surfaces

    asyncio.run(check())
