"""The mirror that lets a finished run outlive its instance.

The live registry dies with the instance by design; what these tests pin is
the promise made on top of that: a run that reached a final status can be
read back — status, feed, and images — by an instance that never ran it,
and a configured mirror that cannot reach its bucket degrades to exactly
the behaviour of having no mirror at all.
"""

from __future__ import annotations

import io
import json
import threading
import time
import urllib.error
import urllib.parse
from pathlib import Path

from service.app import Application
from service.archive import RunArchive

from tests.test_service import FakeProcess, request


class _Reply(io.BytesIO):
    def __enter__(self) -> _Reply:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


class FakeCloud:
    """Metadata server and bucket in one callable, standing in for urlopen."""

    def __init__(self, fail_token: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_token = fail_token

    def __call__(self, request_: urllib.request.Request, timeout: float | None = None) -> _Reply:
        url = request_.full_url
        if "metadata.google.internal" in url:
            if self.fail_token:
                raise urllib.error.URLError("no metadata server here")
            return _Reply(json.dumps({"access_token": "token", "expires_in": 3600}).encode())
        assert request_.get_header("Authorization") == "Bearer token"
        if "/upload/storage/v1/" in url:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            self.objects[query["name"][0]] = request_.data or b""
            return _Reply(b"{}")
        name = urllib.parse.unquote(urllib.parse.urlsplit(url).path.split("/o/", 1)[1])
        if name not in self.objects:
            raise urllib.error.HTTPError(url, 404, "not found", None, io.BytesIO(b""))
        return _Reply(self.objects[name])


def make_app(tmp_path: Path, name: str, archive: RunArchive) -> tuple[Application, threading.Event]:
    release = threading.Event()

    def launch(_command: list[str], **_streams: object) -> FakeProcess:
        return FakeProcess(release)

    app = Application(runs_root=tmp_path / name, launcher=launch, archive=archive)
    return app, release


def wait_for(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "mirror never appeared"
        time.sleep(0.01)


def test_completed_run_outlives_the_instance(tmp_path: Path) -> None:
    cloud = FakeCloud()
    first, release = make_app(tmp_path, "first", RunArchive("bucket", opener=cloud))

    _, _, body = request(first, "POST", "/runs", {"url": "https://example.test", "max_surfaces": 1})
    run_id = json.loads(body)["id"]
    run_dir = tmp_path / "first" / run_id
    (run_dir / "mosaics").mkdir()
    feed = '{"kind":"mosaic","payload":{}}\n{"kind":"finding","payload":{}}\n'
    (run_dir / "feed.jsonl").write_text(feed)
    (run_dir / "mosaics" / "wall.jpg").write_bytes(b"jpeg-bytes")
    release.set()
    wait_for(lambda: f"runs/{run_id}/_meta.json" in cloud.objects)

    # A different instance: fresh registry, fresh run directory, same bucket.
    second, _ = make_app(tmp_path, "second", RunArchive("bucket", opener=cloud))

    status, _, body = request(second, "GET", f"/runs/{run_id}")
    payload = json.loads(body)
    assert status == "200 OK"
    assert payload["status"] == "complete"
    assert payload["counts"] == {"mosaics": 1, "findings": 1}

    status, headers, body = request(second, "GET", f"/runs/{run_id}/feed.jsonl")
    assert status == "200 OK"
    assert body.decode() == feed

    status, headers, body = request(second, "GET", f"/runs/{run_id}/mosaics/wall.jpg")
    assert status == "200 OK"
    assert headers["Content-Type"] == "image/jpeg"
    assert body == b"jpeg-bytes"


def test_missing_run_is_a_miss_on_both_planes(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path, "only", RunArchive("bucket", opener=FakeCloud()))
    status, _, _ = request(app, "GET", "/runs/0000feed0000")
    assert status == "404 Not Found"
    status, _, _ = request(app, "GET", "/runs/0000feed0000/feed.jsonl")
    assert status == "404 Not Found"


def test_unreachable_bucket_degrades_to_no_mirror(tmp_path: Path) -> None:
    cloud = FakeCloud(fail_token=True)
    app, release = make_app(tmp_path, "dark", RunArchive("bucket", opener=cloud))

    _, _, body = request(app, "POST", "/runs", {"url": "https://example.test", "max_surfaces": 1})
    run_id = json.loads(body)["id"]
    release.set()
    wait_for(lambda: json.loads(request(app, "GET", f"/runs/{run_id}")[2])["status"] == "complete")

    assert cloud.objects == {}
    status, _, _ = request(app, "GET", "/runs/someone-elses-run")
    assert status == "404 Not Found"


def test_archived_reads_still_refuse_traversal(tmp_path: Path) -> None:
    cloud = FakeCloud()
    cloud.objects["runs/x/../../secret"] = b"never served"
    app, _ = make_app(tmp_path, "safe", RunArchive("bucket", opener=cloud))
    status, _, _ = request(app, "GET", "/runs/x/../../secret")
    assert status == "404 Not Found"
