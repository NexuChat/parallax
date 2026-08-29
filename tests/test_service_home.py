from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from wsgiref.util import setup_testing_defaults

from service.app import Application


def request(app: Application, method: str, path: str) -> tuple[str, dict[str, str], bytes]:
    environ: dict[str, Any] = {}
    setup_testing_defaults(environ)
    environ.update({"REQUEST_METHOD": method, "PATH_INFO": path, "wsgi.input": io.BytesIO()})
    captured: dict[str, Any] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(app(environ, start_response))
    return captured["status"], captured["headers"], body


def test_home_console_health_unknown_and_path_traversal_contract(tmp_path: Path) -> None:
    app = Application(runs_root=tmp_path / "runs")

    status, headers, body = request(app, "GET", "/")
    assert status == "200 OK"
    assert headers["Content-Type"].startswith("text/html")
    assert b"One eye sees no depth" in body

    status, headers, body = request(app, "GET", "/console")
    assert status == "200 OK"
    assert headers["Content-Type"].startswith("text/html")
    assert b"Live witness mosaic" in body
    assert b'<base href="/console/">' in body

    status, headers, _ = request(app, "GET", "/console/style.css")
    assert status == "200 OK"
    assert headers["Content-Type"].startswith("text/css")

    status, _, body = request(app, "GET", "/healthz")
    assert status == "200 OK"
    assert body == b'{"ok":true}\n'

    status, _, _ = request(app, "GET", "/not-a-page")
    assert status == "404 Not Found"

    status, _, _ = request(app, "GET", "/app.js")
    assert status == "404 Not Found"

    status, _, _ = request(app, "GET", "/console/../app.js")
    assert status == "404 Not Found"
