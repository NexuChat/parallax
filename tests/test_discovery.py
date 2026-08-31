from __future__ import annotations

import asyncio
import json

from parallax.discovery import (
    COMMON_SIGN_IN_PATHS,
    Credential,
    LocaleMechanism,
    SessionDiscovery,
    SignInReport,
    settings_candidates,
    sign_in_candidates,
)


START = "https://chat.example/"


def test_a_secret_is_never_rendered() -> None:
    credential = Credential("owner", "owner@chat.example", "hunter2")

    assert "hunter2" not in repr(credential)
    assert "owner@chat.example" in repr(credential)


def test_a_secret_never_reaches_a_report() -> None:
    report = SignInReport("owner", False, route=f"{START}login", error="TimeoutError: gave up")

    assert "hunter2" not in json.dumps(report.report())
    assert report.report()["route"] == f"{START}login"


def test_links_the_page_offers_outrank_the_guessed_paths() -> None:
    routes = sign_in_candidates(START, [{"href": "/account/enter", "text": "Sign in"}])

    assert routes[0] == "https://chat.example/account/enter"
    assert routes[1] == f"https://chat.example{COMMON_SIGN_IN_PATHS[0]}"


def test_arabic_sign_in_text_is_recognised() -> None:
    routes = sign_in_candidates(START, [{"href": "/dukhul", "text": "تسجيل الدخول"}])

    assert routes[0] == "https://chat.example/dukhul"


def test_offsite_and_script_links_are_never_followed() -> None:
    routes = sign_in_candidates(START, [
        {"href": "https://evil.example/login", "text": "Sign in"},
        {"href": "javascript:signIn()", "text": "Sign in"},
        {"href": "#login", "text": "Sign in"},
    ])

    assert all("evil.example" not in route for route in routes)
    assert all(not route.endswith("#login") for route in routes)
    assert routes == [f"https://chat.example{path}" for path in COMMON_SIGN_IN_PATHS]


def test_arabic_settings_links_are_found() -> None:
    routes = settings_candidates(START, [
        {"href": "/profile/settings", "text": "الإعدادات"},
        {"href": "/pricing", "text": "Pricing"},
    ])

    assert routes == ["https://chat.example/profile/settings"]


class FakePage:
    """A page that answers the probes the way a real one would."""

    def __init__(self, script: dict) -> None:
        self.script = script
        self.url = START
        self.filled: dict[str, str] = {}
        self.clicked: list[str] = []
        self.selected: list[tuple[str, str]] = []
        self.lang = script.get("lang", "en")

    async def goto(self, url: str, **_kwargs) -> None:
        self.url = url
        if url in self.script.get("lang_by_route", {}):
            self.lang = self.script["lang_by_route"][url]

    async def evaluate(self, expression: str, *_args):
        if "document.documentElement.lang" in expression:
            return self.lang
        if 'input[type="password"]' in expression:
            return {"forms": self.script.get("forms", {}).get(self.url, [])}
        if "candidates" in expression:
            return {"candidates": self.script.get("locale_controls", [])}
        return self.script.get("links", [])

    async def fill(self, selector: str, value: str) -> None:
        self.filled[selector] = value

    async def click(self, selector: str, **_kwargs) -> None:
        self.clicked.append(selector)
        if selector in self.script.get("lang_after_click", {}):
            self.lang = self.script["lang_after_click"][selector]
        if self.script.get("signs_in_on_click"):
            self.script["signed_in"] = True

    async def select_option(self, selector: str, value: str) -> None:
        self.selected.append((selector, value))
        if self.script.get("lang_after_select"):
            self.lang = self.script["lang_after_select"]

    async def press(self, *_args) -> None:
        self.script["signed_in"] = self.script.get("signs_in_on_click", False)

    async def wait_for_load_state(self, *_args, **_kwargs) -> None:
        return None

    async def inner_text(self, _selector: str) -> str:
        return "Sign out" if self.script.get("signed_in") else "Please sign in"

    def locator(self, _selector: str) -> "FakePage":
        return self

    async def count(self) -> int:
        return 0 if self.script.get("signed_in") else 1


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.closed = False

    async def new_page(self) -> FakePage:
        return self.page

    async def storage_state(self) -> dict:
        return {"cookies": [{"name": "session", "value": "abc"}], "origins": []}

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.contexts: list[FakeContext] = []

    async def new_context(self, **_kwargs) -> FakeContext:
        context = FakeContext(self.page)
        self.contexts.append(context)
        return context


LOGIN_FORM = {
    "form": "form#login",
    "identifier": "input[name=\"email\"]",
    "password": "input[name=\"password\"]",
    "submit": "button[type=\"submit\"]",
}


def test_the_discovered_form_is_filled_and_a_session_is_confirmed() -> None:
    page = FakePage({
        "links": [{"href": "/enter", "text": "Sign in"}],
        "forms": {"https://chat.example/enter": [LOGIN_FORM]},
        "signs_in_on_click": True,
    })
    browser = FakeBrowser(page)

    report, state = asyncio.run(
        SessionDiscovery(browser, START).sign_in(Credential("owner", "o@chat.example", "hunter2"))
    )

    assert report.succeeded is True
    assert report.route == "https://chat.example/enter"
    assert page.filled['input[name="email"]'] == "o@chat.example"
    assert page.filled['input[name="password"]'] == "hunter2"
    assert state is not None and state["cookies"][0]["name"] == "session"
    assert all(context.closed for context in browser.contexts)


def test_a_form_that_submits_without_producing_a_session_is_a_failure() -> None:
    page = FakePage({
        "links": [{"href": "/enter", "text": "Sign in"}],
        "forms": {"https://chat.example/enter": [LOGIN_FORM]},
        "signs_in_on_click": False,
    })

    report, state = asyncio.run(
        SessionDiscovery(FakeBrowser(page), START).sign_in(Credential("owner", "o@x", "s"))
    )

    assert report.succeeded is False
    assert state is None
    assert report.error is not None and "no session followed" in report.error


def test_no_form_anywhere_says_so_rather_than_claiming_success() -> None:
    page = FakePage({"links": [], "forms": {}})

    report, state = asyncio.run(
        SessionDiscovery(FakeBrowser(page), START).sign_in(Credential("owner", "o@x", "s"))
    )

    assert report.succeeded is False and state is None
    assert report.error == "no sign-in form was found"


def test_a_query_hint_counts_only_when_the_lang_attribute_really_changes() -> None:
    """Assuming ?lang=ar worked is what made a monolingual site fail every page."""
    ignored = FakePage({"lang": "ar", "links": [], "locale_controls": []})

    mechanism = asyncio.run(SessionDiscovery(FakeBrowser(ignored), START).locale_mechanism())

    assert mechanism.kind == "none"
    assert "no language control" in (mechanism.detail or "")


def test_a_query_hint_that_does_change_the_lang_is_accepted() -> None:
    honoured = FakePage({
        "lang": "en",
        "lang_by_route": {"https://chat.example/?lang=ar": "ar"},
        "links": [],
    })

    mechanism = asyncio.run(SessionDiscovery(FakeBrowser(honoured), START).locale_mechanism())

    assert mechanism.kind == "query"


def test_a_language_control_is_actuated_and_verified() -> None:
    page = FakePage({
        "lang": "en",
        "links": [],
        "locale_controls": [{"selector": "#lang-toggle", "kind": "control", "text": "اللغة"}],
        "lang_after_click": {"#lang-toggle": "ar"},
    })

    mechanism = asyncio.run(SessionDiscovery(FakeBrowser(page), START).locale_mechanism())

    assert mechanism.kind == "control"
    assert mechanism.selector == "#lang-toggle"
    assert page.clicked == ["#lang-toggle"]


def test_a_control_that_does_not_change_the_language_is_not_accepted() -> None:
    page = FakePage({
        "lang": "en",
        "links": [],
        "locale_controls": [{"selector": "#not-really", "kind": "control", "text": "language"}],
    })

    mechanism = asyncio.run(SessionDiscovery(FakeBrowser(page), START).locale_mechanism())

    assert mechanism.kind == "none"


def test_the_mechanism_report_carries_no_surprises() -> None:
    assert LocaleMechanism("none").report() == {"kind": "none"}
    assert LocaleMechanism("query", "d").report() == {"kind": "query", "detail": "d"}
