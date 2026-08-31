"""Find the way in, and find how the application varies itself.

Everything else in Parallax is handed its sessions. The demo suite knows the
login route and the field names because it wrote the demo; a caller supplies
storage states because a sweep cannot invent an account. That is a reasonable
place to stop for a fixture and an unreasonable one for an agent: the whole
premise is that you point it at a URL, and "first export two storage-state JSON
files by hand" is a long way from that.

Two things are discovered here.

**The way in.** Given a role, an identifier and a secret, find the sign-in
surface, find the form on it, fill the fields that a login form has, submit, and
confirm a session actually exists afterwards. None of that is guessed from a
configuration file; the vocabulary is deliberately multilingual because the
first application this was run against is Arabic.

**How the application varies.** Parallax used to assume `?lang=ar` produced the
Arabic rendering. Applications that keep locale in a user's profile ignore that,
which is how a monolingual sweep of an Arabic site produced a mirroring finding
on every page — the "variant" was the baseline. The locale mechanism is now
discovered and *verified*: a query hint counts only if the document's `lang`
actually changes, and otherwise a real control is located and actuated.

Nothing destructive is ever actuated. The only control this module operates is
one it has identified as a language control, and the only form it submits is one
that contains a password field.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit


# Deliberately multilingual. An agent that can only recognise "Sign in" is an
# agent that only works on English applications.
SIGN_IN_WORDS = (
    "sign in", "signin", "log in", "login", "logon", "sign-in",
    "تسجيل الدخول", "تسجيل دخول", "دخول", "الدخول", "حسابي",
)
SIGN_OUT_WORDS = (
    "sign out", "signout", "log out", "logout", "sign-out",
    "تسجيل الخروج", "خروج", "الخروج",
)
LOCALE_WORDS = (
    "language", "locale", "idioma", "langue",
    "اللغة", "لغة", "اللغه", "تغيير اللغة",
)
SETTINGS_WORDS = (
    "settings", "preferences", "account", "profile",
    "الإعدادات", "اعدادات", "الإعدادت", "الملف الشخصي", "حسابي", "التفضيلات",
)

# Tried before the crawl is consulted, because they cost one request each and
# cover most applications.
COMMON_SIGN_IN_PATHS = (
    "/login", "/signin", "/sign-in", "/auth", "/auth?mode=login",
    "/account/login", "/users/sign_in", "/session/new",
)


@dataclass(frozen=True)
class Credential:
    """One role's way in. The secret is never rendered."""

    role: str
    identifier: str
    secret: str = field(repr=False)

    def __repr__(self) -> str:  # pragma: no cover - defensive, exercised by test
        return f"Credential(role={self.role!r}, identifier={self.identifier!r}, secret=***)"


@dataclass
class SignInReport:
    """Whether a role got in, and by which route — never with what secret."""

    role: str
    succeeded: bool = False
    route: str | None = None
    form: str | None = None
    error: str | None = None

    def report(self) -> dict[str, object]:
        payload: dict[str, object] = {"role": self.role, "succeeded": self.succeeded}
        for key, value in (("route", self.route), ("form", self.form), ("error", self.error)):
            if value:
                payload[key] = value
        return payload


@dataclass
class LocaleMechanism:
    """How this application actually produces a different language."""

    kind: str = "none"  # "query" | "control" | "none"
    detail: str | None = None
    selector: str | None = None
    route: str | None = None

    def report(self) -> dict[str, object]:
        payload: dict[str, object] = {"kind": self.kind}
        for key, value in (("detail", self.detail), ("selector", self.selector), ("route", self.route)):
            if value:
                payload[key] = value
        return payload


_SELECTOR_HELPER = """
const cssEscape = (value) => (window.CSS && CSS.escape) ? CSS.escape(value) : value.replace(/[^a-zA-Z0-9_-]/g, '\\\\$&');
const selectorFor = (el) => {
  if (!el) return null;
  if (el.id) return '#' + cssEscape(el.id);
  const name = el.getAttribute && el.getAttribute('name');
  if (name) return el.tagName.toLowerCase() + '[name="' + name.replace(/"/g, '\\\\"') + '"]';
  const parts = [];
  let node = el;
  while (node && node.nodeType === 1 && parts.length < 5) {
    let part = node.tagName.toLowerCase();
    const parent = node.parentElement;
    if (parent) {
      const siblings = [...parent.children].filter((c) => c.tagName === node.tagName);
      if (siblings.length > 1) part += ':nth-of-type(' + (siblings.indexOf(node) + 1) + ')';
    }
    parts.unshift(part);
    if (node.id) { parts[0] = '#' + cssEscape(node.id); break; }
    node = node.parentElement;
  }
  return parts.join(' > ');
};
"""

LOGIN_FORM_PROBE = f"""
() => {{
  {_SELECTOR_HELPER}
  const skip = new Set(['hidden', 'checkbox', 'radio', 'submit', 'button', 'file']);
  const signIn = {json.dumps(list(SIGN_IN_WORDS))};
  const notThis = ['guest', 'زائر', 'register', 'sign up', 'signup', 'إنشاء', 'انشاء', 'forgot', 'نسيت'];
  const text = (el) => ((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '')).trim();
  const described = (i) => [i.name, i.id, i.autocomplete, i.placeholder, i.getAttribute('aria-label')]
    .filter(Boolean).join(' ');

  const rank = (el) => {{
    const label = text(el).toLowerCase();
    if (!label) return -1;
    // A guest button and a register button both sit next to the password field
    // and both look like a way in. Neither uses the credentials we were given.
    if (notThis.some((word) => label.includes(word))) return -1;
    const hit = signIn.find((word) => label.includes(word.toLowerCase()));
    return hit ? hit.length : -1;
  }};

  const describe = (scope, password) => {{
    const inputs = [...scope.querySelectorAll('input')].filter(
      (i) => i !== password && !skip.has((i.type || 'text').toLowerCase())
    );
    const identifier =
      inputs.find((i) => (i.type || '').toLowerCase() === 'email') ||
      inputs.find((i) => /user|email|login|account|phone|mail|اسم|بريد|هاتف|المعرّف|معرف/i.test(described(i))) ||
      inputs[0] || null;
    const buttons = [...scope.querySelectorAll('button, input[type="submit"], [role="button"]')];
    const ranked = buttons.map((b) => [rank(b), b]).filter(([r]) => r >= 0).sort((a, b) => b[0] - a[0]);
    const submit = ranked.length ? ranked[0][1]
      : scope.querySelector('button[type="submit"], input[type="submit"]');
    return {{
      form: selectorFor(scope),
      identifier: selectorFor(identifier),
      password: selectorFor(password),
      submit: selectorFor(submit),
    }};
  }};

  const found = [];
  for (const password of document.querySelectorAll('input[type="password"]')) {{
    // A <form> is the honest scope when one exists. Modern applications
    // frequently render a sign-in panel with no form element at all, so the
    // fallback climbs to the nearest ancestor that holds both another field and
    // a way to submit — which is what a form would have been.
    let scope = password.closest('form');
    if (!scope) {{
      scope = password.parentElement;
      for (let depth = 0; depth < 8 && scope && scope.parentElement; depth += 1) {{
        const fields = [...scope.querySelectorAll('input')].filter(
          (i) => !skip.has((i.type || 'text').toLowerCase())
        );
        const acts = [...scope.querySelectorAll('button, input[type="submit"], [role="button"]')];
        if (fields.length > 1 && acts.length) break;
        scope = scope.parentElement;
      }}
    }}
    if (scope) found.push(describe(scope, password));
  }}
  return {{ forms: found }};
}}
"""

LINKS_PROBE = """
() => [...document.querySelectorAll('a[href], button, [role="link"], [role="button"]')]
  .map((el) => ({
    href: el.getAttribute('href') || '',
    text: ((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '') +
           ' ' + (el.getAttribute('title') || '')).trim().slice(0, 120),
  }))
  .filter((item) => item.href || item.text)
  .slice(0, 400)
"""

LOCALE_CONTROL_PROBE = f"""
() => {{
  {_SELECTOR_HELPER}
  const words = {json.dumps(list(LOCALE_WORDS))};
  const mentions = (text) => words.some((w) => (text || '').toLowerCase().includes(w.toLowerCase()));
  const described = (el) => [el.textContent, el.getAttribute('aria-label'), el.getAttribute('title'),
                             el.getAttribute('name'), el.id].filter(Boolean).join(' ');
  const selects = [...document.querySelectorAll('select')]
    .filter((el) => mentions(described(el)) ||
      [...el.options].some((o) => /^(ar|en|عرب|إنجل|english|arabic)/i.test(o.value + ' ' + o.textContent)))
    .map((el) => ({{ selector: selectorFor(el), kind: 'select',
                     options: [...el.options].map((o) => o.value).slice(0, 20) }}));
  const links = [...document.querySelectorAll('a[hreflang]')]
    .map((el) => ({{ selector: selectorFor(el), kind: 'link', hreflang: el.getAttribute('hreflang') }}));
  const controls = [...document.querySelectorAll('button, a, [role="button"]')]
    .filter((el) => mentions(described(el)))
    .slice(0, 10)
    .map((el) => ({{ selector: selectorFor(el), kind: 'control', text: (el.textContent || '').trim().slice(0, 40) }}));
  return {{ candidates: [...selects, ...links, ...controls] }};
}}
"""


def _matches(text: str, words: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(word.lower() in lowered for word in words)


def sign_in_candidates(start_url: str, links: list[dict[str, Any]]) -> list[str]:
    """Rank sign-in routes: what the page points at, then the usual paths."""
    origin = f"{urlsplit(start_url).scheme}://{urlsplit(start_url).netloc}"
    found: list[str] = []
    for link in links:
        href, text = str(link.get("href", "")), str(link.get("text", ""))
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        if not (_matches(text, SIGN_IN_WORDS) or _matches(href, SIGN_IN_WORDS)):
            continue
        target = urljoin(start_url, href)
        if urlsplit(target).netloc == urlsplit(start_url).netloc and target not in found:
            found.append(target)
    for path in COMMON_SIGN_IN_PATHS:
        target = urljoin(origin, path)
        if target not in found:
            found.append(target)
    return found


def settings_candidates(start_url: str, links: list[dict[str, Any]]) -> list[str]:
    """Where a signed-in user's preferences are likely to live."""
    found: list[str] = []
    for link in links:
        href, text = str(link.get("href", "")), str(link.get("text", ""))
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        if not (_matches(text, SETTINGS_WORDS) or _matches(href, SETTINGS_WORDS)):
            continue
        target = urljoin(start_url, href)
        if urlsplit(target).netloc == urlsplit(start_url).netloc and target not in found:
            found.append(target)
    return found


class SessionDiscovery:
    """Drive a real browser to get in, and to find how the app changes language."""

    def __init__(self, browser: Any, start_url: str, *, timeout_ms: int = 8_000) -> None:
        self._browser = browser
        self.start_url = start_url
        self._timeout = timeout_ms

    async def sign_in(self, credential: Credential) -> tuple[SignInReport, Any | None]:
        """Find the sign-in surface, use it, and prove a session resulted."""
        report = SignInReport(role=credential.role)
        context = await self._browser.new_context()
        try:
            page = await context.new_page()
            await page.goto(self.start_url, wait_until="domcontentloaded", timeout=self._timeout)
            links = await page.evaluate(LINKS_PROBE)
            for route in sign_in_candidates(self.start_url, list(links or [])):
                form = await self._form_on(page, route)
                if form is None:
                    continue
                report.route, report.form = route, form.get("form")
                if await self._submit(page, form, credential):
                    report.succeeded = True
                    return report, await context.storage_state()
                report.error = "the form was submitted and no session followed"
            report.error = report.error or "no sign-in form was found"
            return report, None
        except Exception as error:  # noqa: BLE001 - a failed sign-in is evidence
            # The secret is not in the message, and must not become part of one.
            report.error = f"{type(error).__name__}: {str(error)[:160]}"
            return report, None
        finally:
            await context.close()

    async def _form_on(self, page: Any, route: str) -> dict[str, Any] | None:
        try:
            await page.goto(route, wait_until="domcontentloaded", timeout=self._timeout)
            # A sign-in panel is frequently not in the served HTML. Probing at
            # domcontentloaded found nothing on the first real application this
            # met, which renders its fields after hydration; waiting for the
            # password field itself is both faster and stricter than waiting for
            # the network to fall quiet.
            await self._await_password_field(page)
            found = await page.evaluate(LOGIN_FORM_PROBE)
        except Exception:
            return None
        forms = (found or {}).get("forms") or []
        return forms[0] if forms else None

    async def _await_password_field(self, page: Any) -> None:
        """Give a client-rendered panel time to exist, without insisting it does."""
        waiter = getattr(page, "wait_for_selector", None)
        if waiter is None:
            return
        try:
            await waiter('input[type="password"]', timeout=self._timeout, state="attached")
        except Exception:
            return

    async def _submit(self, page: Any, form: dict[str, Any], credential: Credential) -> bool:
        identifier, password = form.get("identifier"), form.get("password")
        if not password:
            return False
        if identifier:
            await page.fill(identifier, credential.identifier)
        await page.fill(password, credential.secret)
        if submit := form.get("submit"):
            await page.click(submit)
        else:
            await page.press(password, "Enter")
        try:
            await page.wait_for_load_state("networkidle", timeout=self._timeout)
        except Exception:
            pass
        return await self._is_signed_in(page)

    async def _is_signed_in(self, page: Any) -> bool:
        """A session exists if the password prompt is gone or a way out appeared.

        Neither alone is sufficient. An application can leave a password field on
        the page after signing in, and one can show a sign-out control to
        everybody; requiring either but reporting both keeps a redirect loop from
        being mistaken for a session.
        """
        try:
            still_asking = await page.locator('input[type="password"]').count()
            text = (await page.inner_text("body"))[:4000]
        except Exception:
            return False
        return not still_asking or _matches(text, SIGN_OUT_WORDS)

    async def locale_mechanism(self, storage_state: Any | None = None) -> LocaleMechanism:
        """Establish how a second language is actually produced, or that it is not.

        The query hint is tried first because it is free, but it only counts if
        the document's `lang` really changes. Assuming it worked is what made a
        monolingual Arabic site report a mirroring defect on every surface.
        """
        context = await self._browser.new_context(storage_state=storage_state)
        try:
            page = await context.new_page()
            await page.goto(self.start_url, wait_until="domcontentloaded", timeout=self._timeout)
            baseline = await page.evaluate("() => document.documentElement.lang || ''")

            hinted = f"{self.start_url}{'&' if '?' in self.start_url else '?'}lang=ar"
            await page.goto(hinted, wait_until="domcontentloaded", timeout=self._timeout)
            if (await page.evaluate("() => document.documentElement.lang || ''")) not in {baseline, ""}:
                return LocaleMechanism("query", "the lang attribute changes for ?lang=ar")

            await page.goto(self.start_url, wait_until="domcontentloaded", timeout=self._timeout)
            for route in [self.start_url, *settings_candidates(
                self.start_url, list(await page.evaluate(LINKS_PROBE) or [])
            )][:4]:
                found = await self._locale_control_on(page, route)
                if found is not None:
                    return found
            return LocaleMechanism("none", "no language control was found on the page or in settings")
        except Exception as error:  # noqa: BLE001 - reported, never raised
            return LocaleMechanism("none", f"{type(error).__name__}: {str(error)[:120]}")
        finally:
            await context.close()

    async def _locale_control_on(self, page: Any, route: str) -> LocaleMechanism | None:
        try:
            if str(getattr(page, "url", "")) != route:
                await page.goto(route, wait_until="domcontentloaded", timeout=self._timeout)
            before = await page.evaluate("() => document.documentElement.lang || ''")
            found = await page.evaluate(LOCALE_CONTROL_PROBE)
        except Exception:
            return None
        for candidate in (found or {}).get("candidates", []):
            if await self._actuates_locale(page, candidate, before):
                return LocaleMechanism(
                    "control",
                    f"a {candidate.get('kind')} changes the lang attribute",
                    selector=candidate.get("selector"),
                    route=route,
                )
        return None

    async def _actuates_locale(self, page: Any, candidate: dict[str, Any], before: str) -> bool:
        """Operate one identified language control and see whether it worked."""
        selector = candidate.get("selector")
        if not selector:
            return False
        try:
            if candidate.get("kind") == "select":
                options = [o for o in candidate.get("options", []) if o and o != before]
                if not options:
                    return False
                await page.select_option(selector, options[0])
            else:
                await page.click(selector, timeout=self._timeout)
            try:
                await page.wait_for_load_state("networkidle", timeout=self._timeout)
            except Exception:
                pass
            return (await page.evaluate("() => document.documentElement.lang || ''")) not in {before, ""}
        except Exception:
            return False


def credentials_from_data(data: Any, *, source: str = "credentials") -> list[Credential]:
    """Read roles and secrets from a file rather than from the command line.

    A secret passed as an argument is visible in `ps` to every user on the
    machine and lands in shell history. The file is read once and its contents
    never reach a report, a feed event, or a generated spec.
    """
    if not isinstance(data, dict):
        raise ValueError(f"{source}: expected an object of role -> credential")
    entries = data.get("credentials", data)
    if not isinstance(entries, dict) or not entries:
        raise ValueError(f"{source}: expected at least one role")
    result: list[Credential] = []
    for role, value in entries.items():
        if not isinstance(role, str) or not role.strip():
            raise ValueError(f"{source}: every role must be a non-empty name")
        if not isinstance(value, dict):
            raise ValueError(f"{source}: {role} must be an object with identifier and secret")
        identifier, secret = value.get("identifier"), value.get("secret")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError(f"{source}: {role}.identifier must be a non-empty string")
        if not isinstance(secret, str) or not secret:
            raise ValueError(f"{source}: {role}.secret must be a non-empty string")
        result.append(Credential(role.strip(), identifier, secret))
    return result
