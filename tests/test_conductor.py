from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from parallax.conductor import Conductor
from parallax.types import Axis, Defect, Finding, FindingKind, Severity


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
    async def is_visible(self) -> bool:
        return True


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
        return FakeLocator()


class FakeBrowserContext:
    def __init__(self, browser: "FakeBrowser", behavior: dict[str, Any]) -> None:
        self.page = FakePage(browser, behavior)
        self.cdp = FakeCDPSession()

    async def add_init_script(self, _script: str) -> None:
        pass

    async def new_page(self) -> FakePage:
        return self.page

    async def new_cdp_session(self, _page: FakePage) -> FakeCDPSession:
        return self.cdp

    async def close(self) -> None:
        pass


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
                start: {"links": ["/shop/inside", "/sibling", "https://elsewhere.test/nope"], "affordances": []},
                f"{SITE}/shop/inside": {"links": [], "affordances": []},
            }
            browser = FakeBrowser([{"discovery": discovery}])
            conductor = Conductor(start, tmp_path, browser=browser)

            surfaces = await conductor._discover()

            assert [surface.path for surface in surfaces] == [start, f"{SITE}/shop/inside"]

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
