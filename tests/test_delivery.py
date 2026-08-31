from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from parallax.delivery import (
    MAX_SPECS_PER_PULL_REQUEST,
    DeliveryReport,
    GitHubTransport,
    PullRequestDelivery,
    branch_name,
    pull_request_body,
    pull_request_title,
)
from parallax.types import (
    Axis,
    Context,
    Finding,
    FindingKind,
    Outcome,
    Severity,
    Surface,
    SurfaceKind,
)
# Aliased: pytest tries to collect any imported name starting with "Test".
from parallax.types import Testimony as WitnessTestimony


BASELINE = Context(varies=Axis.BASELINE)


def finding(summary: str = "the cart overflows", severity: Severity = Severity.HIGH) -> Finding:
    return Finding(
        kind=FindingKind.RENDER_DEFECT,
        severity=severity,
        surface=Surface(SurfaceKind.ROUTE, f"https://app.example/{summary.split()[1]}"),
        axis=Axis.VIEWPORT,
        summary=summary,
        testimonies=[WitnessTestimony(Surface(SurfaceKind.ROUTE, "https://app.example/"), BASELINE, Outcome.REACHED)],
        evidence="owner-en-light-mobile=partial",
    )


def spec(tmp_path: Path, name: str = "parallax-render-viewport-abc.spec.ts") -> Path:
    path = tmp_path / name
    path.write_text("test('fails', async () => { expect(1).toBe(2) })", encoding="utf-8")
    return path


class FakeGitHub:
    """Record every call so the guarantees can be asserted, not assumed."""

    def __init__(self, *, existing_branch: bool = False, existing_pr: bool = False) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.existing_branch = existing_branch
        self.existing_pr = existing_pr

    def transport(self) -> GitHubTransport:
        return GitHubTransport(token="never-read", _send=self)

    def __call__(self, method: str, path: str, payload: dict | None) -> object:
        self.calls.append((method, path, payload))
        if method == "GET" and path.endswith("/repos/acme/app"):
            return {"default_branch": "main"}
        if method == "GET" and "/git/ref/heads/" in path:
            return {"object": {"sha": "basesha"}}
        if method == "POST" and path.endswith("/git/refs"):
            if self.existing_branch:
                raise HTTPError(path, 422, "Reference already exists", {}, None)
            return {"ref": payload["ref"] if payload else ""}
        if method == "GET" and "/contents/" in path:
            raise HTTPError(path, 404, "Not Found", {}, None)
        if method == "PUT" and "/contents/" in path:
            return {"content": {"path": path}}
        if method == "POST" and path.endswith("/pulls"):
            if self.existing_pr:
                raise HTTPError(path, 422, "already exists", {}, None)
            return {"html_url": "https://github.com/acme/app/pull/7"}
        if method == "GET" and "/pulls?head=" in path:
            return [{"html_url": "https://github.com/acme/app/pull/3"}] if self.existing_pr else []
        raise AssertionError(f"unexpected call: {method} {path}")

    def paths(self, method: str) -> list[str]:
        return [path for verb, path, _ in self.calls if verb == method]


def test_delivery_is_off_until_it_is_asked_for() -> None:
    assert DeliveryReport(note="not requested").report() == {
        "enabled": False,
        "attempted": False,
        "delivered": False,
        "specs_pushed": 0,
        "note": "not requested",
    }


def test_missing_credentials_are_named_rather_than_silently_skipped(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    report = PullRequestDelivery("acme/app").deliver([finding()], [spec(tmp_path)])

    assert report.attempted is False
    assert report.note is not None and "GITHUB_TOKEN" in report.note


def test_a_malformed_repository_is_refused_before_any_request(tmp_path) -> None:
    github = FakeGitHub()
    report = PullRequestDelivery("not-a-repo", transport=github.transport()).deliver(
        [finding()], [spec(tmp_path)]
    )

    assert report.attempted is False
    assert github.calls == []


def test_a_sweep_with_no_findings_opens_nothing(tmp_path) -> None:
    """An empty pull request teaches a reviewer to ignore the next one."""
    github = FakeGitHub()
    report = PullRequestDelivery("acme/app", transport=github.transport()).deliver([], [])

    assert report.delivered is False
    assert report.note == "no findings to deliver"
    assert github.calls == []


def test_specs_are_pushed_to_a_branch_and_proposed(tmp_path) -> None:
    github = FakeGitHub()
    report = PullRequestDelivery("acme/app", transport=github.transport()).deliver(
        [finding()], [spec(tmp_path)], run_url="https://perallax.mlki.app"
    )

    assert report.delivered is True
    assert report.specs_pushed == 1
    assert report.pull_request_url == "https://github.com/acme/app/pull/7"
    assert report.already_open is False
    created = [payload for verb, path, payload in github.calls if path.endswith("/git/refs")]
    assert created and created[0]["ref"] == f"refs/heads/{report.branch}"


def test_the_base_branch_is_read_and_never_written(tmp_path) -> None:
    """The one hard guarantee: delivery cannot commit to the branch it targets."""
    github = FakeGitHub()
    delivery = PullRequestDelivery("acme/app", transport=github.transport())

    report = delivery.deliver([finding()], [spec(tmp_path)])

    assert report.branch is not None and report.branch.startswith("parallax/findings-")
    for verb, path, payload in github.calls:
        if verb in {"PUT", "POST"} and payload:
            assert payload.get("branch", report.branch) == report.branch
            assert payload.get("ref", "") != "refs/heads/main"
    assert "main" not in {payload.get("branch") for _, _, payload in github.calls if payload}


def test_redelivering_the_same_findings_reuses_the_branch_and_the_pull_request(tmp_path) -> None:
    github = FakeGitHub(existing_branch=True, existing_pr=True)

    report = PullRequestDelivery("acme/app", transport=github.transport()).deliver(
        [finding()], [spec(tmp_path)]
    )

    assert report.delivered is True
    assert report.already_open is True
    assert report.pull_request_url == "https://github.com/acme/app/pull/3"


def test_the_branch_name_is_the_findings_it_carries() -> None:
    one, two = finding("the cart overflows"), finding("the header clips")

    assert branch_name([one, two]) == branch_name([two, one])
    assert branch_name([one]) != branch_name([one, two])


def test_a_large_sweep_stays_reviewable(tmp_path) -> None:
    github = FakeGitHub()
    findings = [finding(f"the row{index} overflows") for index in range(MAX_SPECS_PER_PULL_REQUEST + 4)]
    specs = [spec(tmp_path, f"parallax-{index}.spec.ts") for index in range(len(findings))]

    report = PullRequestDelivery("acme/app", transport=github.transport()).deliver(findings, specs)

    assert report.specs_pushed == MAX_SPECS_PER_PULL_REQUEST
    assert report.specs_skipped == 4
    assert len(github.paths("PUT")) == MAX_SPECS_PER_PULL_REQUEST


def test_a_github_failure_is_reported_and_never_raised(tmp_path) -> None:
    """A sweep that found real defects must not be lost because delivery failed."""

    def explode(method: str, path: str, payload: dict | None) -> object:
        raise HTTPError(path, 503, "unavailable", {}, None)

    transport = GitHubTransport(token="never-read", _send=explode)
    report = PullRequestDelivery("acme/app", transport=transport).deliver([finding()], [spec(tmp_path)])

    assert report.delivered is False
    assert report.error is not None and "503" in report.error


def test_the_token_never_reaches_the_report(tmp_path) -> None:
    def explode(method: str, path: str, payload: dict | None) -> object:
        raise RuntimeError("boom")

    transport = GitHubTransport(token="ghp_supersecret", _send=explode)
    report = PullRequestDelivery("acme/app", transport=transport).deliver([finding()], [spec(tmp_path)])

    assert "ghp_supersecret" not in json.dumps(report.report())


def test_the_body_carries_the_evidence_and_orders_by_severity() -> None:
    body = pull_request_body(
        [finding("the footer clips", Severity.LOW), finding("the cart overflows", Severity.HIGH)],
        run_url="https://perallax.mlki.app",
    )

    assert body.index("the cart") < body.index("the footer")
    assert "owner-en-light-mobile=partial" in body
    assert "https://perallax.mlki.app" in body


def test_a_pipe_in_a_summary_cannot_break_the_table() -> None:
    body = pull_request_body([finding("the a|b column overflows")], run_url=None)

    assert "a\\|b" in body


def test_one_finding_is_not_announced_as_findings() -> None:
    assert pull_request_title([finding()]) == "Parallax: 1 finding, 1 high severity"
    assert pull_request_title([finding(severity=Severity.LOW)]) == "Parallax: 1 finding"
    assert "2 findings" in pull_request_title([finding(), finding("the header clips")])
