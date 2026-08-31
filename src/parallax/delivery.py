"""Deliver a sweep's failing specs to the repository as a pull request.

A finding that stays in `runs/` is a report, and a report is work the person who
ran the sweep still has to do. This closes the loop the rest of the pipeline
opens: the specs the emitter already wrote are pushed to a branch and proposed
as a pull request, so a sweep that starts with a URL ends with a reviewable
change against the codebase.

Three properties matter more than convenience here, because this is the only
part of Parallax that writes anywhere except its own output directory:

* It never touches the base branch. Every delivery goes to its own branch named
  after the findings it carries, and the base is only ever read.
* It is idempotent. The branch name is derived from the finding ids, so the same
  defects re-delivered reuse the existing branch and return the open pull
  request instead of opening a second one.
* It is off unless asked. No token, no `--open-pr`, no findings: no delivery,
  and the report says which of those it was rather than staying silent.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .types import Finding, Severity


GITHUB_API = "https://api.github.com"

# A branch carries the findings of one sweep. Eight hex characters of a digest
# over the sorted finding ids is enough to separate concurrent sweeps of
# different applications while still colliding — deliberately — when the same
# defects are delivered twice.
_BRANCH_PREFIX = "parallax/findings"
_DIGEST_LENGTH = 8

# The emitter writes one spec per finding, and a sweep of a large application can
# produce many. A pull request that adds two hundred files is not reviewable, and
# the contents API costs one request per file, so delivery is capped and the
# report says how many were left behind.
MAX_SPECS_PER_PULL_REQUEST = 25

_SEVERITY_ORDER = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2, Severity.INFO: 3}


@dataclass
class DeliveryReport:
    """What delivery did, including every reason it did nothing."""

    enabled: bool = False
    attempted: bool = False
    delivered: bool = False
    branch: str | None = None
    pull_request_url: str | None = None
    already_open: bool = False
    specs_pushed: int = 0
    specs_skipped: int = 0
    note: str | None = None
    error: str | None = None

    def report(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "enabled": self.enabled,
            "attempted": self.attempted,
            "delivered": self.delivered,
            "specs_pushed": self.specs_pushed,
        }
        for key, value in (
            ("branch", self.branch),
            ("pull_request_url", self.pull_request_url),
            ("specs_skipped", self.specs_skipped or None),
            ("already_open", self.already_open or None),
            ("note", self.note),
            ("error", self.error),
        ):
            if value:
                payload[key] = value
        return payload


@dataclass
class GitHubTransport:
    """The narrow, injectable GitHub REST seam.

    The token is held here and never copied into a report, a feed event, or an
    exception message — an error from GitHub is re-raised with its status and
    body only.
    """

    token: str
    api: str = GITHUB_API
    _send: Callable[[str, str, dict[str, object] | None], Any] | None = field(default=None, repr=False)

    def request(self, method: str, path: str, payload: dict[str, object] | None = None) -> Any:
        if self._send is not None:
            return self._send(method, path, payload)
        request = Request(
            f"{self.api}{path}",
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "parallax",
            },
        )
        with urlopen(request, timeout=30) as response:  # noqa: S310 - api host is a constant
            body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


class PullRequestDelivery:
    """Push a sweep's specs to a branch and propose them."""

    def __init__(
        self,
        repository: str | None = None,
        *,
        base: str | None = None,
        token: str | None = None,
        transport: GitHubTransport | None = None,
    ) -> None:
        self.repository = repository or os.environ.get("PARALLAX_PR_REPOSITORY", "")
        self.base = base or os.environ.get("PARALLAX_PR_BASE", "")
        self._token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
        self._transport = transport

    def _unavailable(self) -> str | None:
        if not self.repository:
            return "no repository: set --open-pr owner/repo or PARALLAX_PR_REPOSITORY"
        if self.repository.count("/") != 1 or not all(self.repository.split("/")):
            return f"repository must be owner/repo, got {self.repository!r}"
        if not self._token and self._transport is None:
            return "no credentials: set GITHUB_TOKEN or GH_TOKEN"
        return None

    def deliver(
        self, findings: Sequence[Finding], spec_paths: Sequence[Path], *, run_url: str | None = None
    ) -> DeliveryReport:
        report = DeliveryReport(enabled=True)
        if (reason := self._unavailable()) is not None:
            report.note = reason
            return report
        if not findings or not spec_paths:
            # Delivering an empty pull request would train a reviewer to ignore
            # them, which is worse than delivering nothing.
            report.note = "no findings to deliver"
            return report

        report.attempted = True
        transport = self._transport or GitHubTransport(self._token)
        branch = branch_name(findings)
        report.branch = branch
        try:
            base = self.base or self._default_branch(transport)
            base_sha = self._branch_head(transport, base)
            self._ensure_branch(transport, branch, base_sha)
            pushed, skipped = self._push_specs(transport, branch, spec_paths)
            report.specs_pushed, report.specs_skipped = pushed, skipped
            url, existed = self._open_pull_request(transport, branch, base, findings, run_url)
            report.pull_request_url, report.already_open = url, existed
            report.delivered = True
        except HTTPError as error:
            report.error = f"github {error.code}: {_http_body(error)}"
        except Exception as error:  # noqa: BLE001 - a failed delivery must not fail the sweep
            report.error = f"{type(error).__name__}: {error}"
        return report

    def _default_branch(self, transport: GitHubTransport) -> str:
        repository = transport.request("GET", f"/repos/{self.repository}")
        return str(repository.get("default_branch") or "main")

    def _branch_head(self, transport: GitHubTransport, base: str) -> str:
        reference = transport.request("GET", f"/repos/{self.repository}/git/ref/heads/{base}")
        return str(reference["object"]["sha"])

    def _ensure_branch(self, transport: GitHubTransport, branch: str, base_sha: str) -> None:
        try:
            transport.request(
                "POST",
                f"/repos/{self.repository}/git/refs",
                {"ref": f"refs/heads/{branch}", "sha": base_sha},
            )
        except HTTPError as error:
            # 422 is GitHub's answer for a reference that already exists, which
            # is the ordinary path when the same findings are delivered twice.
            if error.code != 422:
                raise

    def _push_specs(
        self, transport: GitHubTransport, branch: str, spec_paths: Sequence[Path]
    ) -> tuple[int, int]:
        selected = list(spec_paths)[:MAX_SPECS_PER_PULL_REQUEST]
        skipped = len(spec_paths) - len(selected)
        pushed = 0
        for path in selected:
            target = f"tests/parallax/{path.name}"
            payload: dict[str, object] = {
                "message": f"test: {path.name}",
                "content": base64.b64encode(path.read_bytes()).decode("ascii"),
                "branch": branch,
            }
            if (sha := self._existing_blob(transport, target, branch)) is not None:
                payload["sha"] = sha
            transport.request("PUT", f"/repos/{self.repository}/contents/{target}", payload)
            pushed += 1
        return pushed, skipped

    def _existing_blob(self, transport: GitHubTransport, target: str, branch: str) -> str | None:
        """The contents API rejects an update that does not name the blob it replaces."""
        try:
            existing = transport.request(
                "GET", f"/repos/{self.repository}/contents/{target}?ref={branch}"
            )
        except HTTPError as error:
            if error.code == 404:
                return None
            raise
        sha = existing.get("sha") if isinstance(existing, dict) else None
        return str(sha) if sha else None

    def _open_pull_request(
        self,
        transport: GitHubTransport,
        branch: str,
        base: str,
        findings: Sequence[Finding],
        run_url: str | None,
    ) -> tuple[str | None, bool]:
        owner = self.repository.split("/")[0]
        try:
            created = transport.request(
                "POST",
                f"/repos/{self.repository}/pulls",
                {
                    "title": pull_request_title(findings),
                    "head": branch,
                    "base": base,
                    "body": pull_request_body(findings, run_url),
                },
            )
            return str(created.get("html_url") or "") or None, False
        except HTTPError as error:
            if error.code != 422:
                raise
        # 422 here means a pull request for this head already exists; returning
        # it is the useful answer, and opening a second one would be noise.
        existing = transport.request(
            "GET", f"/repos/{self.repository}/pulls?head={owner}:{branch}&state=open"
        )
        if isinstance(existing, list) and existing:
            return str(existing[0].get("html_url") or "") or None, True
        return None, True


def branch_name(findings: Sequence[Finding]) -> str:
    """Name the branch after the findings, so re-delivery is the same branch."""
    identity = "\n".join(sorted(finding.id for finding in findings))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]
    return f"{_BRANCH_PREFIX}-{digest}"


def pull_request_title(findings: Sequence[Finding]) -> str:
    count = len(findings)
    subject = "1 finding" if count == 1 else f"{count} findings"
    high = sum(1 for finding in findings if finding.severity is Severity.HIGH)
    if high:
        return f"Parallax: {subject}, {high} high severity"
    return f"Parallax: {subject}"


def pull_request_body(findings: Sequence[Finding], run_url: str | None) -> str:
    """Give the reviewer the evidence, not just the assertion."""
    ordered = sorted(findings, key=lambda f: (_SEVERITY_ORDER.get(f.severity, 9), f.id))
    lines = [
        "Opened by a Parallax sweep. Every spec below fails against the current "
        "deployment and is the finding it came from, expressed as a test.",
        "",
        "Each finding is a disagreement between browser contexts that differ by "
        "exactly one property, observed on the same commit — not a diff against "
        "a stored baseline.",
        "",
        "| severity | kind | axis | what disagreed | evidence |",
        "| --- | --- | --- | --- | --- |",
    ]
    for finding in ordered[:MAX_SPECS_PER_PULL_REQUEST]:
        lines.append(
            f"| {finding.severity.value} | {finding.kind.value} | {finding.axis.value} "
            f"| {_cell(finding.summary)} | {_cell(finding.evidence_line())} |"
        )
    if len(ordered) > MAX_SPECS_PER_PULL_REQUEST:
        lines.append("")
        lines.append(
            f"{len(ordered) - MAX_SPECS_PER_PULL_REQUEST} further findings were not "
            "included, so this pull request stays reviewable."
        )
    if run_url:
        lines += ["", f"Full evidence, including the witness mosaics: {run_url}"]
    return "\n".join(lines)


def _cell(text: str) -> str:
    """Keep a summary inside its table cell without changing its meaning."""
    flattened = " ".join(str(text).split()).replace("|", "\\|")
    return flattened if len(flattened) <= 160 else flattened[:157] + "..."


def _http_body(error: HTTPError) -> str:
    try:
        return error.read().decode("utf-8")[:200]
    except Exception:  # noqa: BLE001 - the status alone is still worth reporting
        return error.reason or ""
