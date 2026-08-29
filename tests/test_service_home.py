from __future__ import annotations

import io
import re
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
    source_console = Path(__file__).resolve().parents[1] / "console"
    console = tmp_path / "console"
    (console / "runs").mkdir(parents=True)
    for name in ("index.html", "style.css"):
        (console / name).write_bytes((source_console / name).read_bytes())
    (console / "runs" / "index.json").write_text('{"workspace":{}}', encoding="utf-8")
    app = Application(runs_root=tmp_path / "runs", console_root=console)

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

    status, headers, body = request(app, "GET", "/console/runs/index.json")
    assert status == "200 OK"
    assert headers["Content-Type"].startswith("application/json")
    assert b'"workspace"' in body

    status, _, body = request(app, "GET", "/healthz")
    assert status == "200 OK"
    assert body == b'{"ok":true}\n'

    status, _, _ = request(app, "GET", "/not-a-page")
    assert status == "404 Not Found"

    status, _, _ = request(app, "GET", "/app.js")
    assert status == "404 Not Found"

    status, _, _ = request(app, "GET", "/console/../app.js")
    assert status == "404 Not Found"


def test_graded_summary_is_json_when_present_and_404_when_absent(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    app = Application(runs_root=tmp_path / "runs", web_root=web)

    status, _, _ = request(app, "GET", "/graded-summary.json")
    assert status == "404 Not Found"

    (web / "graded-summary.json").write_text('{"sites":{}}', encoding="utf-8")
    status, headers, body = request(app, "GET", "/graded-summary.json")
    assert status == "200 OK"
    assert headers["Content-Type"].startswith("application/json")
    assert body == b'{"sites":{}}'


def test_home_html_references_only_served_assets(tmp_path: Path) -> None:
    source_web = Path(__file__).resolve().parents[1] / "web"
    app = Application(runs_root=tmp_path / "runs", web_root=source_web)

    status, headers, body = request(app, "GET", "/")
    assert status == "200 OK"
    assert headers["Content-Type"].startswith("text/html")
    assert b'/style.css' not in body
    assert b'/favicon.ico' not in body
    script = (source_web / "home.js").read_text(encoding="utf-8")
    assert "/graded-summary.json" in script
    assert "control" in script
    assert "Control result unavailable" in script
    assert "/console/runs/index.json" in script
    assert "new URLSearchParams(location.search).get('app')" in script
    assert "entries.find((entry) => entry.name === 'workspace')" in script
    assert "|| entries[0]" in script
    assets = re.findall(r'(?:href|src)="(/[^"?#]+)', body.decode())
    for asset in assets:
        status, _, _ = request(app, "GET", asset)
        assert status == "200 OK", asset
    status, _, _ = request(app, "GET", "/generated-example.spec.ts")
    assert status == "200 OK"


def test_home_renders_when_graded_summary_is_unavailable(tmp_path: Path) -> None:
    source_web = Path(__file__).resolve().parents[1] / "web"
    web = tmp_path / "web"
    web.mkdir()
    for name in ("index.html", "home.css", "home.js", "generated-example.spec.ts"):
        (web / name).write_bytes((source_web / name).read_bytes())
    app = Application(runs_root=tmp_path / "runs", web_root=web)

    status, headers, body = request(app, "GET", "/")
    assert status == "200 OK"
    assert headers["Content-Type"].startswith("text/html")
    assert b"Measured control" in body

    status, _, _ = request(app, "GET", "/graded-summary.json")
    assert status == "404 Not Found"
