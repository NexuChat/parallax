"""Browser proofs for every deliberately planted Parallax demo defect."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import re
import threading
import time
from collections.abc import Generator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest


try:
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright
except ImportError:  # pragma: no cover - exercised on browser-less machines
    async_playwright = None
    PlaywrightError = Exception


pytestmark = pytest.mark.skipif(async_playwright is None, reason="Playwright is not installed")


@pytest.fixture(scope="module")
def demo_url() -> Generator[str]:
    """Run the real demo HTTP adapter locally, with an OS-assigned port."""
    serve = importlib.import_module("serve")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), serve.handler_for(serve.Fleet()))
    except OSError as error:  # pragma: no cover - sandbox environments may forbid listeners
        pytest.skip(f"A local demo server cannot start: {error}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


async def browser_page(*, viewport: dict[str, int] | None = None):
    """Yield a page and guarantee browser cleanup even when an assertion fails."""
    assert async_playwright is not None
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
    except PlaywrightError as error:  # pragma: no cover - environment dependent
        pytest.skip(f"Chromium is unavailable: {error}")
    context = await browser.new_context(viewport=viewport)
    page = await context.new_page()
    return playwright, browser, context, page


async def close_browser(resources: tuple) -> None:
    playwright, browser, context, _page = resources
    await context.close()
    await browser.close()
    await playwright.stop()


def account_password(module_name: str, account: str) -> str:
    """Extract seeded credentials from each site's documented module contract."""
    documentation = inspect.getdoc(importlib.import_module(module_name)) or ""
    pair = re.search(rf"``{re.escape(account)} / ([^`]+)``", documentation)
    if pair:
        return pair.group(1)
    password = re.search(r"password ``([^`]+)``", documentation)
    assert password, f"No documented password for {module_name}"
    return password.group(1)


async def login(page, base: str, site: str, account: str, module_name: str, *, email: bool = False) -> None:
    await page.goto(f"{base}/{site}/login")
    await page.locator('input[name="email"]' if email else 'input[name="username"]').fill(account)
    await page.locator('input[name="password"]').fill(account_password(module_name, account))
    await page.locator('button[type="submit"]').click()
    await page.wait_for_load_state("networkidle")


async def rect(page, selector: str) -> dict[str, float]:
    value = await page.locator(selector).evaluate("element => element.getBoundingClientRect().toJSON()")
    assert value is not None
    return value


async def probe(page) -> dict:
    source = (Path(__file__).parents[1] / "src/parallax/probe.js").read_text(encoding="utf-8")
    snapshot = await page.evaluate(source)
    assert isinstance(snapshot, dict)
    return snapshot


def test_probe_content_signature_ignores_chrome_outside_main() -> None:
    async def check() -> None:
        resources = await browser_page()
        try:
            page = resources[3]
            await page.set_content('<header><span id="badge">2</span></header><main id="content">Stable content</main>')
            initial = (await probe(page))["contentSignature"]
            await page.locator("#badge").evaluate("element => { element.textContent = '3'; }")
            assert (await probe(page))["contentSignature"] == initial
            await page.locator("#content").evaluate("element => { element.textContent = 'Changed content'; }")
            assert (await probe(page))["contentSignature"] != initial
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_probe_content_signature_falls_back_to_body_without_main() -> None:
    async def check() -> None:
        resources = await browser_page()
        try:
            page = resources[3]
            await page.set_content('<article id="content">Initial content</article>')
            initial = (await probe(page))["contentSignature"]
            await page.locator("#content").evaluate("element => { element.textContent = 'Changed content'; }")
            assert (await probe(page))["contentSignature"] != initial
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_shop_viewports_share_a_main_content_signature(demo_url: str) -> None:
    async def check() -> None:
        resources = await browser_page(viewport={"width": 1280, "height": 800})
        try:
            page = resources[3]
            await page.goto(f"{demo_url}/shop/")
            desktop = (await probe(page))["contentSignature"]
            await page.set_viewport_size({"width": 360, "height": 740})
            assert (await probe(page))["contentSignature"] == desktop
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_docs_faq_viewport_plant_changes_the_main_content_signature(demo_url: str) -> None:
    async def check() -> None:
        resources = await browser_page(viewport={"width": 1280, "height": 800})
        try:
            page = resources[3]
            await page.goto(f"{demo_url}/docs/faq")
            desktop = (await probe(page))["contentSignature"]
            await page.set_viewport_size({"width": 767, "height": 800})
            assert (await probe(page))["contentSignature"] != desktop
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_deliberate_workspace_public_audit_and_private_owner_routes(demo_url: str) -> None:
    async def check() -> None:
        resources = await browser_page()
        try:
            page = resources[3]
            audit = await page.goto(f"{demo_url}/workspace/audit")
            assert audit and audit.status == 200
            assert await page.locator("h1").inner_text() == "Audit log"
            for route in ("settings", "billing"):
                response = await page.goto(f"{demo_url}/workspace/{route}")
                assert response and response.status == 200
                assert page.url.endswith("/workspace/login")
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_deliberate_workspace_rtl_composer_does_not_mirror(demo_url: str) -> None:
    async def check() -> None:
        resources = await browser_page(viewport={"width": 1280, "height": 800})
        try:
            page = resources[3]
            await login(page, demo_url, "workspace", "owner@demo", "sites.workspace", email=True)
            await page.goto(f"{demo_url}/workspace/threads?lang=en")
            english_tool, english_control = await rect(page, ".composer-tools"), await rect(page, '.composer button[type="submit"]')
            width = await page.evaluate("innerWidth")
            await page.goto(f"{demo_url}/workspace/threads?lang=ar")
            arabic_tool, arabic_control = await rect(page, ".composer-tools"), await rect(page, '.composer button[type="submit"]')
            mirrored_tool_x = width - english_tool["x"] - english_tool["width"]
            mirrored_control_x = width - english_control["x"] - english_control["width"]
            assert abs(arabic_tool["x"] - mirrored_tool_x) > 1
            assert abs(arabic_control["x"] - mirrored_control_x) <= 1
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_deliberate_workspace_dark_theme_shifts_content_geometry(demo_url: str) -> None:
    async def check() -> None:
        resources = await browser_page()
        try:
            page = resources[3]
            await login(page, demo_url, "workspace", "owner@demo", "sites.workspace", email=True)
            await page.goto(f"{demo_url}/workspace/threads?theme=light")
            light = await rect(page, ".app-shell")
            await page.goto(f"{demo_url}/workspace/threads?theme=dark")
            dark = await rect(page, ".app-shell")
            assert dark["y"] > light["y"]
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_deliberate_workspace_quiet_messages_do_not_propagate_to_peer(demo_url: str) -> None:
    async def check() -> None:
        resources = await browser_page()
        try:
            _playwright, _browser, first, page_a = resources
            second = await first.new_page()
            await login(page_a, demo_url, "workspace", "owner@demo", "sites.workspace", email=True)
            await login(second, demo_url, "workspace", "member@demo", "sites.workspace", email=True)
            initial = await second.evaluate("async () => (await fetch('/workspace/api/messages?since=0')).json()")
            since = max(message["id"] for message in initial["messages"])
            quiet_text, general_text = "quiet browser plant", "general browser plant"
            await page_a.goto(f"{demo_url}/workspace/threads")
            await page_a.locator('input[value="quiet"]').check()
            await page_a.locator('input[name="message"]').fill(quiet_text)
            await page_a.locator("button").filter(has_text="Send").click()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                peer = await second.evaluate("async since => (await fetch('/workspace/api/messages?since=' + since)).json()", since)
                assert quiet_text not in [message["text"] for message in peer["messages"]]
                await asyncio.sleep(0.1)
            await page_a.locator('input[value="general"]').check()
            await page_a.locator('input[name="message"]').fill(general_text)
            await page_a.locator("button").filter(has_text="Send").click()
            for _ in range(20):
                peer = await second.evaluate("async since => (await fetch('/workspace/api/messages?since=' + since)).json()", since)
                if general_text in [message["text"] for message in peer["messages"]]:
                    break
                await asyncio.sleep(0.1)
            else:
                pytest.fail("A normal-thread message did not reach the second browser session")
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_deliberate_shop_checkout_primary_button_is_offscreen_at_360px(demo_url: str) -> None:
    async def check() -> None:
        resources = await browser_page(viewport={"width": 360, "height": 740})
        try:
            page = resources[3]
            await page.goto(f"{demo_url}/shop/checkout")
            button = await rect(page, ".checkout-action-row .button")
            assert button["right"] > await page.evaluate("innerWidth")
            snapshot = await probe(page)
            observations = [item for item in snapshot["defects"] if item["type"] == "offscreen_control"]
            assert any(item["selector"].endswith("div.checkout-action-row > button.button") for item in observations)
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_probe_does_not_report_controls_reachable_in_a_scrollable_ancestor() -> None:
    async def check() -> None:
        resources = await browser_page(viewport={"width": 360, "height": 740})
        try:
            page = resources[3]
            await page.set_content("""
                <main id="rail" style="width: 240px; overflow-x: auto">
                  <div style="width: 720px; padding-left: 600px">
                    <button id="reachable">Reach me</button>
                  </div>
                </main>
            """)
            snapshot = await probe(page)
            observations = [item for item in snapshot["defects"] if item["type"] == "offscreen_control"]
            assert all(item["selector"] != "#reachable" for item in observations)
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_deliberate_shop_cart_has_horizontal_overflow_at_360px(demo_url: str) -> None:
    async def check() -> None:
        resources = await browser_page(viewport={"width": 360, "height": 740})
        try:
            page = resources[3]
            await page.goto(f"{demo_url}/shop/cart")
            dimensions = await page.evaluate("({scrollWidth: document.documentElement.scrollWidth, innerWidth})")
            assert dimensions["scrollWidth"] > dimensions["innerWidth"]
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_deliberate_shop_quantity_stepper_is_smaller_than_44px(demo_url: str) -> None:
    async def check() -> None:
        resources = await browser_page(viewport={"width": 360, "height": 740})
        try:
            page = resources[3]
            await page.goto(f"{demo_url}/shop/cart")
            stepper = await rect(page, ".cart-table tbody tr:first-child .stepper button:first-child")
            assert stepper["width"] < 44 or stepper["height"] < 44
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_deliberate_shop_product_title_is_clipped_by_its_container(demo_url: str) -> None:
    async def check() -> None:
        resources = await browser_page(viewport={"width": 360, "height": 740})
        try:
            page = resources[3]
            await page.goto(f"{demo_url}/shop/product/organizer")
            clipped = await page.locator(".product-title-box").evaluate("box => box.scrollHeight > box.clientHeight")
            assert clipped
            snapshot = await probe(page)
            observations = [item for item in snapshot["defects"] if item["type"] == "clipped"]
            assert any(".product-title-box" in item["selector"] for item in observations)

            await page.set_viewport_size({"width": 1280, "height": 800})
            await page.reload()
            desktop_clipped = await page.locator(".product-title-box").evaluate(
                "box => box.scrollHeight > box.clientHeight"
            )
            assert not desktop_clipped
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_deliberate_docs_arabic_guide_shows_raw_i18n_key(demo_url: str) -> None:
    async def check() -> None:
        resources = await browser_page()
        try:
            page = resources[3]
            await page.goto(f"{demo_url}/docs/guide?lang=ar")
            assert await page.locator("body").inner_text() is not None
            assert "guide.sections.limits.title" in await page.locator("body").inner_text()
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_deliberate_docs_dark_help_text_fails_wcag_aa_contrast(demo_url: str) -> None:
    async def check() -> None:
        resources = await browser_page()
        try:
            page = resources[3]
            await page.goto(f"{demo_url}/docs/?theme=dark")
            element_background, backdrop_background = await page.locator(".help-text").evaluate("""element => {
                let background = element;
                while (background && getComputedStyle(background).backgroundColor === 'rgba(0, 0, 0, 0)') {
                    background = background.parentElement;
                }
                return [getComputedStyle(element).backgroundColor, getComputedStyle(background).backgroundColor];
            }""")
            assert element_background == "rgba(0, 0, 0, 0)"
            assert backdrop_background != element_background
            ratio = await page.locator(".help-text").evaluate("""element => {
                const rgb = value => value.match(/\\d+/g).slice(0, 3).map(Number);
                const luminance = color => {
                    const channels = rgb(color).map(value => value / 255).map(value =>
                        value <= .03928 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
                    return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2];
                };
                let background = element;
                while (getComputedStyle(background).backgroundColor === 'rgba(0, 0, 0, 0)') background = background.parentElement;
                const a = luminance(getComputedStyle(element).color);
                const b = luminance(getComputedStyle(background).backgroundColor);
                return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
            }""")
            assert ratio < 4.5
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_deliberate_docs_related_questions_disappear_below_768px(demo_url: str) -> None:
    async def check() -> None:
        resources = await browser_page(viewport={"width": 1440, "height": 800})
        try:
            page = resources[3]
            await page.goto(f"{demo_url}/docs/faq")
            assert await page.locator(".related-questions").is_visible()
            await page.set_viewport_size({"width": 767, "height": 800})
            assert not await page.locator(".related-questions").is_visible()
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_deliberate_admin_reports_authorization_is_inverted(demo_url: str) -> None:
    async def check() -> None:
        resources = await browser_page()
        try:
            _playwright, _browser, owner_context, owner = resources
            member_context = await _browser.new_context()
            member = await member_context.new_page()
            await login(owner, demo_url, "admin", "owner", "sites.admin")
            await login(member, demo_url, "admin", "member", "sites.admin")
            await owner.goto(f"{demo_url}/admin/reports")
            assert owner.url.endswith("/admin/login")
            response = await member.goto(f"{demo_url}/admin/reports")
            assert response and response.status == 200
            assert "Scheduled reports" in await member.locator("h1").inner_text()
            await member_context.close()
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_deliberate_admin_exports_only_resolves_in_english(demo_url: str) -> None:
    async def check() -> None:
        resources = await browser_page()
        try:
            page = resources[3]
            await login(page, demo_url, "admin", "owner", "sites.admin")
            english = await page.goto(f"{demo_url}/admin/exports?lang=en")
            assert english and english.status == 200
            arabic = await page.goto(f"{demo_url}/admin/exports?lang=ar")
            assert arabic and arabic.status == 404
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_deliberate_admin_legacy_route_is_dead_for_every_role(demo_url: str) -> None:
    async def check() -> None:
        resources = await browser_page()
        try:
            _playwright, browser, _context, anonymous = resources
            for account in ("owner", "member"):
                context = await browser.new_context()
                page = await context.new_page()
                await login(page, demo_url, "admin", account, "sites.admin")
                response = await page.goto(f"{demo_url}/admin/legacy")
                assert response and response.status == 404
                await context.close()
            response = await anonymous.goto(f"{demo_url}/admin/legacy")
            assert response and response.status == 404
        finally:
            await close_browser(resources)
    asyncio.run(check())


def test_clean_control_has_none_of_the_planted_browser_defects(demo_url: str) -> None:
    async def check() -> None:
        resources = await browser_page(viewport={"width": 360, "height": 740})
        try:
            page = resources[3]
            await page.goto(f"{demo_url}/control/")
            dimensions = await page.evaluate("({scrollWidth: document.documentElement.scrollWidth, innerWidth})")
            assert dimensions["scrollWidth"] <= dimensions["innerWidth"]
            targets = await page.locator(".tap, button, input").evaluate_all("elements => elements.map(element => { const r = element.getBoundingClientRect(); return [r.width, r.height]; })")
            assert all(width >= 44 and height >= 44 for width, height in targets)
            for language in ("en", "ar"):
                await page.goto(f"{demo_url}/control/?lang={language}")
                assert "guide.sections.limits.title" not in await page.locator("body").inner_text()
            await page.set_viewport_size({"width": 1280, "height": 800})
            await page.goto(f"{demo_url}/control/?lang=en&theme=light")
            english = await rect(page, ".mast")
            light_main = await rect(page, "main")
            width = await page.evaluate("innerWidth")
            await page.goto(f"{demo_url}/control/?lang=ar&theme=light")
            arabic = await rect(page, ".mast")
            assert abs(arabic["x"] - (width - english["x"] - english["width"])) <= 1
            await page.goto(f"{demo_url}/control/?lang=en&theme=dark")
            dark_main = await rect(page, "main")
            assert (dark_main["x"], dark_main["y"], dark_main["width"], dark_main["height"]) == (light_main["x"], light_main["y"], light_main["width"], light_main["height"])
        finally:
            await close_browser(resources)
    asyncio.run(check())
