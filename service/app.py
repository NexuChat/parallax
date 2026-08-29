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


Response = tuple[str, list[tuple[str, str]], bytes]
Launcher = Callable[[list[str]], Any]


class Application:
    """Serve the console and isolate each long-running sweep in a run directory."""

    def __init__(
        self,
        runs_root: Path | str = "/data/runs",
        console_root: Path | str | None = None,
        launcher: Launcher = subprocess.Popen,
    ) -> None:
        self.runs_root = Path(runs_root)
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.console_root = Path(console_root) if console_root else Path(__file__).resolve().parents[1] / "console"
        self.launcher = launcher
        self.runs: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()

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
            return self.file_response(self.console_root / "index.html")
        if path == "/runs" or path.startswith("/runs/"):
            return self.run_response(method, path, environ)
        if path.startswith("/") and method == "GET":
            return self.console_response(path)
        return self.not_found()

    def console_response(self, path: str) -> Response:
        relative = Path(path.lstrip("/"))
        if not self.safe_relative(relative):
            return self.not_found()
        return self.file_response(self.console_root / relative)

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
        try:
            process = self.launcher(command)
            code = process.wait()
            with self.lock:
                self.runs[run_id]["status"] = "complete" if code == 0 else "failed"
                if code != 0:
                    self.runs[run_id]["error"] = f"sweep exited with status {code}"
        except Exception as error:  # Keep failures observable without killing the HTTP server.
            with self.lock:
                self.runs[run_id].update(status="failed", error=str(error))

    def run_status(self, run_id: str) -> Response:
        with self.lock:
            run = self.runs.get(run_id)
            details = dict(run) if run else None
        if details is None:
            return self.not_found()
        return self.json_response("200 OK", {
            "id": run_id,
            "status": details["status"],
            "url": details["url"],
            "counts": self.counts(self.runs_root / run_id / "feed.jsonl"),
            "error": details["error"],
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
        with self.lock:
            exists = run_id in self.runs
        if not exists or not self.safe_relative(relative):
            return self.not_found()
        return self.file_response(self.runs_root / run_id / relative)

    @staticmethod
    def file_response(path: Path) -> Response:
        if not path.is_file():
            return Application.not_found()
        content_type = "application/x-ndjson" if path.name == "feed.jsonl" else mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return "200 OK", [("Content-Type", content_type), ("Content-Length", str(path.stat().st_size))], path.read_bytes()

    @staticmethod
    def json_response(status: str, payload: dict[str, Any]) -> Response:
        body = json.dumps(payload, separators=(",", ":")).encode() + b"\n"
        return status, [("Content-Type", "application/json"), ("Content-Length", str(len(body)))], body

    @staticmethod
    def not_found() -> Response:
        return "404 Not Found", [("Content-Type", "text/plain")], b"not found\n"


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    with make_server("0.0.0.0", port, Application()) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
