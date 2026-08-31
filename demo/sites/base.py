"""The contract every demo site implements.

Parallax needs somewhere honest to point at: applications with real roles, real
translation, a real dark mode and real defects. One application cannot carry
every scenario without becoming a page of fixtures, so there is a small fleet of
them, and this is the seam they share. A site is a pure function from a request
to a response — no framework, no sockets, no globals — which is what lets one
server mount all of them and one test drive any of them without a port.

Each site also declares what is deliberately broken in it. That declaration is
the point: a run can then be checked against the truth, so "Parallax found the
escalation" and "Parallax invented nine of them" stop being the same result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Request:
    method: str = "GET"
    path: str = "/"
    # Where this site is mounted, without a trailing slash, e.g. "/shop". A site
    # that links to "/cart" instead of f"{mount}/cart" sends every visitor —
    # and every witness — out of the site and into whatever else the host serves.
    mount: str = ""
    query: dict[str, str] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    @property
    def lang(self) -> str:
        """Return an explicit language choice first, then a safe header fallback.

        Query and cookie choices are deliberate preferences and therefore win.
        Otherwise English remains the default: Accept-Language yields Arabic only
        when it contains a valid Arabic tag and no valid English tag. This keeps
        English-primary visitors who also accept Arabic in English while retaining
        Arabic for the locale witness, which sends ``Accept-Language: ar``.
        Missing, malformed, and other-language headers fall back to English.
        """
        explicit = self.query.get("lang") or self.cookies.get("lang")
        if explicit in ("ar", "en"):
            return explicit

        languages = set()
        for item in self.headers.get("accept-language", "").split(","):
            tag = item.split(";", 1)[0].strip().lower()
            subtags = tag.split("-")
            if tag and all(
                1 <= len(subtag) <= 8 and subtag.isascii() and subtag.isalnum()
                for subtag in subtags
            ) and subtags[0].isalpha():
                languages.add(subtags[0])

        return "ar" if "ar" in languages and "en" not in languages else "en"

    @property
    def theme(self) -> str:
        explicit = self.query.get("theme") or self.cookies.get("theme")
        return explicit if explicit in ("light", "dark") else "light"


@dataclass
class Response:
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    @classmethod
    def html(cls, markup: str, status: int = 200, **headers: str) -> "Response":
        return cls(status, {"Content-Type": "text/html; charset=utf-8", **headers}, markup.encode("utf-8"))

    @classmethod
    def json(cls, payload: object, status: int = 200, **headers: str) -> "Response":
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return cls(status, {"Content-Type": "application/json; charset=utf-8", **headers}, body)

    @classmethod
    def redirect(cls, location: str, status: int = 302, **headers: str) -> "Response":
        return cls(status, {"Location": location, **headers}, b"")

    @classmethod
    def not_found(cls) -> "Response":
        return cls.html("<!doctype html><title>404</title><h1>Not found</h1>", status=404)


@dataclass(frozen=True)
class Planted:
    """One defect deliberately built into a site.

    `defect` names the Defect or FindingKind Parallax should raise; `axis` is the
    witness axis expected to expose it. A site with an empty list is a control:
    finding anything there is a false positive, which is worth proving too.

    `evidence` is optional and exists because kind, axis and route were not
    enough. A protocol fixture broke at step two for an unrelated reason and the
    gate still counted its step-seven plant as found — the finding had the right
    kind on the right route, and nothing checked that it was the right finding.
    When a plant names a phrase, the matching finding has to contain it.
    """

    defect: str
    axis: str
    route: str
    note: str
    evidence: str = ""


@dataclass(frozen=True)
class Account:
    """A seeded login, declared rather than discovered.

    A grader that scrapes credentials out of a site's source with a regular
    expression works right up until someone rewrites the site — which is exactly
    what happened, and it took the whole graded run down with it. A site knows
    its own accounts; it should say so.
    """

    role: str          # "owner" | "member"
    email: str
    password: str


@runtime_checkable
class Site(Protocol):
    name: str          # url prefix and run id, e.g. "workspace"
    title: str
    planted: list[Planted]
    accounts: list[Account]   # empty when the site has no login at all

    def handle(self, request: Request) -> Response: ...


# Served by the fleet from demo/assets/fonts. Every site opens its stylesheet
# with this, so text metrics are a property of the checkout rather than of the
# machine: asking for Georgia or system-ui resolves to a different fallback on
# every host, which is enough to move an overflow measurement across its
# threshold and invent a render finding nobody planted.
FONT_FACE_CSS = "".join(
    f'@font-face{{font-family:"Parallax {label}";src:url("/assets/fonts/parallax-{slug}-{weight}.woff2")'
    f' format("woff2");font-weight:{weight};font-style:normal;font-display:block}}'
    for label, slug in (("Serif", "serif"), ("Sans", "sans"), ("Mono", "mono"))
    for weight in (400, 700)
) + (
    # Anything the sites do not name explicitly would otherwise inherit the user
    # agent's own default — Times New Roman and a bare `monospace`, which resolve
    # to whatever the host has. These two rules carry the lowest useful
    # specificity, so every site rule below still wins.
    'html{font-family:"Parallax Serif",serif}'
    'code,pre,kbd,samp,tt{font-family:"Parallax Mono",monospace}'
)
