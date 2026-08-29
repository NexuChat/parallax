from __future__ import annotations

import serve
from sites.base import Planted, Request, Response
from parallax.types import Axis, Finding, FindingKind, Severity, Surface, SurfaceKind
from scripts import run_demo_suite


class StubSite:
    name = "stub"
    title = "Stub fleet member"
    planted: list[Planted] = []

    def __init__(self) -> None:
        self.requests: list[Request] = []

    def handle(self, request: Request) -> Response:
        self.requests.append(request)
        if request.path == "/go":
            return Response.redirect("/stub/done")
        return Response.html("stub response")


def test_fleet_mounts_stub_and_translates_requests() -> None:
    site = StubSite()
    fleet = serve.Fleet([site])

    response = fleet.dispatch(
        "GET", "/stub/tasks?lang=ar&theme=dark", {"X-Trace": "yes", "Cookie": "role=owner; lang=en"}, b""
    )

    assert response.status == 200
    assert site.requests == [
        Request(
            method="GET",
            path="/tasks",
            query={"lang": "ar", "theme": "dark"},
            cookies={"role": "owner", "lang": "en"},
            headers={"x-trace": "yes", "cookie": "role=owner; lang=en"},
            body=b"",
        )
    ]


def test_fleet_translates_redirect_and_front_door() -> None:
    fleet = serve.Fleet([StubSite()])

    redirect = fleet.dispatch("GET", "/stub/go", {}, b"")
    front_door = fleet.dispatch("GET", "/", {}, b"")

    assert redirect.status == 302
    assert redirect.headers["Location"] == "/stub/done"
    assert b'href="/stub/"' in front_door.body


def test_fleet_rejects_unknown_and_parent_paths_and_answers_healthz() -> None:
    fleet = serve.Fleet([StubSite()])

    assert fleet.dispatch("GET", "/missing/", {}, b"").status == 404
    assert fleet.dispatch("GET", "/stub/../secret", {}, b"").status == 404
    assert fleet.dispatch("GET", "/healthz", {}, b"").status == 200


def finding(kind: FindingKind, axis: Axis, url: str, *, defect: str | None = None) -> Finding:
    testimony = type("Testimony", (), {"defects": [defect] if defect else []})()
    return Finding(kind, Severity.HIGH, Surface(SurfaceKind.ROUTE, url), axis, "test", [testimony])


def test_grader_buckets_found_missed_and_false_positive_and_exit_code() -> None:
    plants = [
        Planted("escalation", "privilege", "/billing", "found"),
        Planted("low_contrast", "theme", "/settings", "missed"),
    ]
    findings = [
        finding(FindingKind.ESCALATION, Axis.PRIVILEGE, "http://demo.test/stub/billing"),
        finding(FindingKind.DEAD_SURFACE, Axis.BASELINE, "http://demo.test/stub/elsewhere"),
    ]

    grade = run_demo_suite.grade_findings(findings, plants, site_name="stub")

    assert [plant.note for plant in grade.found] == ["found"]
    assert [plant.note for plant in grade.missed] == ["missed"]
    assert grade.false_positives == [findings[1]]
    assert run_demo_suite.exit_code({"stub": grade}) == 1
    assert run_demo_suite.exit_code({"stub": run_demo_suite.grade_findings([], [])}) == 0
