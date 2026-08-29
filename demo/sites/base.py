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
        """Arabic when asked for by query, cookie, or Accept-Language — in that order."""
        explicit = self.query.get("lang") or self.cookies.get("lang")
        if explicit in ("ar", "en"):
            return explicit
        accept = self.headers.get("accept-language", "").lower()
        return "ar" if accept.startswith("ar") else "en"

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
    """

    defect: str
    axis: str
    route: str
    note: str


@runtime_checkable
class Site(Protocol):
    name: str          # url prefix and run id, e.g. "workspace"
    title: str
    planted: list[Planted]

    def handle(self, request: Request) -> Response: ...
