"""Completed runs outlive the instance that produced them.

The service keeps its live registry in one instance's memory on purpose —
that decision and its cost are written beside the deploy flags. What was not
acceptable was the second half of the cost falling on a visitor: a sweep
finished at night, its link saved, and the morning instance answering
``unknown run`` because Cloud Run's filesystem is memory. So a run that
reaches a final status is mirrored, file by file, into a Cloud Storage
bucket, and both the status route and the artifact route read through to
that mirror when their own instance has never heard of the run.

Deliberately small: the Google Cloud Storage JSON API over urllib with a
token from the metadata server, because a dependency added ninety minutes
before a deadline is how working services stop working. Without a bucket
name in the environment the archive is disabled and every call is a no-op,
which is what keeps local development and the test suite off the network.
Archiving is best-effort by construction — a mirror that could fail a sweep
would cost more than the restarts it guards against.
"""

from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

Opener = Callable[..., Any]

_METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)
_STORAGE = "https://storage.googleapis.com"
_META_NAME = "_meta.json"


class RunArchive:
    """Mirror finished run directories to a bucket and read them back on a miss."""

    def __init__(self, bucket: str | None, opener: Opener = urllib.request.urlopen) -> None:
        self.bucket = bucket or None
        self.opener = opener
        self._token: str | None = None
        self._token_expiry = 0.0

    @property
    def enabled(self) -> bool:
        return self.bucket is not None

    # ------------------------------------------------------------------ token

    def token(self) -> str | None:
        if not self.enabled:
            return None
        if self._token and time.time() < self._token_expiry:
            return self._token
        request = urllib.request.Request(_METADATA_TOKEN_URL, headers={"Metadata-Flavor": "Google"})
        try:
            with self.opener(request, timeout=5) as response:
                grant = json.load(response)
        except (urllib.error.URLError, OSError, ValueError):
            # Off Google Cloud there is no metadata server; a bucket configured
            # there is a misconfiguration the service should survive, not serve.
            return None
        self._token = grant.get("access_token")
        self._token_expiry = time.time() + float(grant.get("expires_in", 0)) - 60
        return self._token

    # ------------------------------------------------------------------ write

    def store(self, run_id: str, directory: Path, meta: dict[str, Any]) -> None:
        """Mirror one finished run. Never raises: the run already happened."""
        token = self.token()
        if token is None:
            return
        try:
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    relative = path.relative_to(directory).as_posix()
                    self._put(token, f"runs/{run_id}/{relative}", path.read_bytes(),
                              mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            body = json.dumps(meta, separators=(",", ":")).encode()
            self._put(token, f"runs/{run_id}/{_META_NAME}", body, "application/json")
        except (urllib.error.URLError, OSError, ValueError):
            return

    def _put(self, token: str, name: str, body: bytes, content_type: str) -> None:
        query = urllib.parse.urlencode({"uploadType": "media", "name": name})
        request = urllib.request.Request(
            f"{_STORAGE}/upload/storage/v1/b/{self.bucket}/o?{query}",
            data=body,
            method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": content_type},
        )
        with self.opener(request, timeout=30) as response:
            response.read()

    # ------------------------------------------------------------------- read

    def fetch(self, run_id: str, relative: str) -> bytes | None:
        token = self.token()
        if token is None:
            return None
        name = urllib.parse.quote(f"runs/{run_id}/{relative}", safe="")
        request = urllib.request.Request(
            f"{_STORAGE}/storage/v1/b/{self.bucket}/o/{name}?alt=media",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            with self.opener(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            return None
        except (urllib.error.URLError, OSError):
            return None

    def meta(self, run_id: str) -> dict[str, Any] | None:
        body = self.fetch(run_id, _META_NAME)
        if body is None:
            return None
        try:
            found = json.loads(body)
        except ValueError:
            return None
        return found if isinstance(found, dict) else None
