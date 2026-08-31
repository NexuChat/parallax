"""Serve every available pure demo site under its own URL prefix.

Run with ``python demo/serve.py``.  Sites are intentionally discovered at
runtime so this small front door remains usable while individual demos land.
"""

from __future__ import annotations

import importlib
import inspect
import os
import pkgutil
import sys
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit


DEMO_DIR = Path(__file__).resolve().parent
if str(DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(DEMO_DIR))

from sites.base import FONT_FACE_CSS, Request, Response, Site  # noqa: E402

_FONT_ROOT = DEMO_DIR / "assets" / "fonts"
# An explicit allowlist rather than a directory listing: this route takes a path
# segment straight from the request, and the allowlist is what stands between
# that and the filesystem.
_FONT_FILES = frozenset({
    "parallax-serif-400.woff2",
    "parallax-serif-700.woff2",
    "parallax-sans-400.woff2",
    "parallax-sans-700.woff2",
    "parallax-mono-400.woff2",
    "parallax-mono-700.woff2",
})


def discover_sites() -> list[Site]:
    """Load valid site classes without coupling the server to named demos."""
    sites_dir = DEMO_DIR / "sites"
    discovered: list[Site] = []
    for info in pkgutil.iter_modules([str(sites_dir)]):
        if info.name == "base" or info.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"sites.{info.name}")
            candidates: list[Site] = []
            for _, candidate in inspect.getmembers(module, inspect.isclass):
                if candidate.__module__ != module.__name__:
                    continue
                try:
                    instance = candidate()
                except TypeError:
                    continue
                if isinstance(instance, Site):
                    candidates.append(instance)
            if len(candidates) != 1:
                raise ValueError(f"expected one Site class, found {len(candidates)}")
            discovered.append(candidates[0])
        except Exception as error:
            print(f"demo: skipped {info.name}: {error}", file=sys.stderr)
    return sorted(discovered, key=lambda site: site.name)


class Fleet:
    """HTTP-independent adapter, kept small enough for socket-free tests."""

    def __init__(self, sites: list[Site] | None = None) -> None:
        available = discover_sites() if sites is None else sites
        self.sites = {site.name: site for site in available}

    def dispatch(self, method: str, target: str, headers: dict[str, str], body: bytes) -> Response:
        parts = urlsplit(target)
        path = unquote(parts.path or "/")
        if _has_parent_segment(path):
            return Response.not_found()
        if path == "/healthz":
            return Response(status=200, headers={"Content-Type": "text/plain; charset=utf-8"}, body=b"ok\n")
        if path == "/":
            return self._front_door()
        if path.startswith("/assets/fonts/"):
            return self._font(path.removeprefix("/assets/fonts/"))
        segments = path.lstrip("/").split("/", 1)
        site = self.sites.get(segments[0])
        if site is None:
            return Response.not_found()
        local_path = "/" + segments[1] if len(segments) == 2 else "/"
        normalized_headers = {key.lower(): value for key, value in headers.items()}
        request = Request(
            method=method.upper(),
            path=local_path,
            mount=f"/{site.name}",
            query=dict(parse_qsl(parts.query, keep_blank_values=True)),
            cookies=_cookies(normalized_headers.get("cookie", "")),
            headers=normalized_headers,
            body=body,
        )
        return site.handle(request)

    def _font(self, name: str) -> Response:
        """Serve the bundled faces so text metrics do not depend on the host.

        Every site asks for these by name instead of Georgia or system-ui, which
        resolve to a different fallback on every machine — enough to move an
        overflow or tap-target measurement across its threshold and report a
        render defect nobody planted.
        """
        if name not in _FONT_FILES:
            return Response.not_found()
        path = _FONT_ROOT / name
        if not path.is_file():
            return Response.not_found()
        return Response(
            status=200,
            headers={
                "Content-Type": "font/woff2",
                "Cache-Control": "public, max-age=31536000, immutable",
            },
            body=path.read_bytes(),
        )

    def _front_door(self) -> Response:
        """Every application the fleet serves, and what each one is for.

        Generated from the sites themselves rather than a curated list, so a new
        fixture appears here by existing. The real-time ones — the game and the
        call room — are applications in the fleet exactly like the storefront
        and the docs site, not test scaffolding parked somewhere else.
        """
        cards = "".join(
            f'<article class="app">'
            f'<h2><a href="/{escape(site.name)}{escape(getattr(site, "entry", "/"))}">{escape(site.title)}</a></h2>'
            f'<p>{escape(getattr(site, "blurb", ""))}</p>'
            f'<p class="meta"><code>/{escape(site.name)}/</code>'
            + (
                f' · <b>{len(site.planted)}</b> planted defect{"" if len(site.planted) == 1 else "s"}'
                if getattr(site, "planted", None) else " · <b>clean control</b> — nothing planted"
            )
            + (f' · {len(getattr(site, "accounts", []))} accounts' if getattr(site, "accounts", None) else "")
            + "</p></article>"
            for site in self.sites.values()
        ) or "<p>No demo sites are available yet.</p>"
        planted = sum(len(getattr(site, "planted", [])) for site in self.sites.values())
        return Response.html(
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            "<title>Parallax demo fleet</title><style>"
            f"{FONT_FACE_CSS}"
            'body{margin:0;background:#fbfbfa;color:#16211f;font:16px/1.6 "Parallax Serif",serif}'
            ".shell{max-inline-size:60rem;margin-inline:auto;padding:clamp(20px,5vw,56px)}"
            'h1{font:800 clamp(28px,5vw,44px)/1.1 "Parallax Sans",sans-serif;letter-spacing:-.02em;margin:0 0 8px}'
            ".lead{color:#4c5a57;max-inline-size:52ch;margin:0 0 32px}"
            ".grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(17rem,1fr))}"
            ".app{background:#fff;border:1px solid #d8e0de;border-radius:12px;padding:16px}"
            'h2{font:700 18px/1.3 "Parallax Sans",sans-serif;margin:0 0 6px}'
            "h2 a{color:#16211f;text-decoration:none}h2 a:hover{text-decoration:underline}"
            ".app p{margin:0 0 8px;color:#3d4a48;font-size:14px}"
            '.meta{color:#6b7a77;font:600 12px/1.5 "Parallax Mono",monospace;margin:0}'
            ".meta code{background:#eef2f1;border-radius:4px;padding:1px 5px}"
            "a:focus-visible{outline:3px solid #16211f;outline-offset:2px}"
            "</style></head><body><main class=\"shell\">"
            "<h1>Parallax demo fleet</h1>"
            f"<p class=\"lead\">{len(self.sites)} applications served from one process. "
            f"{planted} defects are planted in code and declared by the site that carries them, "
            f"so a sweep can be graded rather than admired.</p>"
            f'<div class="grid">{cards}</div></main></body></html>'
        )


def _has_parent_segment(path: str) -> bool:
    return any(segment == ".." for segment in path.split("/"))


def _cookies(header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for item in header.split(";"):
        key, separator, value = item.strip().partition("=")
        if separator and key:
            cookies[key] = value
    return cookies


def handler_for(fleet: Fleet) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _respond(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            response = fleet.dispatch(self.command, self.path, dict(self.headers.items()), self.rfile.read(length))
            self.send_response(response.status)
            for name, value in response.headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(response.body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(response.body)

        do_GET = _respond
        do_POST = _respond
        do_PUT = _respond
        do_PATCH = _respond
        do_DELETE = _respond
        do_HEAD = _respond

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    return Handler


def main() -> int:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), handler_for(Fleet()))
    print(f"Parallax demo fleet listening on 0.0.0.0:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
