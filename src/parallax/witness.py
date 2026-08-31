"""Browser witnesses: isolated contexts that turn a surface visit into testimony."""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .media import INSTRUMENT_MEDIA
from .types import (
    Axis,
    Context,
    Defect,
    DefectObservation,
    Outcome,
    Privilege,
    Surface,
    SurfaceKind,
    Testimony,
    derive_witnesses,
)


FrameConsumer = Callable[[bytes, dict[str, Any]], Awaitable[None] | None]
BrowserFactory = Callable[[], Awaitable[Any] | Any]
StorageState = dict[str, Any] | str | Path | None


def contextual_url(url: str, context: Context) -> str:
    """Replay the URL exactly as the varied locale or theme witness saw it."""
    if context.varies is Axis.LOCALE:
        keys = {"lang", "locale"}
        value = context.locale.value
    elif context.varies is Axis.THEME:
        keys = {"theme", "color-scheme"}
        value = context.theme.value
    else:
        return url

    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    if not any(key in keys for key, _ in query):
        return url
    contextual_query = [
        (key, value if key in keys else current)
        for key, current in query
    ]
    return urlunsplit(parts._replace(query=urlencode(contextual_query)))


class Witness:
    """A single isolated browser context; the caller retains ownership of the browser."""

    LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]

    def __init__(
        self,
        context: Context,
        browser: Any,
        *,
        storage_state: StorageState = None,
        probe_source: str | None = None,
    ) -> None:
        self.context = context
        self.browser = browser
        self.storage_state = storage_state
        self.browser_context: Any | None = None
        self.page: Any | None = None
        self.last_probe: dict[str, Any] | None = None
        self._probe_source = probe_source
        self._cdp_session: Any | None = None
        self._screencast_handler: Callable[[dict[str, Any]], None] | None = None
        self._screencast_tasks: set[asyncio.Task[None]] = set()
        self._streaming = False
        self.screencast_ack_count = 0

    @classmethod
    async def create(cls, context: Context, browser: Any, **kwargs: Any) -> "Witness":
        witness = cls(context, browser, **kwargs)
        await witness.open()
        return witness

    async def open(self) -> None:
        """Create this witness's private context exactly once."""
        if self.browser_context is not None:
            return

        self.browser_context = await self.browser.new_context(
            viewport={"width": self.context.viewport.width, "height": self.context.viewport.height},
            locale=self.context.locale.value,
            color_scheme=self.context.theme.value,
            extra_http_headers={"Accept-Language": self.context.locale.value},
            storage_state=self.storage_state,
        )
        # Before any application script: a page's peer connections are otherwise
        # unreachable, and a call cannot be measured from outside the objects
        # that carry it. This records them and changes nothing.
        try:
            await self.browser_context.add_init_script(INSTRUMENT_MEDIA)
        except Exception:
            pass
        self.page = await self.browser_context.new_page()

    async def visit(self, surface: Surface) -> Testimony:
        """Visit one surface and record failures as evidence instead of raising them."""
        try:
            await self.open()
            assert self.page is not None
            target = contextual_url(surface.path, self.context)
            response = await self.page.goto(target, wait_until="domcontentloaded", timeout=5_000)
            await self._wait_for_load()
            await self.reveal_lazy_content()
        except Exception as error:
            return self._error_testimony(surface, "navigation", error)

        return await self.measure(surface, status=getattr(response, "status", None) if response is not None else None)

    # Enough to walk a long page, bounded so an infinite-scroll feed cannot hold
    # a sweep open forever. Twelve viewports is far past any fold.
    _LAZY_SCROLL_STEPS = 12
    _LAZY_SETTLE_MS = 120

    _REVEAL_LAZY_CONTENT = """
    async ({ steps, settle }) => {
      const pause = (ms) => new Promise((done) => setTimeout(done, ms));
      const start = window.scrollY;
      let previous = -1;
      for (let step = 0; step < steps; step += 1) {
        const height = document.documentElement.scrollHeight;
        const target = Math.min(height, (step + 1) * window.innerHeight);
        if (target <= previous) break;
        previous = target;
        window.scrollTo(0, target);
        await pause(settle);
        if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 1
            && height === document.documentElement.scrollHeight) break;
      }
      window.scrollTo(0, start);
      await pause(settle);
      return document.documentElement.scrollHeight;
    }
    """

    async def reveal_lazy_content(self) -> None:
        """Scroll the page once so deferred content exists before it is measured.

        The probe already walks the whole DOM, so static content far below the
        fold is measured without this. Content that does not exist until an
        IntersectionObserver fires is a different matter: it is simply absent,
        and a sweep that never scrolls reports a clean page because it never
        loaded the half that was broken. Scrolling has no side effects, unlike
        every other way of making an application reveal itself.
        """
        if self.page is None:
            return
        try:
            await self.page.evaluate(
                self._REVEAL_LAZY_CONTENT,
                {"steps": self._LAZY_SCROLL_STEPS, "settle": self._LAZY_SETTLE_MS},
            )
        except Exception:
            # A page that refuses to scroll is still worth measuring as it is.
            return

    async def measure(self, surface: Surface, *, status: int | None = None) -> Testimony:
        """Measure whatever the page currently shows, however it got there.

        `visit` navigates and then calls this. A capability check calls it again
        after an action, because the state a click produces — the dialog, the
        drawer, the confirmation — is never on a freshly loaded page and is
        therefore invisible to every check that only measures page load.
        """
        assert self.page is not None
        try:
            probe = await self.page.evaluate(self._load_probe())
        except Exception as error:
            return self._error_testimony(surface, "probe", error)

        self.last_probe = probe if isinstance(probe, dict) else {}
        final_path = self._path_of(str(getattr(self.page, "url", surface.path)))
        observations = self._map_defects(self.last_probe.get("defects"))
        defects = list(dict.fromkeys(observation.defect for observation in observations))
        blocked = self._is_denied(status, surface.path, final_path)
        affordance_missing = False
        if not blocked and surface.kind is SurfaceKind.AFFORDANCE and surface.selector:
            try:
                affordance_missing = not await self._affordance_is_visible(surface.selector)
                blocked = affordance_missing
            except Exception as error:
                return self._error_testimony(surface, "affordance", error)

        # Preserve a 5xx as a degradation diagnostic without letting it answer an
        # access question: no role reached a server error page.
        server_error = status is not None and 500 <= status < 600
        outcome = Outcome.BLOCKED if blocked else Outcome.PARTIAL if server_error or defects else Outcome.REACHED
        note = self._note_for(
            outcome, status, final_path, defects,
            affordance=surface.selector if affordance_missing else None,
        )
        return Testimony(
            surface=surface,
            context=self.context,
            outcome=outcome,
            http_status=status,
            final_path=final_path,
            content_signature=self.last_probe.get("contentSignature"),
            # Raw material for the mirror test and the theme invariant. A single
            # witness cannot judge either — only the comparison across two can.
            layout_signature=self.last_probe.get("layoutSignature"),
            geometry=list(self.last_probe.get("geometry") or []),
            document_lang=self._document_lang(self.last_probe),
            support=self._support(self.last_probe),
            defects=defects,
            observations=observations,
            note=note,
        )

    async def start_screencast(self, consumer: FrameConsumer) -> None:
        """Deliver JPEG frames asynchronously so a slow consumer cannot block CDP events."""
        await self.open()
        assert self.browser_context is not None and self.page is not None
        if self._streaming:
            raise RuntimeError("screencast is already running")

        session = await self.browser_context.new_cdp_session(self.page)

        def on_frame(event: dict[str, Any]) -> None:
            if not self._streaming:
                return
            task = asyncio.create_task(self._deliver_frame(session, event, consumer))
            self._screencast_tasks.add(task)
            task.add_done_callback(self._screencast_tasks.discard)

        self._cdp_session = session
        self._screencast_handler = on_frame
        self._streaming = True
        session.on("Page.screencastFrame", on_frame)
        try:
            await session.send("Page.startScreencast", {"format": "jpeg", "quality": 60})
        except Exception:
            self._streaming = False
            self._remove_listener(session, on_frame)
            self._cdp_session = None
            self._screencast_handler = None
            raise

    async def stop_screencast(self) -> None:
        """Detach the stream and cancel pending delivery without closing the shared browser."""
        session, handler = self._cdp_session, self._screencast_handler
        self._streaming = False
        self._cdp_session = None
        self._screencast_handler = None
        if session is None:
            return
        self._remove_listener(session, handler)
        try:
            await session.send("Page.stopScreencast")
        except Exception:
            pass
        for task in tuple(self._screencast_tasks):
            task.cancel()
        if self._screencast_tasks:
            await asyncio.gather(*tuple(self._screencast_tasks), return_exceptions=True)
        self._screencast_tasks.clear()
        detach = getattr(session, "detach", None)
        if detach is not None:
            try:
                await detach()
            except Exception:
                pass

    async def close(self) -> None:
        await self.stop_screencast()
        if self.browser_context is not None:
            await self.browser_context.close()
            self.browser_context = None
            self.page = None

    async def _wait_for_load(self) -> None:
        wait = getattr(self.page, "wait_for_load_state", None)
        if wait is not None:
            await wait("networkidle", timeout=5_000)

    async def _affordance_is_visible(self, selector: str) -> bool:
        return bool(await self.page.locator(selector).is_visible())

    async def _deliver_frame(self, session: Any, event: dict[str, Any], consumer: FrameConsumer) -> None:
        try:
            payload = base64.b64decode(event["data"])
            result = consumer(payload, dict(event.get("metadata", {})))
            if inspect.isawaitable(result):
                await result
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            try:
                await session.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})
                self.screencast_ack_count += 1
            except Exception:
                pass

    def _load_probe(self) -> str:
        return self._probe_source or Path(__file__).with_name("probe.js").read_text(encoding="utf-8")

    def _error_testimony(self, surface: Surface, stage: str, error: Exception) -> Testimony:
        return Testimony(
            surface=surface,
            context=self.context,
            outcome=Outcome.ERROR,
            note=f"{stage} failed: {self._short_error(error)}",
        )

    @staticmethod
    def _map_defects(raw_defects: object) -> list[DefectObservation]:
        if not isinstance(raw_defects, list):
            return []
        observations: list[DefectObservation] = []
        for raw in raw_defects:
            try:
                defect = Defect(raw["type"]) if isinstance(raw, dict) else Defect(raw)
            except (KeyError, TypeError, ValueError):
                continue
            selector = raw.get("selector") if isinstance(raw, dict) else None
            detail = raw.get("detail", "") if isinstance(raw, dict) else ""
            observations.append(DefectObservation(
                defect,
                selector if isinstance(selector, str) else None,
                detail if isinstance(detail, str) else json.dumps(detail, sort_keys=True, separators=(",", ":")),
            ))
        return observations

    @staticmethod
    def _document_lang(probe: dict[str, Any]) -> str | None:
        view = probe.get("view")
        lang = view.get("lang") if isinstance(view, dict) else None
        return lang if isinstance(lang, str) and lang else None

    @staticmethod
    def _support(probe: dict[str, Any]) -> dict[str, bool]:
        raw = probe.get("support")
        if not isinstance(raw, dict):
            return {}
        return {
            key: value for key, value in raw.items()
            if isinstance(key, str) and isinstance(value, bool)
        }

    @staticmethod
    def _is_denied(status: int | None, requested: str, final_path: str) -> bool:
        if status is not None and 400 <= status < 500:
            return True
        if status is not None and 500 <= status < 600:
            return False
        requested_path = Witness._path_of(requested)
        if requested_path == final_path:
            return False
        lowered = final_path.lower()
        return any(marker in lowered for marker in ("login", "sign-in", "signin", "denied", "forbidden", "unauthorized"))

    @staticmethod
    def _path_of(url: str) -> str:
        return urlsplit(url).path or "/"

    def _contextual_url(self, url: str) -> str:
        return contextual_url(url, self.context)

    @staticmethod
    def _note_for(
        outcome: Outcome,
        status: int | None,
        final_path: str,
        defects: list[Defect],
        *,
        affordance: str | None = None,
    ) -> str:
        if outcome is Outcome.BLOCKED:
            if affordance is not None:
                # The page was served and stayed put; the control simply was not
                # there for this witness. Reporting that as a redirect is a false
                # statement about what happened, and it reaches the emitted spec.
                return f"{affordance} was not rendered for this witness"
            if status in (404, 410):
                return f"HTTP {status}: absent"
            if status is not None and 400 <= status < 500:
                return f"HTTP {status}"
            return f"redirected to {final_path}"
        if outcome is Outcome.PARTIAL:
            if status is not None and 500 <= status < 600:
                return f"HTTP {status} server error"
            return f"{len(defects)} render defect(s)"
        return f"reached {final_path}"

    @staticmethod
    def _remove_listener(session: Any, handler: Callable[[dict[str, Any]], None] | None) -> None:
        if handler is None:
            return
        remove = getattr(session, "remove_listener", None) or getattr(session, "off", None)
        if remove is not None:
            remove("Page.screencastFrame", handler)

    @staticmethod
    def _short_error(error: Exception) -> str:
        return " ".join(str(error).split())[:160] or type(error).__name__


async def run_witnesses(
    surface: Surface,
    *,
    browser: Any | None = None,
    browser_factory: BrowserFactory | None = None,
    contexts: Sequence[Context] | None = None,
    storage_states: Mapping[Privilege | str, StorageState] | None = None,
) -> list[Testimony]:
    """Run all derived contexts against one shared browser and close only their contexts."""
    owned_browser = browser is None
    playwright = None
    if browser is None:
        browser, playwright = await _make_browser(browser_factory)

    testimonies: list[Testimony] = []
    try:
        # Concurrently, not one after another. Sequential visits would make the
        # relational axis unobservable: by the time a receiver looked, the
        # sender's session would already be closed — and a whole class of defect
        # would simply never appear.
        witnesses = [
            Witness(context, browser, storage_state=_storage_for(context, storage_states))
            for context in contexts or derive_witnesses()
        ]
        gathered = await asyncio.gather(
            *(_visit_and_close(witness, surface) for witness in witnesses),
            return_exceptions=True,
        )
        testimonies = [
            item if isinstance(item, Testimony) else Testimony(
                surface, witness.context, Outcome.ERROR,
                note=f"witness failed: {type(item).__name__}: {item}",
            )
            for item, witness in zip(gathered, witnesses)
        ]
    finally:
        if owned_browser:
            await browser.close()
            if playwright is not None:
                await playwright.stop()
    return testimonies


async def _visit_and_close(witness: Witness, surface: Surface) -> Testimony:
    """Close this witness's own context, never the browser the others share."""
    try:
        return await witness.visit(surface)
    finally:
        await witness.close()


async def _make_browser(factory: BrowserFactory | None) -> tuple[Any, Any | None]:
    if factory is not None:
        browser = factory()
        return (await browser if inspect.isawaitable(browser) else browser), None
    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True, args=Witness.LAUNCH_ARGS)
    return browser, playwright


def _storage_for(context: Context, states: Mapping[Privilege | str, StorageState] | None) -> StorageState:
    if states is None:
        return None
    return states.get(context.privilege, states.get(context.privilege.value))
