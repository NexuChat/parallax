"""Coordinate discovery, simultaneous witnessing, judgement, and publication."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import json
import re
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urldefrag, urljoin, urlsplit, urlunsplit

from .compositor import Compositor
from .contracts import FeedEvent, Frame, Moment, MosaicFrame, Specialist, finding_payload, mosaic_payload
from .differ import compare
from .emitter import emit_all
from .mirror import mirror_defects, mirror_report
from .proposer import BaselineObservation, ObservedAffordance, ProposalRejection, ProposalReport, ScenarioProposer
from .capability import CapabilityRun, CapabilityScenario
from .capability import judge as judge_capability
from .relational import Expectation, RelationalPair
from .types import Axis, AxisApplicability, Context, DefectObservation, Finding, Outcome, Privilege, RelationalReplay, Surface, SurfaceKind, Testimony, derive_witnesses
from .witness import StorageState, Witness


_DISCOVERY_SCRIPT = r"""/* PARALLAX_DISCOVERY */
() => {
  const visible = (element) => {
    const style = getComputedStyle(element); const box = element.getBoundingClientRect();
    return style.visibility !== "hidden" && style.display !== "none" && box.width > 0 && box.height > 0;
  };
  const selector = (element) => {
    if (element.id) return "#" + CSS.escape(element.id);
    const tag = element.tagName.toLowerCase();
    const classes = [...element.classList].filter(Boolean).map((name) => "." + CSS.escape(name)).join("");
    const named = element.getAttribute("name");
    const value = element.getAttribute("value");
    const candidates = [
      classes && tag + classes,
      named && `${tag}[name="${CSS.escape(named)}"]${value ? `[value="${CSS.escape(value)}"]` : ""}`,
      element.matches("[data-parallax-surface]") && "[data-parallax-surface]",
    ].filter(Boolean);
    for (const candidate of candidates) if (document.querySelectorAll(candidate).length === 1) return candidate;
    const parent = element.parentElement;
    if (!parent) return tag;
    const siblings = [...parent.children].filter((child) => child.tagName === element.tagName);
    return `${selector(parent)} > ${tag}:nth-of-type(${siblings.indexOf(element) + 1})`;
  };
  const label = (element) => (element.innerText || element.getAttribute("aria-label") || element.value || "").trim();
  const actions = [...document.querySelectorAll('button, a:not([href]), [role="button"]')]
    .filter(visible).map((element) => ({ selector: selector(element), label: label(element) }));
  const forms = [...document.forms].filter(visible).map((form) => ({
    selector: selector(form), label: label(form.querySelector('[type="submit"]') || form),
  }));
  const controls = [...document.querySelectorAll("input, select, textarea")].filter(visible)
    .map((element) => ({ selector: selector(element), label: label(element) }));
  const endpoints = [
    ...performance.getEntriesByType("resource").filter((entry) => ["fetch", "xmlhttprequest"].includes(entry.initiatorType)).map((entry) => entry.name),
    ...[...document.scripts].flatMap((script) => [...(script.textContent || "").matchAll(/fetch\(\s*["']([^"']+)/g)].map((match) => match[1])),
  ].filter((value) => {
    try { return new URL(value, location.href).origin === location.origin; } catch (_) { return false; }
  });
  return {
    links: [...document.querySelectorAll("a[href]")].filter(visible).map((anchor) => anchor.href),
    affordances: actions, forms, controls, endpoints: [...new Set(endpoints)], text: (document.body.innerText || "").trim().slice(0, 4000),
  };
}"""


@dataclass(frozen=True)
class ConductSummary:
    surfaces: list[Surface]
    testimonies: list[Testimony]
    findings: list[Finding]
    spec_paths: list[Path]
    feed_path: Path
    axis_applicability: list[AxisApplicability]
    proposal_report: ProposalReport
    # Declared and model-proposed scenarios are replayed by the same code, so the
    # count has to come from what was exercised rather than from what the caller
    # passed in. Reporting only the declared ones made a proposed scenario that
    # produced a finding look like a finding from a scenario that never ran.
    scenarios_exercised: int = 0
    scenarios_proposed_exercised: int = 0
    capabilities_exercised: int = 0
    capabilities_proposed_exercised: int = 0
    capability_roles_exercised: int = 0


@dataclass(frozen=True)
class RelationalScenario:
    """A caller-declared claim that requires two live, private sessions."""

    surface: Surface
    sender: Context
    receiver: Context
    action: Callable[[Any], Awaitable[None] | None]
    effect: Expectation
    deadline_ms: int
    # "propagation" asks how long until the receiver SEES the sender's action;
    # "revocation" asks how long until it STOPS seeing what was taken away. Same
    # two live sessions, opposite predicate, and the elapsed time is the result.
    kind: str = "propagation"
    distribution: Expectation | None = None
    enforcement: Expectation | None = None
    replay: RelationalReplay | None = None
    max_lag_ms: int | None = None


class Conductor:
    """The single owner of the run-level ordering and the shared mosaic wall."""

    def __init__(
        self,
        start_url: str,
        out_dir: str | Path,
        *,
        browser: Any,
        contexts: Sequence[Context] | None = None,
        specialists: Sequence[Specialist] | None = None,
        storage_states: Mapping[Privilege | str, StorageState] | None = None,
        max_surfaces: int = 12,
        settle_ms: int = 500,
        poll_ms: int = 50,
        relational_scenarios: Sequence[RelationalScenario] | None = None,
        capability_scenarios: Sequence[CapabilityScenario] | None = None,
        scenario_proposer: ScenarioProposer | None = None,
        proposal_validator: Callable[..., list[RelationalScenario]] | None = None,
        capability_validator: Callable[..., list[CapabilityScenario]] | None = None,
    ) -> None:
        if max_surfaces < 1:
            raise ValueError("max_surfaces must be at least 1")
        self.start_url = _normal_url(start_url)
        self.out_dir = Path(out_dir)
        self.browser = browser
        self.contexts = list(contexts or derive_witnesses())
        self.specialists = list(specialists or [])
        self.storage_states = storage_states
        self.max_surfaces = max_surfaces
        self.settle_ms = settle_ms
        self.poll_ms = max(1, poll_ms)
        self.relational_scenarios = list(relational_scenarios or [])
        self.capability_scenarios = list(capability_scenarios or [])
        self.scenario_proposer = scenario_proposer
        self.proposal_validator = proposal_validator
        self.capability_validator = capability_validator
        self._observed_routes: set[str] = set()
        self._observed_affordances: set[ObservedAffordance] = set()
        self._observed_endpoints: set[str] = set()
        self._observed_text: list[str] = []

    async def conduct(self) -> ConductSummary:
        """Run the complete pipeline. A witness error remains testimony, never a crash."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        _clean_managed_mosaics(self.out_dir)
        feed_path = self.out_dir / "feed.jsonl"
        feed_path.write_text("", encoding="utf-8")
        surfaces = await self._discover()
        proposal_report, proposed_scenarios, proposed_capabilities = self._proposed_scenarios()
        relational_scenarios = [*self.relational_scenarios, *proposed_scenarios]
        capability_scenarios = [*self.capability_scenarios, *proposed_capabilities]
        compositor = Compositor(
            [context.name for context in self.contexts],
            settle_ms=self.settle_ms,
            tile_size=_tile_size(self._baseline()),
        )
        sequence = {context.name: 0 for context in self.contexts}
        all_testimonies: list[Testimony] = []
        all_findings: list[Finding] = []
        published_finding_ids: set[str] = set()
        surface_mosaics: dict[str, MosaicFrame] = {}
        specialist_runs: list[tuple[Surface, list[Moment], list[Testimony]]] = []

        for surface in surfaces:
            self._write(feed_path, "status", {"surface": surface.describe(), "surface_id": surface.id, "state": "started"})
            compositor.set_action(surface.describe())
            testimonies, moments = await self._run_surface(surface, compositor, sequence)
            all_testimonies.extend(testimonies)
            for moment in moments:
                image = self._write_mosaic(surface, moment)
                self._write(feed_path, "mosaic", mosaic_payload(moment.mosaic, image, surface_id=surface.id))
            if moments:
                surface_mosaics[surface.id] = moments[-1].mosaic

            specialist_runs.append((surface, moments, testimonies))

        axis_applicability = assess_axis_applicability(all_testimonies, self.storage_states)
        for decision in axis_applicability:
            self._write(feed_path, "status", {
                "state": "axis_applicability",
                "axis": decision.axis.value,
                "applicable": decision.applicable,
                "reason": decision.reason,
            })
        exercised = {decision.axis for decision in axis_applicability if decision.applicable}
        findings = compare(_with_mirror_observations(_applicable_testimonies(all_testimonies, exercised)))
        for surface, moments, testimonies in specialist_runs:
            specialist_findings = self._judge_specialists(feed_path, surface, moments, testimonies)
            findings.extend(_applicable_findings(specialist_findings, exercised))
        findings = _unpublished_findings(findings, published_finding_ids)
        all_findings.extend(findings)
        for finding in findings:
            self._write(feed_path, "finding", finding_payload(finding, mosaic=surface_mosaics.get(finding.surface.id)))

        for scenario in relational_scenarios:
            self._write(feed_path, "status", {
                "surface": scenario.surface.describe(), "surface_id": scenario.surface.id, "state": "started",
            })
            testimonies, moments, observed_finding = await self._run_relational_scenario(scenario)
            all_testimonies.extend(testimonies)
            scenario_mosaic = None
            for moment in moments:
                image = self._write_mosaic(scenario.surface, moment)
                self._write(feed_path, "mosaic", mosaic_payload(moment.mosaic, image, surface_id=scenario.surface.id))
                scenario_mosaic = moment.mosaic

            findings = compare(testimonies)
            if observed_finding is not None:
                findings.append(observed_finding)
            findings.extend(self._judge_specialists(feed_path, scenario.surface, moments, testimonies))
            findings = _unpublished_findings(findings, published_finding_ids)
            all_findings.extend(findings)
            for finding in findings:
                self._write(feed_path, "finding", finding_payload(finding, mosaic=scenario_mosaic))

        for capability in capability_scenarios:
            self._write(feed_path, "status", {
                "surface": capability.surface.describe(),
                "surface_id": capability.surface.id,
                "state": "started",
            })
            runner = CapabilityRun(self.browser, storage_states=dict(self.storage_states or {}))
            # Sequential on purpose, unlike every other multi-session path here.
            # Each role performs the *same* declared action with the *same*
            # payload, so running them together would let one role's effect
            # satisfy another role's check and report a capability that the
            # second role never had. An audience scenario can be concurrent
            # because it has one actor and the rest only watch.
            attempts = [await runner.attempt(capability, role) for role in capability.roles]
            all_testimonies.extend(attempt.testimony for attempt in attempts)
            findings = _unpublished_findings(judge_capability(capability, attempts), published_finding_ids)
            all_findings.extend(findings)
            for finding in findings:
                self._write(feed_path, "finding", finding_payload(finding))

        spec_paths = emit_all(
            all_findings, self.out_dir / "specs",
            # Only the roles this run was actually given; a guessed path makes a
            # spec that cannot open its state and never reaches an assertion.
            {str(role): str(path) for role, path in (self.storage_states or {}).items()},
        )
        return ConductSummary(
            surfaces, all_testimonies, all_findings, spec_paths, feed_path, axis_applicability,
            proposal_report,
            scenarios_exercised=len(relational_scenarios),
            scenarios_proposed_exercised=len(proposed_scenarios),
            capabilities_exercised=len(capability_scenarios),
            capabilities_proposed_exercised=len(proposed_capabilities),
            capability_roles_exercised=sum(len(c.roles) for c in capability_scenarios),
        )

    async def _discover(self) -> list[Surface]:
        """Use only the baseline context to make the replay set causal and comparable.

        Routes form a breadth-first frontier.  They are deliberately selected before
        controls: a control is another observation of its page, while a route can
        reveal an entire new navigation layer (including links visible only to the
        baseline's signed-in state).  This makes a short crawl cover distinct pages
        before spending its remaining slots on siblings such as page-one buttons.
        """
        witness = Witness(self._baseline(), self.browser, storage_state=self._storage_for(self._baseline()))
        pending_routes = [self.start_url]
        queued_routes = {self.start_url}
        visited_routes: set[str] = set()
        pending_affordances: list[Surface] = []
        queued_affordances: set[tuple[str, str]] = set()
        surfaces: list[Surface] = []
        origin = _origin(self.start_url)
        try:
            await witness.open()
            assert witness.page is not None
            while len(surfaces) < self.max_surfaces:
                if pending_routes:
                    # FIFO preserves breadth-first order.  More importantly, every
                    # queued route outranks affordances from an already represented
                    # route, so shallow controls cannot starve deeper navigation.
                    route = pending_routes.pop(0)
                    queued_routes.remove(route)
                    if route in visited_routes:
                        continue
                    visited_routes.add(route)
                    self._observed_routes.add(route)
                    surfaces.append(Surface(SurfaceKind.ROUTE, route))
                elif pending_affordances:
                    surfaces.append(pending_affordances.pop(0))
                    continue
                else:
                    break
                try:
                    await witness.page.goto(route, wait_until="domcontentloaded", timeout=5_000)
                    data = await witness.page.evaluate(_DISCOVERY_SCRIPT)
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                self._record_baseline_observation(route, data)
                for action in data.get("affordances", []):
                    if not isinstance(action, dict) or not isinstance(action.get("selector"), str):
                        continue
                    affordance_key = (route, action["selector"])
                    if affordance_key in queued_affordances:
                        continue
                    surface = Surface(SurfaceKind.AFFORDANCE, route, action["selector"], action.get("label"))
                    queued_affordances.add(affordance_key)
                    pending_affordances.append(surface)
                for href in data.get("links", []):
                    if not isinstance(href, str):
                        continue
                    target = _normal_url(urljoin(route, href))
                    if (
                        _origin(target) == origin
                        and _is_at_or_below_start_path(target, self.start_url)
                        and target not in visited_routes
                        and target not in queued_routes
                    ):
                        self._observed_routes.add(target)
                        queued_routes.add(target)
                        pending_routes.append(target)
        finally:
            await witness.close()
        return surfaces

    def _proposed_scenarios(
        self,
    ) -> tuple[ProposalReport, list[RelationalScenario], list[CapabilityScenario]]:
        """Pass model proposals through the declared-scenario validator one at a time."""
        proposer = self.scenario_proposer
        if proposer is None:
            return ProposalReport.disabled(), [], []
        try:
            batch = proposer.propose(self._baseline_observation())
        except Exception as error:
            message = f"{type(error).__name__}: {str(error)[:200]}"
            return ProposalReport(
                True, 0, 0, calls_attempted=getattr(proposer, "calls_attempted", 0),
                calls_succeeded=getattr(proposer, "calls_succeeded", 0), route=getattr(proposer, "route", "unknown"),
                last_error=message, note="scenario proposer failed before it returned a proposal",
            ), [], []

        rejections = list(batch.rejections)
        scenarios: list[RelationalScenario] = []
        capabilities: list[CapabilityScenario] = []
        for candidate in batch.candidates:
            # A proposal is validated by exactly the validator its declared
            # counterpart uses. The model gets no shorter path into execution
            # than a human writing the same JSON by hand.
            validator = (
                self.capability_validator if candidate.kind == "capability" else self.proposal_validator
            )
            if validator is None:
                rejections.append(ProposalRejection(candidate.index, "proposal validator was not configured"))
                continue
            try:
                produced = validator([candidate.data], self.start_url, source=f"proposal {candidate.index}")
            except SystemExit as error:
                rejections.append(ProposalRejection(candidate.index, str(error)))
                continue
            (capabilities if candidate.kind == "capability" else scenarios).extend(produced)
        note = batch.note
        if batch.proposed == 0 and note is None:
            note = "Gemini proposed no scenarios"
        return ProposalReport(
            True, batch.proposed, len(scenarios) + len(capabilities), tuple(rejections),
            getattr(proposer, "calls_attempted", 0), getattr(proposer, "calls_succeeded", 0),
            getattr(proposer, "route", "unknown"), getattr(proposer, "last_error", None), note,
        ), scenarios, capabilities

    def _baseline_observation(self) -> BaselineObservation:
        """Keep the model's input to what this baseline actually encountered."""
        roles = {context.privilege.value for context in self.contexts if context.privilege is Privilege.ANON}
        for privilege in Privilege:
            if self._storage_for(Context(privilege=privilege)) is not None:
                roles.add(privilege.value)
        return BaselineObservation(
            self.start_url,
            tuple(sorted(self._observed_routes)),
            tuple(sorted(self._observed_affordances, key=lambda item: (item.route, item.kind, item.selector))),
            tuple(sorted(self._observed_endpoints)),
            tuple(sorted(roles)),
            "\n".join(dict.fromkeys(self._observed_text))[:4_000],
        )

    def _record_baseline_observation(self, route: str, data: dict[str, Any]) -> None:
        """Preserve baseline controls for proposal input without changing discovery order."""
        for field, kind in (("affordances", "affordance"), ("forms", "form"), ("controls", "control")):
            items = data.get(field, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict) or not isinstance(selector := item.get("selector"), str) or not selector:
                    continue
                label = item.get("label")
                self._observed_affordances.add(ObservedAffordance(route, selector, label if isinstance(label, str) else "", kind))
        endpoints = data.get("endpoints", [])
        if not isinstance(endpoints, list):
            endpoints = []
        for endpoint in endpoints:
            if not isinstance(endpoint, str):
                continue
            target = _normal_url(urljoin(route, endpoint))
            if _origin(target) == _origin(self.start_url) and _is_at_or_below_start_path(target, self.start_url):
                self._observed_endpoints.add(target)
        if isinstance(text := data.get("text"), str) and text.strip():
            self._observed_text.append(text.strip())

    async def _run_surface(
        self, surface: Surface, compositor: Compositor, sequence: dict[str, int]
    ) -> tuple[list[Testimony], list[Moment]]:
        async def run(context: Context) -> Testimony:
            witness = Witness(context, self.browser, storage_state=self._storage_for(context))

            async def consume(jpeg: bytes, _metadata: dict[str, Any]) -> None:
                sequence[context.name] += 1
                try:
                    compositor.submit(Frame(context.name, jpeg, sequence[context.name]))
                except ValueError:
                    # A malformed visual frame is not enough to invalidate the witness's DOM evidence.
                    pass

            try:
                try:
                    await witness.start_screencast(consume)
                except Exception:
                    pass
                testimony = await witness.visit(surface)
                await self._record_visible_offers(testimony, witness)
                return testimony
            except Exception as error:
                return Testimony(surface, context, Outcome.ERROR, note=f"conductor failed: {type(error).__name__}: {error}")
            finally:
                try:
                    await witness.stop_screencast()
                finally:
                    await witness.close()

        # Moments have to be harvested WHILE the witnesses work. Letting them all
        # finish and ticking once would reduce a live wall to a single end-state
        # snapshot per surface and discard every instant in between — and those
        # instants are the only thing the specialists are there to look at.
        moments: list[Moment] = []
        collecting = True

        async def collect() -> None:
            while collecting:
                settled = compositor.tick(_now_ms())
                if settled is not None:
                    moments.append(replace(settled, surface=surface))
                await asyncio.sleep(self.poll_ms / 1000)

        collector = asyncio.create_task(collect())
        try:
            testimonies = list(await asyncio.gather(*(run(context) for context in self.contexts)))
        finally:
            collecting = False
            collector.cancel()
            await asyncio.gather(collector, return_exceptions=True)

        # One last look, dated past the settle window, for a tile that moved and
        # never got the chance to hold still before its witness closed. ``tick``
        # also enforces a fully painted wall, so this flush cannot publish a
        # half-painted mosaic after one witness ends without a screencast frame.
        final = compositor.tick(_now_ms() + self.settle_ms)
        if final is not None:
            moments.append(replace(final, surface=surface))
        return testimonies, moments

    async def _run_relational_scenario(
        self, scenario: RelationalScenario
    ) -> tuple[list[Testimony], list[Moment], Finding | None]:
        """Observe a declared cross-session effect without borrowing ordinary witnesses.

        This is intentionally a two-tile compositor: the sender and receiver are
        the whole claim, and both tiles must be live while the action runs.
        """
        pair = RelationalPair(
            scenario.sender, scenario.receiver, self.browser,
            sender_storage_state=self._storage_for(scenario.sender),
            receiver_storage_state=self._storage_for(scenario.receiver),
            poll_interval_ms=self.poll_ms,
        )
        contexts = (pair.sender.context, pair.receiver.context)
        compositor = Compositor(
            [context.name for context in contexts], settle_ms=self.settle_ms, tile_size=_tile_size(self._baseline())
        )
        compositor.set_action(scenario.surface.describe())
        sequence = {context.name: 0 for context in contexts}

        def consumer(context: Context) -> Callable[[bytes, dict[str, Any]], Awaitable[None]]:
            async def consume(jpeg: bytes, _metadata: dict[str, Any]) -> None:
                sequence[context.name] += 1
                try:
                    compositor.submit(Frame(context.name, jpeg, sequence[context.name]))
                except ValueError:
                    pass
            return consume

        moments: list[Moment] = []
        collecting = True

        async def collect() -> None:
            while collecting:
                settled = compositor.tick(_now_ms())
                if settled is not None:
                    moments.append(replace(settled, surface=scenario.surface))
                await asyncio.sleep(self.poll_ms / 1000)

        try:
            await pair.open()
            for witness in (pair.sender, pair.receiver):
                try:
                    await witness.start_screencast(consumer(witness.context))
                except Exception:
                    pass
            collector = asyncio.create_task(collect())
            try:
                if scenario.kind == "revocation":
                    observed = await pair.measure_revocation_lag(
                        scenario.action, scenario.effect, scenario.deadline_ms,
                        max_lag_ms=scenario.max_lag_ms or 0,
                        surface=scenario.surface,
                        distribution=scenario.distribution,
                        enforcement=scenario.enforcement,
                    )
                else:
                    observed = await pair.observe(
                        scenario.action, scenario.effect, scenario.deadline_ms, surface=scenario.surface
                    )
            finally:
                collecting = False
                collector.cancel()
                await asyncio.gather(collector, return_exceptions=True)
        except Exception as error:
            testimonies = [
                Testimony(scenario.surface, context, Outcome.ERROR, note=f"relational scenario failed: {type(error).__name__}: {error}")
                for context in contexts
            ]
            return testimonies, moments, None
        finally:
            await asyncio.gather(pair.sender.stop_screencast(), pair.receiver.stop_screencast(), return_exceptions=True)
            await pair.close()

        final = compositor.tick(_now_ms() + self.settle_ms)
        if final is not None:
            moments.append(replace(final, surface=scenario.surface))
        if isinstance(observed, Finding):
            observed.replay = scenario.replay
            return observed.testimonies, moments, observed
        return observed, moments, None

    def _baseline(self) -> Context:
        return next((context for context in self.contexts if context.varies is Axis.BASELINE), self.contexts[0])

    def _storage_for(self, context: Context) -> StorageState:
        if self.storage_states is None:
            return None
        return self.storage_states.get(context.privilege, self.storage_states.get(context.privilege.value))

    async def _record_visible_offers(self, testimony: Testimony, witness: Witness) -> None:
        """Attach this witness's own same-origin navigation offer to its testimony.

        Discovery stays baseline-driven: it alone chooses the bounded crawl.
        These per-witness observations merely preserve what each rendered page
        offered, so the differ can distinguish a public page from a removed
        privilege check.  A blocked-witness rule alone misses that worst case
        because complete exposure leaves no witness blocked.
        """
        offers: set[Surface] = set()
        page = witness.page
        if testimony.is_evidence and page is not None:
            try:
                data = await page.evaluate(_DISCOVERY_SCRIPT)
                page_url = _normal_url(str(getattr(page, "url", testimony.surface.path)))
                if isinstance(data, dict):
                    for href in data.get("links", []):
                        if not isinstance(href, str):
                            continue
                        target = _normal_url(urljoin(page_url, href))
                        if _origin(target) == _origin(self.start_url):
                            offers.add(Surface(SurfaceKind.ROUTE, target))
                    for action in data.get("affordances", []):
                        if isinstance(action, dict) and isinstance(action.get("selector"), str):
                            offers.add(Surface(SurfaceKind.AFFORDANCE, page_url, action["selector"], action.get("label")))
            except Exception:
                # Failure to observe navigation is silence, never evidence that
                # the page hid it; the differ will still use denial evidence.
                pass
        testimony.offered_surfaces = offers  # type: ignore[attr-defined]

    def _write_mosaic(self, surface: Surface, moment: Moment) -> str:
        relative = Path("mosaics") / f"{surface.id}-{moment.mosaic.seq}.jpg"
        path = self.out_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(moment.mosaic.jpeg)
        return relative.as_posix()

    def _judge_specialists(
        self, feed_path: Path, surface: Surface, moments: Sequence[Moment], testimonies: Sequence[Testimony]
    ) -> list[Finding]:
        """Run each lens against a private snapshot so it cannot poison another."""
        findings: list[Finding] = []
        for specialist in self.specialists:
            try:
                findings.extend(specialist.judge(deepcopy(moments), deepcopy(testimonies)))
            except Exception as error:
                # Lens errors are run diagnostics, not witness evidence. Keep
                # them in the feed without allowing one optional lens to end
                # the sweep or hide the remaining lenses' findings.
                self._write(feed_path, "status", {
                    "surface": surface.describe(),
                    "surface_id": surface.id,
                    "state": "error",
                    "specialist": specialist.name,
                    "error": f"{type(error).__name__}: {error}",
                })
        return findings

    @staticmethod
    def _write(path: Path, kind: str, payload: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as feed:
            feed.write(json.dumps(FeedEvent(kind, payload).to_json(), separators=(",", ":")) + "\n")


def assess_axis_applicability(
    testimonies: Sequence[Testimony], storage_states: Mapping[Privilege | str, StorageState] | None
) -> list[AxisApplicability]:
    """Accept only page claims and supplied sessions as grounds for a comparison."""
    support = {
        key
        for testimony in testimonies
        if testimony.is_evidence
        for key, present in testimony.support.items()
        if present
    }
    baseline = next((testimony for testimony in testimonies if testimony.context.varies is Axis.BASELINE), None)
    locale_langs = {
        testimony.document_lang.lower()
        for testimony in testimonies
        if testimony.is_evidence
        and testimony.context.varies is Axis.LOCALE
        and isinstance(testimony.document_lang, str)
        and testimony.document_lang
    }
    lang_changed = (
        baseline is not None
        and isinstance(baseline.document_lang, str)
        and bool(locale_langs)
        and baseline.document_lang.lower() not in locale_langs
    )
    # Non-Latin text is not a locale mechanism, and treating it as one made
    # every monolingual Arabic page fail the mirror test. arbchat.org serves
    # dir="rtl" whether asked for lang=ar or lang=en, so the "variant" was the
    # baseline; Parallax compared a page to itself and reported that it was not
    # mirrored, once per surface. An axis is applicable when the application
    # offers the variation, not when the content happens to look foreign.
    locale_reason = _support_reason(
        support,
        (
            ("localeAlternate", "page declares localized alternatives"),
            ("languageSwitcher", "page exposes a language switcher"),
        ),
        "no localized alternate, language switcher, or changed lang attribute observed",
    )
    if lang_changed:
        locale_reason = "page lang attribute changes between contexts"
    theme_reason = _support_reason(
        support,
        (
            ("themeMedia", "stylesheets use prefers-color-scheme"),
            ("themeToggle", "page exposes a theme toggle"),
        ),
        "no prefers-color-scheme media query or theme toggle observed",
    )
    viewport_reason = _support_reason(
        support,
        (
            ("viewportMeta", "page declares a viewport meta tag"),
            ("viewportMedia", "stylesheets use viewport media queries"),
        ),
        "no viewport meta tag or media query observed",
    )
    privilege_reason = _privilege_reason(storage_states)
    return [
        AxisApplicability(
            Axis.PRIVILEGE,
            privilege_reason is not None,
            privilege_reason or "no distinct role storage states were supplied",
        ),
        AxisApplicability(
            Axis.LOCALE,
            bool(support & {"localeAlternate", "languageSwitcher"}) or lang_changed,
            locale_reason,
        ),
        AxisApplicability(Axis.THEME, bool(support & {"themeMedia", "themeToggle"}), theme_reason),
        AxisApplicability(Axis.VIEWPORT, bool(support & {"viewportMeta", "viewportMedia"}), viewport_reason),
    ]


def _support_reason(support: set[str], options: tuple[tuple[str, str], ...], absent: str) -> str:
    return next((reason for key, reason in options if key in support), absent)


def _privilege_reason(storage_states: Mapping[Privilege | str, StorageState] | None) -> str | None:
    if storage_states is None:
        return None
    supplied = [
        state for privilege in Privilege
        if (state := storage_states.get(privilege, storage_states.get(privilege.value))) is not None
    ]
    distinct = {key for state in supplied if (key := _storage_state_key(state)) is not None}
    return "distinct role storage states were supplied" if len(distinct) >= 2 else None


def _storage_state_key(state: StorageState) -> str | None:
    if isinstance(state, (Path, str)):
        path = Path(state)
        try:
            if path.is_symlink() or not path.is_file():
                return None
            return f"content:{hashlib.sha256(path.read_bytes()).hexdigest()}"
        except OSError:
            return None
    try:
        return json.dumps(state, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return repr(state)


def _applicable_testimonies(testimonies: Sequence[Testimony], exercised: set[Axis]) -> list[Testimony]:
    return [
        testimony for testimony in testimonies
        if testimony.context.varies in exercised | {Axis.BASELINE, Axis.RELATIONAL}
    ]


_MANAGED_MOSAIC = re.compile(r"[0-9a-f]{16}-\d+\.jpg")


def _clean_managed_mosaics(out_dir: Path) -> None:
    """Remove only mosaics named by Parallax so reruns cannot publish stale frames."""
    mosaic_dir = out_dir / "mosaics"
    if not mosaic_dir.exists():
        return
    if mosaic_dir.is_symlink():
        raise RuntimeError(f"refusing symlinked mosaic directory: {mosaic_dir}")
    for candidate in mosaic_dir.iterdir():
        if _MANAGED_MOSAIC.fullmatch(candidate.name) and (candidate.is_file() or candidate.is_symlink()):
            candidate.unlink()


def _applicable_findings(findings: Sequence[Finding], exercised: set[Axis]) -> list[Finding]:
    return [
        finding for finding in findings
        if finding.axis in exercised | {Axis.BASELINE, Axis.RELATIONAL}
    ]


_TILE_WIDTH = 480


def _tile_size(baseline: Context) -> tuple[int, int]:
    """The baseline's proportions, but not its pixels.

    A wall of full 1440x900 tiles is 5760x1800 — re-encoded every time anyone
    looks at it and shipped to a model on every moment, for detail nobody can
    resolve at tile scale.
    """
    scale = _TILE_WIDTH / baseline.viewport.width
    return _TILE_WIDTH, max(1, round(baseline.viewport.height * scale))


def _now_ms() -> int:
    """The same clock domain the compositor keeps its settle windows in."""
    return int(time.time() * 1000)


def _normal_url(url: str) -> str:
    """Return one stable key per navigable route before it enters the crawl.

    Browsers commonly expose both a directory URL and its trailing-slash form,
    and link builders can emit the same query parameters in different orders.
    Treating either as a new route would consume a bounded discovery slot twice.
    """
    clean, _ = urldefrag(url)
    parts = urlsplit(clean)
    path = parts.path.rstrip("/") or "/"
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))


def _origin(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    return parts.scheme, parts.netloc


def _is_at_or_below_start_path(target: str, start_url: str) -> bool:
    """Keep discovery in the start path's directory, whether or not it ends in '/'."""
    start_path = urlsplit(start_url).path or "/"
    directory = start_path if start_path.endswith("/") else f"{start_path}/"
    target_path = urlsplit(target).path or "/"
    return target_path == start_path.rstrip("/") or target_path.startswith(directory)


def _with_mirror_observations(testimonies: Sequence[Testimony]) -> list[Testimony]:
    """Give the differ derived mirror observations without rewriting evidence."""
    observations = []
    for testimony in testimonies:
        observation = replace(
            testimony,
            defects=list(testimony.defects),
            observations=list(testimony.observations),
        )
        # Offers are run-local evidence attached by _record_visible_offers.
        # ``replace`` copies declared dataclass fields only, so preserve them
        # explicitly before the differ consumes this derived observation.
        observation.offered_surfaces = set(getattr(testimony, "offered_surfaces", set()))  # type: ignore[attr-defined]
        observations.append(observation)
    baselines = {
        item.surface.id: item
        for item in testimonies
        if item.context.varies is Axis.BASELINE
    }
    for index, variant in enumerate(testimonies):
        baseline = baselines.get(variant.surface.id)
        if baseline is None:
            continue
        for defect in mirror_defects(baseline, variant):
            if defect not in observations[index].defects:
                observations[index].defects.append(defect)
            for offender in mirror_report(baseline, variant):
                selector = offender.selector
                if selector.startswith("<") or "[text=" in selector:
                    continue
                observations[index].observations.append(DefectObservation(
                    defect=defect,
                    selector=selector,
                    detail=json.dumps({
                        "expected": offender.expected,
                        "actual": offender.actual,
                        "tolerance": 3,
                    }, separators=(",", ":")),
                ))
    return observations


def _unpublished_findings(findings: Sequence[Finding], published_ids: set[str]) -> list[Finding]:
    """One deterministic finding identity may be corroborated by many lenses."""
    unique: list[Finding] = []
    seen: set[str] = set()
    for finding in findings:
        if finding.id not in seen and finding.id not in published_ids:
            seen.add(finding.id)
            unique.append(finding)
    published_ids.update(seen)
    return unique
