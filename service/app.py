"""A small WSGI service that starts and publishes Parallax sweeps."""

from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import threading
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from wsgiref.simple_server import make_server

try:  # Imported as a package on the box, as a sibling inside the container.
    from service.archive import RunArchive
except ImportError:  # pragma: no cover - container layout
    from archive import RunArchive


Response = tuple[str, list[tuple[str, str]], bytes]
Launcher = Callable[..., Any]


# The protocol the live page plays. Declared here rather than imported from the
# demo package so the service does not depend on the fixture fleet's source tree
# to answer a request about it.
_ARENA_PROTOCOL: dict[str, Any] = {
    "label": "invite, play, and win",
    "surface": "/game-legacy",
    "participants": [
        {"name": "amira", "surface": "/game-legacy?me=amira&vs=samir"},
        {"name": "samir", "surface": "/game-legacy?me=samir&vs=amira"},
    ],
    "steps": [
        {
            "label": "amira invites samir",
            "actor": "amira",
            "action": {"type": "click", "selector": "#send-invite"},
            "expect": [
                {"participant": "samir", "effect": {"type": "visible", "selector": "#accept"},
                 "note": "the invitation must reach its recipient"},
                {"participant": "amira", "effect": {"type": "visible", "selector": "#accept"},
                 "visible": False, "note": "and must not be offered to its sender"},
            ],
        },
        {
            "label": "samir accepts",
            "actor": "samir",
            "action": {"type": "click", "selector": "#accept"},
            "expect": [{"participant": "amira",
                        # Rendered text, not source text: the pill is uppercased by CSS, and
                        # what a player reads is what the promise is about.
                        "effect": {"type": "text_equals", "selector": "#status", "equals": "PLAYING"},
                        "note": "accepting starts the game for both players"}],
        },
        *(
            {
                "label": label,
                "actor": actor,
                "action": {"type": "click", "selector": f"#cell-{cell}"},
                "expect": [{"participant": watcher,
                            "effect": {"type": "text_equals", "selector": f"#cell-{cell}", "equals": mark},
                            "note": f"{actor}'s move must appear on {watcher}'s board"}],
            }
            for label, actor, cell, mark, watcher in (
                ("amira takes the centre", "amira", 4, "X", "samir"),
                ("samir takes a corner", "samir", 0, "O", "amira"),
                ("amira takes the left of the middle row", "amira", 3, "X", "samir"),
                ("samir takes the top", "samir", 1, "O", "amira"),
            )
        ),
        {
            "label": "amira completes the middle row and wins",
            "actor": "amira",
            "action": {"type": "click", "selector": "#cell-5"},
            "expect": [
                {"participant": "amira", "effect": {"type": "visible", "selector": "#winner"},
                 "note": "the winner is told they won"},
                {"participant": "samir", "effect": {"type": "visible", "selector": "#winner"},
                 "note": "and so is the player who lost"},
            ],
            "deadline_ms": 4000,
        },
    ],
}


def _tail(path: Path, limit: int = 2_000) -> str:
    """Return the end of a sweep log, which is where its diagnosis lands."""
    try:
        text = path.read_text(errors="replace").strip()
    except OSError:
        return ""
    return text[-limit:]


class Application:
    """Serve the public face, console, and isolate each sweep in a run directory."""

    def __init__(
        self,
        runs_root: Path | str = "/data/runs",
        console_root: Path | str | None = None,
        web_root: Path | str | None = None,
        launcher: Launcher = subprocess.Popen,
        archive: RunArchive | None = None,
    ) -> None:
        self.runs_root = Path(runs_root)
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.console_root = Path(console_root) if console_root else Path(__file__).resolve().parents[1] / "console"
        self.web_root = Path(web_root) if web_root else Path(__file__).resolve().parents[1] / "web"
        self.launcher = launcher
        self.runs: dict[str, dict[str, Any]] = {}
        self.protocols: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()
        # Completed runs are mirrored to a bucket so their links survive the
        # instance; without a configured bucket the mirror is a no-op.
        self.archive = archive if archive is not None else RunArchive(os.environ.get("PARALLAX_RUNS_BUCKET"))

    def __call__(self, environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        response = self.dispatch(environ)
        start_response(response[0], response[1])
        return [response[2]]

    def dispatch(self, environ: dict[str, Any]) -> Response:
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/")
        if path == "/healthz" and method == "GET":
            return self.json_response("200 OK", {"ok": True})
        if path == "/" and method == "GET":
            return self.file_response(self.web_root / "index.html")
        if path in {"/console", "/console/"} and method == "GET":
            return self.console_index_response()
        if path == "/protocol" or path.startswith("/protocol/"):
            return self.protocol_response(method, path)
        if path == "/runs" or path.startswith("/runs/"):
            return self.run_response(method, path, environ)
        if path.startswith("/console/") and method == "GET":
            return self.console_response(path.removeprefix("/console/"))
        if path.startswith("/") and method == "GET":
            return self.web_response(path)
        return self.not_found()

    def console_response(self, path: str) -> Response:
        relative = Path(path.lstrip("/"))
        if not self.safe_relative(relative):
            return self.not_found()
        return self.file_response(self.console_root / relative)

    def web_response(self, path: str) -> Response:
        relative = Path(path.lstrip("/"))
        if not self.safe_relative(relative):
            return self.not_found()
        return self.file_response(self.web_root / relative)

    def console_index_response(self) -> Response:
        """Serve /console with an explicit base so its relative assets stay mounted."""
        path = self.console_root / "index.html"
        if not path.is_file():
            return self.not_found()
        # The base must precede every relative URL in the document, so it goes
        # immediately after <head>. Appending it before </head> left the
        # stylesheet already resolved against /console — a 404, and a console
        # served with no styling at all.
        source = path.read_bytes()
        marker = b"<head>"
        index = source.find(marker)
        if index == -1:
            return self.not_found()
        cut = index + len(marker)
        body = source[:cut] + b'\n  <base href="/console/">' + source[cut:]
        # The CDN in front of this service enforces a four-hour browser cache from
        # a zone setting we do not want to change, so a redeployed console kept
        # running yesterday's JavaScript. Stamp the assets with the build's own
        # mtime: every deploy changes the URL, and nothing else has to.
        body = self.version_assets(body, self.console_root)
        return "200 OK", [("Content-Type", "text/html"), ("Content-Length", str(len(body)))], body

    @staticmethod
    def version_assets(body: bytes, root: Path) -> bytes:
        """Append each local asset's mtime to its reference, so a deploy busts the cache."""
        for name in ("app.js", "style.css", "home.js", "home.css"):
            asset = root / name
            if not asset.is_file():
                continue
            stamp = str(int(asset.stat().st_mtime)).encode()
            for quote in (b'"', b"'"):
                needle = quote + name.encode() + quote
                body = body.replace(needle, quote + name.encode() + b"?v=" + stamp + quote)
        return body

    def run_response(self, method: str, path: str, environ: dict[str, Any]) -> Response:
        parts = path.split("/")[2:]
        if path == "/runs" and method == "POST":
            return self.start_run(environ)
        if not parts or not parts[0] or not self.safe_relative(Path(*parts)):
            return self.not_found()
        run_id = parts[0]
        if len(parts) == 1 and method == "GET":
            return self.run_status(run_id)
        if len(parts) > 1 and method == "GET":
            return self.artifact_response(run_id, Path(*parts[1:]))
        return self.not_found()

    @staticmethod
    def safe_relative(path: Path) -> bool:
        return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)

    # ------------------------------------------------------------- protocol demo

    def protocol_response(self, method: str, path: str) -> Response:
        """Play the arena protocol with real sessions and report it step by step.

        This exists so the claim can be pressed rather than read. A visitor who
        is told that seven steps were verified from two live sessions has to
        take it on trust; a visitor who starts it and watches each step settle
        does not. The steps reported here are the choreography engine's own
        results — the same objects the graded gate judges — not a description
        of them.
        """
        parts = [part for part in path.strip("/").split("/") if part]
        if method == "POST" and len(parts) == 1:
            return self.start_protocol()
        if method == "GET" and len(parts) == 2:
            with self.lock:
                state = self.protocols.get(parts[1])
            if state is None:
                return self.not_found()
            return self.json_response("200 OK", state)
        return self.not_found()

    def start_protocol(self) -> Response:
        run_id = uuid.uuid4().hex
        with self.lock:
            self.protocols[run_id] = {"id": run_id, "status": "queued", "steps": [], "verdict": None, "error": None}
        threading.Thread(target=self.execute_protocol, args=(run_id,), daemon=True).start()
        return self.json_response("202 Accepted", {"id": run_id, "status": "queued"})

    def execute_protocol(self, run_id: str) -> None:
        import asyncio

        def record(**fields: Any) -> None:
            with self.lock:
                self.protocols[run_id].update(fields)

        def add_step(result: Any) -> None:
            expectations = []
            for expect in result.step.expect:
                broken = next((reason for spec, reason in result.violated if spec is expect), None)
                expectations.append({
                    "participant": expect.participant,
                    "wanted": "must see it" if expect.visible else "must not see it",
                    "observed": broken or ("as expected" if broken is None else broken),
                    "held": broken is None,
                    "note": expect.note,
                })
            with self.lock:
                self.protocols[run_id]["steps"].append({
                    "label": result.step.label,
                    "actor": result.step.actor,
                    "passed": result.passed,
                    "error": result.error,
                    "expectations": expectations,
                })

        async def play() -> None:
            from playwright.async_api import async_playwright

            from parallax.choreography import ChoreographyRun
            from parallax.choreography import judge as judge_choreography
            from parallax.__main__ import choreographies_from_data

            host = os.environ.get("PARALLAX_DEMO_HOST", "https://demo.mlki.app")
            declaration = json.loads(json.dumps(_ARENA_PROTOCOL))
            declaration["surface"] = f"{host}/arena{declaration['surface']}"
            for participant in declaration["participants"]:
                participant["surface"] = f"{host}/arena{participant['surface']}"
            [choreography] = choreographies_from_data({"choreographies": [declaration]}, host)

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                try:
                    # A fresh game, so a visitor never joins one somebody left
                    # half-played. The fixture resets on invite anyway; this is
                    # belt and braces for a page anyone can press twice.
                    context = await browser.new_context()
                    await context.request.post(f"{host}/arena/api/reset", data={})
                    await context.close()
                    record(status="playing")
                    outcome = await ChoreographyRun(browser, poll_ms=80).play(choreography, on_step=add_step)
                finally:
                    await browser.close()
            findings = judge_choreography(outcome)
            record(
                status="complete",
                verdict=findings[0].summary if findings else None,
                held=not findings,
            )

        try:
            asyncio.run(play())
        except Exception as error:  # noqa: BLE001 - reported to the page
            record(status="failed", error=f"{type(error).__name__}: {error}")

    def start_run(self, environ: dict[str, Any]) -> Response:
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
            body = json.loads(environ["wsgi.input"].read(length) or b"{}")
            url = body["url"]
            max_surfaces = body.get("max_surfaces", 12)
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                raise ValueError("url must be an http(s) URL")
            if not isinstance(max_surfaces, int) or isinstance(max_surfaces, bool) or max_surfaces < 1:
                raise ValueError("max_surfaces must be a positive integer")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            return self.json_response("400 Bad Request", {"error": str(error)})

        run_id = uuid.uuid4().hex
        output = self.runs_root / run_id
        output.mkdir()
        with self.lock:
            self.runs[run_id] = {"status": "queued", "url": url, "error": None}
        threading.Thread(target=self.execute_run, args=(run_id, url, max_surfaces, output), daemon=True).start()
        return self.json_response("202 Accepted", {"id": run_id, "status": "queued"})

    def execute_run(self, run_id: str, url: str, max_surfaces: int, output: Path) -> None:
        with self.lock:
            self.runs[run_id]["status"] = "running"
        command = [sys.executable, "-m", "parallax", url, "--out", str(output), "--max-surfaces", str(max_surfaces)]
        log_path = output / "sweep.log"
        try:
            # An exit status alone cannot be acted on. The sweep's own diagnosis —
            # the vision route it chose, the navigation that failed, the traceback —
            # goes to stderr, so keep it beside the run's other artifacts and carry
            # its last lines in the status a caller already polls.
            with log_path.open("wb") as log:
                process = self.launcher(command, stdout=log, stderr=subprocess.STDOUT)
                code = process.wait()
            with self.lock:
                self.runs[run_id]["status"] = "complete" if code == 0 else "failed"
                if code != 0:
                    self.runs[run_id]["error"] = f"sweep exited with status {code}"
                    self.runs[run_id]["log"] = _tail(log_path)
        except Exception as error:  # Keep failures observable without killing the HTTP server.
            with self.lock:
                self.runs[run_id].update(status="failed", error=str(error))
        # The run reached a final status either way; mirror what exists so the
        # visitor's saved link outlives this instance. Counts are computed now
        # because the mirror serves status without a feed on local disk.
        with self.lock:
            row = dict(self.runs[run_id])
        row.update(id=run_id, counts=self.counts(output / "feed.jsonl"), log=row.get("log", ""))
        self.archive.store(run_id, output, row)

    def run_status(self, run_id: str) -> Response:
        with self.lock:
            run = self.runs.get(run_id)
            details = dict(run) if run else None
        if details is None:
            # This instance never ran it, but a previous one may have finished
            # and mirrored it; a saved link should not depend on which is which.
            archived = self.archive.meta(run_id)
            if archived is None:
                return self.not_found()
            return self.json_response("200 OK", archived)
        return self.json_response("200 OK", {
            "id": run_id,
            "status": details["status"],
            "url": details["url"],
            "counts": self.counts(self.runs_root / run_id / "feed.jsonl"),
            "error": details["error"],
            "log": details.get("log", ""),
        })

    @staticmethod
    def counts(feed: Path) -> dict[str, int]:
        counts = {"mosaics": 0, "findings": 0}
        if not feed.is_file():
            return counts
        for line in feed.read_text(errors="replace").splitlines():
            try:
                kind = json.loads(line).get("kind")
            except json.JSONDecodeError:
                continue
            if kind == "mosaic":
                counts["mosaics"] += 1
            elif kind == "finding":
                counts["findings"] += 1
        return counts

    def artifact_response(self, run_id: str, relative: Path) -> Response:
        if not self.safe_relative(relative):
            return self.not_found()
        with self.lock:
            exists = run_id in self.runs
        if exists:
            return self.file_response(self.runs_root / run_id / relative)
        body = self.archive.fetch(run_id, relative.as_posix())
        if body is None:
            return self.not_found()
        content_type = mimetypes.guess_type(relative.name)[0] or (
            "application/x-ndjson" if relative.name == "feed.jsonl" else "application/octet-stream"
        )
        return "200 OK", [
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-cache, must-revalidate"),
        ], body

    @staticmethod
    def file_response(path: Path) -> Response:
        if not path.is_file():
            return Application.not_found()
        if path.name == "feed.jsonl":
            content_type = "application/x-ndjson"
        elif path.name == "graded-summary.json":
            content_type = "application/json"
        else:
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        # Everything this service serves is either a live run's output or a page
        # that changes between takes. Behind a CDN the default was a four-hour
        # cache, so a fix deployed during a demo would not appear until long
        # after the demo ended.
        return "200 OK", [
            ("Content-Type", content_type),
            ("Content-Length", str(path.stat().st_size)),
            ("Cache-Control", "no-cache, must-revalidate"),
        ], path.read_bytes()

    @staticmethod
    def json_response(status: str, payload: dict[str, Any]) -> Response:
        body = json.dumps(payload, separators=(",", ":")).encode() + b"\n"
        return status, [("Content-Type", "application/json"), ("Content-Length", str(len(body)))], body

    @staticmethod
    def not_found() -> Response:
        return "404 Not Found", [("Content-Type", "text/plain")], b"not found\n"


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    # /data is where the container mounts its writable volume; anywhere else —
    # a developer's laptop, a systemd unit on a host — needs to say so rather
    # than crash on a path it was never going to be allowed to create.
    runs_root = os.environ.get("PARALLAX_RUNS_ROOT", "/data/runs")
    with make_server("0.0.0.0", port, Application(runs_root=runs_root)) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
