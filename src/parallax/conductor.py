"""Coordinate discovery, simultaneous witnessing, judgement, and publication."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit

from .compositor import Compositor
from .contracts import FeedEvent, Frame, Moment, Specialist, finding_payload, mosaic_payload
from .differ import compare
from .emitter import emit_all
from .mirror import mirror_defects
from .types import Axis, Context, Finding, Outcome, Privilege, Surface, SurfaceKind, Testimony, derive_witnesses
from .witness import StorageState, Witness


_DISCOVERY_SCRIPT = r"""/* PARALLAX_DISCOVERY */
() => {
  const visible = (element) => {
    const style = getComputedStyle(element); const box = element.getBoundingClientRect();
    return style.visibility !== "hidden" && style.display !== "none" && box.width > 0 && box.height > 0;
  };
  const selector = (element, index) => {
    if (element.id) return "#" + CSS.escape(element.id);
    const tagged = "[data-parallax-surface]";
    if (element.matches(tagged)) return tagged + `:nth-of-type(${index + 1})`;
    return `${element.tagName.toLowerCase()}:nth-of-type(${index + 1})`;
  };
  const actions = [...document.querySelectorAll('button, a:not([href]), [role="button"]')]
    .filter(visible).map((element, index) => ({ selector: selector(element, index), label: (element.innerText || element.getAttribute("aria-label") || "").trim() }));
  return { links: [...document.querySelectorAll("a[href]")].filter(visible).map((anchor) => anchor.href), affordances: actions };
}"""


@dataclass(frozen=True)
class ConductSummary:
    surfaces: list[Surface]
    testimonies: list[Testimony]
    findings: list[Finding]
    spec_paths: list[Path]
    feed_path: Path


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

    async def conduct(self) -> ConductSummary:
        """Run the complete pipeline. A witness error remains testimony, never a crash."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        feed_path = self.out_dir / "feed.jsonl"
        feed_path.write_text("", encoding="utf-8")
        surfaces = await self._discover()
        compositor = Compositor(
            [context.name for context in self.contexts],
            settle_ms=self.settle_ms,
            tile_size=_tile_size(self._baseline()),
        )
        sequence = {context.name: 0 for context in self.contexts}
        all_testimonies: list[Testimony] = []
        all_findings: list[Finding] = []

        for surface in surfaces:
            self._write(feed_path, "status", {"surface": surface.describe(), "surface_id": surface.id, "state": "started"})
            compositor.set_action(surface.describe())
            testimonies, moments = await self._run_surface(surface, compositor, sequence)
            all_testimonies.extend(testimonies)
            for moment in moments:
                image = self._write_mosaic(surface, moment)
                self._write(feed_path, "mosaic", mosaic_payload(moment.mosaic, image))

            baseline = next((item for item in testimonies if item.context.varies is Axis.BASELINE), None)
            if baseline is not None:
                for variant in testimonies:
                    for defect in mirror_defects(baseline, variant):
                        if defect not in variant.defects:
                            variant.defects.append(defect)
            findings = compare(testimonies)
            for specialist in self.specialists:
                findings.extend(specialist.judge(moments, testimonies))
            all_findings.extend(findings)
            for finding in findings:
                self._write(feed_path, "finding", finding_payload(finding))

        spec_paths = emit_all(all_findings, self.out_dir / "specs")
        return ConductSummary(surfaces, all_testimonies, all_findings, spec_paths, feed_path)

    async def _discover(self) -> list[Surface]:
        """Use only the baseline context to make the replay set causal and comparable."""
        witness = Witness(self._baseline(), self.browser, storage_state=self._storage_for(self._baseline()))
        pending = [self.start_url]
        visited: set[str] = set()
        surfaces: list[Surface] = []
        origin = _origin(self.start_url)
        try:
            await witness.open()
            assert witness.page is not None
            while pending and len(surfaces) < self.max_surfaces:
                route = pending.pop(0)
                if route in visited:
                    continue
                visited.add(route)
                surfaces.append(Surface(SurfaceKind.ROUTE, route))
                try:
                    await witness.page.goto(route, wait_until="domcontentloaded", timeout=5_000)
                    data = await witness.page.evaluate(_DISCOVERY_SCRIPT)
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                for action in data.get("affordances", []):
                    if len(surfaces) >= self.max_surfaces:
                        break
                    if not isinstance(action, dict) or not isinstance(action.get("selector"), str):
                        continue
                    surface = Surface(SurfaceKind.AFFORDANCE, route, action["selector"], action.get("label"))
                    if surface not in surfaces:
                        surfaces.append(surface)
                for href in data.get("links", []):
                    if not isinstance(href, str):
                        continue
                    target = _normal_url(urljoin(route, href))
                    if (
                        _origin(target) == origin
                        and _is_at_or_below_start_path(target, self.start_url)
                        and target not in visited
                        and target not in pending
                    ):
                        pending.append(target)
        finally:
            await witness.close()
        return surfaces

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
                return await witness.visit(surface)
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
        # never got the chance to hold still before its witness closed.
        final = compositor.tick(_now_ms() + self.settle_ms)
        if final is not None:
            moments.append(replace(final, surface=surface))
        return testimonies, moments

    def _baseline(self) -> Context:
        return next((context for context in self.contexts if context.varies is Axis.BASELINE), self.contexts[0])

    def _storage_for(self, context: Context) -> StorageState:
        if self.storage_states is None:
            return None
        return self.storage_states.get(context.privilege, self.storage_states.get(context.privilege.value))

    def _write_mosaic(self, surface: Surface, moment: Moment) -> str:
        relative = Path("mosaics") / f"{surface.id}-{moment.mosaic.seq}.jpg"
        path = self.out_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(moment.mosaic.jpeg)
        return relative.as_posix()

    @staticmethod
    def _write(path: Path, kind: str, payload: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as feed:
            feed.write(json.dumps(FeedEvent(kind, payload).to_json(), separators=(",", ":")) + "\n")


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
    clean, _ = urldefrag(url)
    parts = urlsplit(clean)
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))


def _origin(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    return parts.scheme, parts.netloc


def _is_at_or_below_start_path(target: str, start_url: str) -> bool:
    """Keep discovery in the start path's directory, whether or not it ends in '/'."""
    start_path = urlsplit(start_url).path or "/"
    directory = start_path if start_path.endswith("/") else f"{start_path}/"
    target_path = urlsplit(target).path or "/"
    return target_path == start_path.rstrip("/") or target_path.startswith(directory)
