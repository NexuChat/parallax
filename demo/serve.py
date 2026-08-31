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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit


DEMO_DIR = Path(__file__).resolve().parent
if str(DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(DEMO_DIR))

from sites.base import Request, Response, Site  # noqa: E402

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
        links = "".join(
            f'<li><a href="/{site.name}/">{site.title}</a> <small>/{site.name}/</small></li>'
            for site in self.sites.values()
        ) or "<li>No demo sites are available yet.</li>"
        return Response.html(f"<!doctype html><title>Parallax demo fleet</title><h1>Parallax demo fleet</h1><ul>{links}</ul>")


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
