from __future__ import annotations

import io
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from wsgiref.util import setup_testing_defaults

from service.app import Application


class FakeProcess:
    def __init__(self, release: threading.Event) -> None:
        self.release = release
        self.returncode: int | None = None

    def wait(self) -> int:
        self.release.wait(timeout=2)
        self.returncode = 0
        return self.returncode


def request(
    app: Application, method: str, path: str, body: dict[str, Any] | None = None
) -> tuple[str, dict[str, str], bytes]:
    environ: dict[str, Any] = {}
    setup_testing_defaults(environ)
    payload = json.dumps(body).encode() if body is not None else b""
    environ.update({
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_LENGTH": str(len(payload)),
        "wsgi.input": io.BytesIO(payload),
    })
    captured: dict[str, Any] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = dict(headers)

    response_body = b"".join(app(environ, start_response))
    return captured["status"], captured["headers"], response_body


def make_app(tmp_path: Path) -> tuple[Application, threading.Event]:
    release = threading.Event()

    def launch(_command: list[str]) -> FakeProcess:
        return FakeProcess(release)

    return Application(runs_root=tmp_path / "runs", launcher=launch), release


def test_console_health_and_unknown_path(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)

    status, headers, body = request(app, "GET", "/")
    assert status == "200 OK"
    assert headers["Content-Type"].startswith("text/html")
    assert b"PARALLAX" in body

    status, _, body = request(app, "GET", "/healthz")
    assert status == "200 OK"
    assert body == b'{"ok":true}\n'

    status, _, _ = request(app, "GET", "/missing")
    assert status == "404 Not Found"


def test_start_is_immediate_and_status_and_feed_are_available(tmp_path: Path) -> None:
    app, release = make_app(tmp_path)

    status, _, body = request(app, "POST", "/runs", {"url": "https://example.test", "max_surfaces": 3})
    assert status == "202 Accepted"
    run_id = json.loads(body)["id"]
    assert run_id

    run_dir = tmp_path / "runs" / run_id
    feed = run_dir / "feed.jsonl"
    feed.write_text('{"kind":"mosaic","payload":{}}\n{"kind":"finding","payload":{}}\n')
    status, _, body = request(app, "GET", f"/runs/{run_id}")
    payload = json.loads(body)
    assert status == "200 OK"
    assert payload["status"] in {"queued", "running"}
    assert payload["counts"] == {"mosaics": 1, "findings": 1}

    status, headers, body = request(app, "GET", f"/runs/{run_id}/feed.jsonl")
    assert status == "200 OK"
    assert headers["Content-Type"] == "application/x-ndjson"
    assert body == feed.read_bytes()
    release.set()


def test_artifact_path_traversal_is_refused(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    status, _, _ = request(app, "GET", "/runs/../feed.jsonl")
    assert status == "404 Not Found"
