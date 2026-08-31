from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from parallax.conductor import Conductor, RelationalScenario, assess_axis_applicability
from parallax.__main__ import relational_scenarios_from_data
from parallax.contracts import finding_payload
from parallax.proposer import ProposalBatch, ProposalCandidate
from parallax.types import Axis, Context, Defect, Finding, FindingKind, Locale, Outcome, Privilege, Severity, Surface, SurfaceKind, Testimony as WitnessTestimony


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
        return [Finding(FindingKind.RENDER_DEFECT, Severity.LOW, testimony.surface, Axis.BASELINE,
                        "specialist", [testimony], defect=Defect.HORIZONTAL_OVERFLOW)]


def test_axis_applicability_requires_page_claims_and_distinct_role_states() -> None:
    surface = Surface(SurfaceKind.ROUTE, f"{SITE}/")
    baseline = WitnessTestimony(surface, Context(), Outcome.REACHED, document_lang="en", support={
        "localeAlternate": True, "themeMedia": True, "viewportMeta": True,
    })
    arabic = WitnessTestimony(surface, Context(locale=Locale.AR, varies=Axis.LOCALE), Outcome.REACHED, document_lang="ar")
    decisions = assess_axis_applicability(
        [baseline, arabic], {"owner": {"cookies": ["owner"]}, "member": {"cookies": ["member"]}},
    )

    assert all(decision.applicable for decision in decisions)


def test_privilege_axis_rejects_different_paths_with_identical_state_content(tmp_path: Path) -> None:
    surface = Surface(SurfaceKind.ROUTE, f"{SITE}/")
    testimony = WitnessTestimony(surface, Context(), Outcome.REACHED)
    owner = tmp_path / "owner.json"
    member = tmp_path / "member.json"
    owner.write_text('{"cookies":[{"name":"session","value":"same"}],"origins":[]}', encoding="utf-8")
    member.write_bytes(owner.read_bytes())

    privilege = next(decision for decision in assess_axis_applicability(
        [testimony], {"owner": owner, "member": member},
    ) if decision.axis is Axis.PRIVILEGE)

    assert not privilege.applicable


def test_axis_applicability_reports_every_missing_claim() -> None:
    surface = Surface(SurfaceKind.ROUTE, f"{SITE}/")
    decisions = assess_axis_applicability([WitnessTestimony(surface, Context(), Outcome.REACHED)], None)

    assert {decision.axis for decision in decisions} == {Axis.PRIVILEGE, Axis.LOCALE, Axis.THEME, Axis.VIEWPORT}
    assert all(not decision.applicable for decision in decisions)
    assert all(decision.reason for decision in decisions)


def test_conductor_publishes_not_applicable_axes_without_their_findings(tmp_path: Path) -> None:
    async def check() -> None:
        behaviors = [{"discovery": {f"{SITE}/": {"links": [], "affordances": []}}}]
        for index in range(7):
            defects = [{"type": "offscreen_control"}] if index == 5 else []
            behaviors.append({"probe": {"defects": defects}})
        result = await Conductor(f"{SITE}/", tmp_path, browser=FakeBrowser(behaviors), settle_ms=0).conduct()

        events = [json.loads(line) for line in result.feed_path.read_text().splitlines()]
        decisions = [event["payload"] for event in events if event["payload"].get("state") == "axis_applicability"]

        assert result.findings == []
        assert len(decisions) == 4
        assert all(not decision["applicable"] and decision["reason"] for decision in decisions)

    asyncio.run(check())


def test_finding_payload_carries_its_mosaic_reference() -> None:
    from parallax.contracts import MosaicFrame, Tile
    from parallax.types import BASELINE, Outcome, Surface, SurfaceKind

    surface = Surface(SurfaceKind.ROUTE, f"{SITE}/shop?category=paper")
    finding = Finding(
        FindingKind.RENDER_DEFECT,
        Severity.LOW,
        surface,
        Axis.BASELINE,
        "paper listing clips its heading",
        [WitnessTestimony(surface, BASELINE, Outcome.PARTIAL)],
    )
    mosaic = MosaicFrame(jpeg((12, 34, 56)), (Tile(BASELINE.name, 0, 0, 12, 8),), seq=17)

    payload = finding_payload(finding, mosaic=mosaic)

    assert payload["mosaic"] == {"surface_id": surface.id, "seq": 17}


def test_render_findings_with_distinct_defects_survive_identity_deduplication() -> None:
    from parallax.conductor import _unpublished_findings

    surface = Surface(SurfaceKind.ROUTE, f"{SITE}/shop")
    testimony = WitnessTestimony(
        surface,
        Context(),
        Outcome.PARTIAL,
        defects=[Defect.HORIZONTAL_OVERFLOW, Defect.SMALL_TAP_TARGET],
    )
    findings = [
        Finding(
            FindingKind.RENDER_DEFECT,
            Severity.MEDIUM,
            surface,
            Axis.VIEWPORT,
            "wide content",
            [testimony],
            defect=Defect.HORIZONTAL_OVERFLOW,
        ),
        Finding(
            FindingKind.RENDER_DEFECT,
            Severity.LOW,
            surface,
            Axis.VIEWPORT,
            "small control",
            [testimony],
            defect=Defect.SMALL_TAP_TARGET,
        ),
    ]

    unpublished = _unpublished_findings(findings, set())

    assert unpublished == findings
    base_identity = f"render-viewport-{surface.id}"
    assert [finding.id for finding in unpublished] == [
        f"{base_identity}-horizontal_overflow",
        f"{base_identity}-small_tap_target",
    ]


def test_conductor_finding_reference_uses_its_surface_mosaic(tmp_path: Path) -> None:
    async def check() -> None:
        discovery = {
            f"{SITE}/": {"links": ["/shop?category=paper"], "affordances": []},
            f"{SITE}/shop?category=paper": {"links": [], "affordances": []},
        }
        result = await Conductor(
            f"{SITE}/", tmp_path, browser=FakeBrowser([{"discovery": discovery}] + [{} for _ in range(14)]),
            specialists=[Specialist()], max_surfaces=2, settle_ms=0,
        ).conduct()

        events = [json.loads(line) for line in result.feed_path.read_text().splitlines()]
        mosaics = [event["payload"] for event in events if event["kind"] == "mosaic"]
        finding = next(event["payload"] for event in events if event["kind"] == "finding" and event["payload"]["surface_id"] == result.surfaces[1].id)

        assert finding["mosaic"]["surface_id"] == result.surfaces[1].id
        assert finding["mosaic"] in [{"surface_id": mosaic["surface_id"], "seq": mosaic["seq"]} for mosaic in mosaics]

    asyncio.run(check())


def test_conductor_finding_without_settled_moment_carries_no_mosaic_reference(tmp_path: Path) -> None:
    class NoFrameCDPSession(FakeCDPSession):
        async def send(self, name: str, params: dict[str, Any] | None = None) -> None:
            self.sent.append((name, params))

    class SilentBrowser(FakeBrowser):
        async def new_context(self, **options: Any) -> FakeBrowserContext:
            context = await super().new_context(**options)
            if len(self.contexts) > 1:
                context.cdp = NoFrameCDPSession()
            return context

    async def check() -> None:
        result = await Conductor(
            f"{SITE}/", tmp_path,
            browser=SilentBrowser([{"discovery": {f"{SITE}/": {"links": [], "affordances": []}}}] + [{} for _ in range(7)]),
            specialists=[Specialist()], max_surfaces=1, settle_ms=0,
        ).conduct()
        events = [json.loads(line) for line in result.feed_path.read_text().splitlines()]
        finding = next(event["payload"] for event in events if event["kind"] == "finding")

        assert finding["mosaic"] is None

    asyncio.run(check())


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


def test_conductor_records_each_witness_own_visible_offers(tmp_path: Path) -> None:
    async def check() -> None:
        privileged = Surface(SurfaceKind.ROUTE, f"{SITE}/settings")
        owner_discovery = {f"{SITE}/": {"links": ["/settings"], "affordances": []}}
        hidden_discovery = {f"{SITE}/": {"links": [], "affordances": []}}
        browser = FakeBrowser(
            [{"discovery": owner_discovery}]
            + [{"discovery": owner_discovery}]
            + [{"discovery": hidden_discovery} for _ in range(6)]
        )

        result = await Conductor(f"{SITE}/", tmp_path, browser=browser, max_surfaces=1, settle_ms=0).conduct()

        owner = next(testimony for testimony in result.testimonies if testimony.context.varies is Axis.BASELINE)
        anonymous = next(testimony for testimony in result.testimonies if testimony.context.privilege is Privilege.ANON)
        assert privileged in owner.offered_surfaces  # type: ignore[attr-defined]
        assert privileged not in anonymous.offered_surfaces  # type: ignore[attr-defined]

    asyncio.run(check())


def test_conductor_reports_an_unoffered_anonymous_reach_without_a_blocked_witness(tmp_path: Path) -> None:
    async def check() -> None:
        owner_discovery = {f"{SITE}/": {"links": ["/settings"], "affordances": []}}
        hidden_discovery = {f"{SITE}/": {"links": [], "affordances": []}}
        browser = FakeBrowser(
            [{"discovery": owner_discovery}]
            + [{"discovery": owner_discovery}]
            + [{"discovery": hidden_discovery} for _ in range(6)]
            + [{} for _ in range(7)]
        )

        result = await Conductor(
            f"{SITE}/", tmp_path, browser=browser, max_surfaces=2, settle_ms=0,
            storage_states={"owner": {"cookies": ["owner"]}, "member": {"cookies": ["member"]}},
        ).conduct()

        escalations = [finding for finding in result.findings if finding.kind is FindingKind.ESCALATION]
        assert len(escalations) == 1
        assert escalations[0].severity is Severity.HIGH
        assert all(testimony.outcome is not Outcome.BLOCKED for testimony in escalations[0].testimonies)

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


def test_second_surface_never_publishes_a_wall_with_a_stale_context(tmp_path: Path) -> None:
    class NoFrameCDPSession(FakeCDPSession):
        async def send(self, name: str, params: dict[str, Any] | None = None) -> None:
            self.sent.append((name, params))

    class OneSilentWitnessBrowser(FakeBrowser):
        async def new_context(self, **options: Any) -> FakeBrowserContext:
            context = await super().new_context(**options)
            # Discovery takes the first context; the seventh witness on the
            # second surface is silent. Its old first-surface frame must not
            # count as paint for the new surface.
            if len(self.contexts) == 15:
                context.cdp = NoFrameCDPSession()
            return context

    async def check() -> None:
        browser = OneSilentWitnessBrowser(
            [{"discovery": {f"{SITE}/": {"links": ["/second"], "affordances": []}}}] + [{} for _ in range(14)]
        )
        result = await Conductor(
            f"{SITE}/", tmp_path, browser=browser, max_surfaces=2, settle_ms=0, poll_ms=1
        ).conduct()

        events = [json.loads(line) for line in result.feed_path.read_text().splitlines()]
        assert [event for event in events if event["kind"] == "mosaic"]
        assert not [
            event for event in events
            if event["kind"] == "mosaic" and event["payload"]["surface_id"] == result.surfaces[1].id
        ]

    asyncio.run(check())


def test_mirror_observations_reach_the_differ_without_mutating_witness_evidence(tmp_path: Path, monkeypatch: Any) -> None:
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
            probe = {
                "defects": [], "contentSignature": "same", "layoutSignature": "same",
                "geometry": arabic if index == 3 else geometry, "support": {"localeAlternate": True},
            }
            behaviors.append({"probe": probe, "error": index == 6})
        result = await Conductor(f"{SITE}/", tmp_path, browser=FakeBrowser(behaviors), settle_ms=0).conduct()

        assert len(result.testimonies) == 7
        assert any(testimony.note.startswith("navigation failed") for testimony in result.testimonies)
        assert seen
        locale = next(testimony for testimony in seen[0] if testimony.context.varies is Axis.LOCALE)
        assert Defect.RTL_NOT_MIRRORED in locale.defects
        assert locale.observations[0].defect is Defect.RTL_NOT_MIRRORED
        assert locale.observations[0].selector == "#nav"
        recorded_locale = next(testimony for testimony in result.testimonies if testimony.context.varies is Axis.LOCALE)
        assert Defect.RTL_NOT_MIRRORED not in recorded_locale.defects

    asyncio.run(check())


def test_mirror_observations_use_each_surface_own_baseline() -> None:
    from parallax.conductor import _with_mirror_observations

    first_surface = Surface(SurfaceKind.ROUTE, f"{SITE}/first")
    second_surface = Surface(SurfaceKind.ROUTE, f"{SITE}/second")
    arabic = Context(locale=Locale.AR, varies=Axis.LOCALE)

    def testimony(surface: Surface, context: Context, x: int) -> WitnessTestimony:
        return WitnessTestimony(
            surface,
            context,
            Outcome.REACHED,
            geometry=[{"selector": "#nav", "tag": "nav", "x": x, "y": 10, "w": 200, "h": 40, "text": ""}],
        )

    observed = _with_mirror_observations([
        testimony(first_surface, Context(), 20),
        testimony(first_surface, arabic, 1220),
        testimony(second_surface, Context(), 40),
        testimony(second_surface, arabic, 40),
    ])

    first_locale, second_locale = observed[1], observed[3]
    assert Defect.RTL_NOT_MIRRORED not in first_locale.defects
    assert Defect.RTL_NOT_MIRRORED in second_locale.defects


def test_specialists_are_isolated_deduplicated_and_failures_are_reported(tmp_path: Path) -> None:
    class BrokenLens:
        name = "broken"

        def judge(self, _moments: object, testimonies: object) -> list[Finding]:
            first = list(testimonies)[0]
            first.defects.append(Defect.CLIPPED)
            raise RuntimeError("lens broke")

    class DuplicateLens:
        name = "duplicate"

        def __init__(self) -> None:
            self.saw_unmodified_evidence = False

        def judge(self, _moments: object, testimonies: object) -> list[Finding]:
            first = list(testimonies)[0]
            self.saw_unmodified_evidence = first.defects == []
            return [Finding(FindingKind.RENDER_DEFECT, Severity.LOW, first.surface, Axis.LOCALE,
                            "duplicate", [first], defect=Defect.HORIZONTAL_OVERFLOW)]

    async def check() -> None:
        duplicate = DuplicateLens()
        browser = FakeBrowser(
            [{"discovery": {f"{SITE}/": {"links": [], "affordances": []}}}]
            + [{"probe": {"support": {"localeAlternate": True}}} for _ in range(7)]
        )
        result = await Conductor(
            f"{SITE}/", tmp_path, browser=browser, specialists=[BrokenLens(), duplicate], settle_ms=0
        ).conduct()

        assert duplicate.saw_unmodified_evidence
        assert len(result.findings) == 1
        assert result.testimonies[0].defects == []
        assert len(result.spec_paths) == 1
        events = [json.loads(line) for line in result.feed_path.read_text().splitlines()]
        assert any(
            event["kind"] == "status"
            and event["payload"].get("specialist") == "broken"
            and event["payload"].get("state") == "error"
            for event in events
        )

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


def test_conductor_validates_and_runs_proposals_alongside_declared_scenarios(tmp_path: Path) -> None:
    class FakeProposer:
        route = "injected"
        calls_attempted = 1
        calls_succeeded = 1
        last_error = None

        def propose(self, observation: object) -> ProposalBatch:
            assert {item.kind for item in observation.affordances} == {"form"}
            assert set(observation.roles) == {"anon", "member", "owner"}
            return ProposalBatch(1, (ProposalCandidate(1, {"surface": "/threads"}),), ())

    async def check() -> None:
        discovery = {
            f"{SITE}/": {
                "links": [],
                "affordances": [],
                "forms": [{"selector": "form.revoke", "label": "Remove member"}],
            },
        }
        browser = FakeBrowser(
            [{"discovery": discovery}] + [{} for _ in range(7)] + [{}, {"visible": True}] + [{}, {"visible": True}]
        )
        declared = _relational_scenario(lambda _page: None)
        proposed = _relational_scenario(lambda _page: None)

        def validate(data: object, start_url: str, *, source: str) -> list[RelationalScenario]:
            assert data == [{"surface": "/threads"}]
            assert start_url == f"{SITE}/"
            assert source == "proposal 1"
            return [proposed]

        result = await Conductor(
            f"{SITE}/", tmp_path, browser=browser, settle_ms=0, poll_ms=1,
            storage_states={"owner": {"cookies": ["owner"]}, "member": {"cookies": ["member"]}},
            relational_scenarios=[declared], scenario_proposer=FakeProposer(), proposal_validator=validate,
        ).conduct()

        assert result.proposal_report.proposed == result.proposal_report.validated == 1
        assert len([item for item in result.testimonies if item.context.varies is Axis.RELATIONAL]) == 4

    asyncio.run(check())


def test_conductor_records_validator_rejections_without_running_them(tmp_path: Path) -> None:
    class FakeProposer:
        route = "injected"
        calls_attempted = 1
        calls_succeeded = 1
        last_error = None

        def propose(self, _observation: object) -> ProposalBatch:
            return ProposalBatch(1, (ProposalCandidate(1, {"surface": "/threads"}),), ())

    async def check() -> None:
        result = await Conductor(
            f"{SITE}/", tmp_path,
            browser=FakeBrowser([{"discovery": {f"{SITE}/": {"links": [], "affordances": []}}}] + [{} for _ in range(7)]),
            settle_ms=0, scenario_proposer=FakeProposer(), proposal_validator=relational_scenarios_from_data,
        ).conduct()

        assert result.proposal_report.proposed == 1
        assert result.proposal_report.validated == 0
        assert "scenario 1.sender" in result.proposal_report.rejections[0].reason
        assert len(result.testimonies) == 7

    asyncio.run(check())


def test_conduct_removes_only_stale_managed_mosaics(tmp_path: Path) -> None:
    async def check() -> None:
        mosaics = tmp_path / "mosaics"
        mosaics.mkdir()
        stale = mosaics / "0123456789abcdef-999.jpg"
        manual = mosaics / "handwritten.jpg"
        stale.write_bytes(b"stale")
        manual.write_bytes(b"manual")
        discovery = {f"{SITE}/": {"links": [], "affordances": []}}

        await Conductor(
            f"{SITE}/",
            tmp_path,
            browser=FakeBrowser([{"discovery": discovery}] + [{} for _ in range(7)]),
            settle_ms=0,
        ).conduct()

        assert not stale.exists()
        assert manual.read_bytes() == b"manual"

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


def test_non_latin_text_alone_does_not_make_the_locale_axis_applicable() -> None:
    """A monolingual Arabic page has no locale variant to compare against.

    arbchat.org serves dir="rtl" whether asked for lang=ar or lang=en. Treating
    its Arabic content as evidence of a locale mechanism made Parallax compare
    the page to itself and report rtl_not_mirrored on every surface.
    """
    surface = Surface(SurfaceKind.ROUTE, f"{SITE}/")
    baseline = WitnessTestimony(
        surface, Context(), Outcome.REACHED, document_lang="ar", support={"nonLatinText": True}
    )
    variant = WitnessTestimony(
        surface, Context(locale=Locale.AR, varies=Axis.LOCALE), Outcome.REACHED, document_lang="ar"
    )

    decisions = {d.axis: d for d in assess_axis_applicability([baseline, variant], None)}

    assert decisions[Axis.LOCALE].applicable is False
    assert "no localized alternate" in decisions[Axis.LOCALE].reason


def test_a_changed_lang_attribute_still_makes_the_locale_axis_applicable() -> None:
    surface = Surface(SurfaceKind.ROUTE, f"{SITE}/")
    baseline = WitnessTestimony(surface, Context(), Outcome.REACHED, document_lang="en", support={})
    variant = WitnessTestimony(
        surface, Context(locale=Locale.AR, varies=Axis.LOCALE), Outcome.REACHED, document_lang="ar"
    )

    decisions = {d.axis: d for d in assess_axis_applicability([baseline, variant], None)}

    assert decisions[Axis.LOCALE].applicable is True
    assert decisions[Axis.LOCALE].reason == "page lang attribute changes between contexts"


def test_a_confirmed_locale_mechanism_outranks_what_a_single_page_shows() -> None:
    """arbchat.org keeps its language switch in a signed-in user's settings.

    Discovery found it, operated it, and watched the lang attribute change,
    while every individual page still looked monolingual — so the gate skipped
    the axis the same run had just proved exists.
    """
    surface = Surface(SurfaceKind.ROUTE, f"{SITE}/")
    baseline = WitnessTestimony(surface, Context(), Outcome.REACHED, document_lang="ar", support={})
    variant = WitnessTestimony(
        surface, Context(locale=Locale.AR, varies=Axis.LOCALE), Outcome.REACHED, document_lang="ar"
    )

    without = {d.axis: d for d in assess_axis_applicability([baseline, variant], None)}
    with_discovery = {
        d.axis: d for d in assess_axis_applicability([baseline, variant], None, locale_mechanism="control")
    }

    assert without[Axis.LOCALE].applicable is False
    assert with_discovery[Axis.LOCALE].applicable is True
    assert "discovery confirmed a locale mechanism: control" == with_discovery[Axis.LOCALE].reason


def test_a_mechanism_discovery_could_not_find_does_not_open_the_axis() -> None:
    surface = Surface(SurfaceKind.ROUTE, f"{SITE}/")
    baseline = WitnessTestimony(surface, Context(), Outcome.REACHED, document_lang="ar", support={})

    decisions = {d.axis: d for d in assess_axis_applicability([baseline], None, locale_mechanism="none")}

    assert decisions[Axis.LOCALE].applicable is False


def test_a_revocation_without_a_declared_tolerance_is_not_scored_against_zero() -> None:
    """`max_lag_ms or 0` made every unspecified revocation fail its own plane.

    Omitting a tolerance means unspecified, not zero: the effects plane was
    scored `lag_ms <= 0`, which no measurement across a real round trip can
    satisfy, so an application revoking in 40ms was reported as HIGH.
    """
    from parallax.conductor import DEFAULT_REVOCATION_TOLERANCE_MS

    assert DEFAULT_REVOCATION_TOLERANCE_MS > 0
    source = (Path(__file__).resolve().parents[1] / "src" / "parallax" / "conductor.py").read_text(encoding="utf-8")
    assert "max_lag_ms=scenario.max_lag_ms or 0" not in source
    assert "DEFAULT_REVOCATION_TOLERANCE_MS" in source


def test_declared_roles_count_toward_the_privilege_axis() -> None:
    """A run given two custom roles opened both, then threw the evidence away.

    _privilege_reason iterated only the built-in three, so sessions named
    support and superadmin never reached the distinctness check and the axis
    was reported as not applicable — discarding every privilege witness.
    """
    surface = Surface(SurfaceKind.ROUTE, f"{SITE}/")
    testimony = WitnessTestimony(surface, Context(), Outcome.REACHED)

    decisions = {d.axis: d for d in assess_axis_applicability(
        [testimony],
        {"support": {"cookies": [{"name": "s", "value": "one"}]},
         "superadmin": {"cookies": [{"name": "s", "value": "two"}]}},
    )}

    assert decisions[Axis.PRIVILEGE].applicable is True
    assert "distinct role storage states" in decisions[Axis.PRIVILEGE].reason
