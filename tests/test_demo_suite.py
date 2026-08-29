from __future__ import annotations

import json
from urllib.parse import parse_qs

from parallax.types import Axis, Finding, FindingKind, Severity, Surface, SurfaceKind
from scripts import run_demo_suite
from sites.base import Account, Planted


def finding(kind: FindingKind, axis: Axis, url: str) -> Finding:
    return Finding(kind, Severity.HIGH, Surface(SurfaceKind.ROUTE, url), axis, "test", [])


def test_template_route_matches_a_concrete_url_under_a_site_mount() -> None:
    plant = Planted("render", "baseline", "/product/<id>", "product")
    grade = run_demo_suite.grade_findings(
        [finding(FindingKind.RENDER_DEFECT, Axis.BASELINE, "http://127.0.0.1:8099/shop/product/ledger")],
        [plant],
        site_name="shop",
    )

    assert grade.found == [plant]


def test_different_route_is_not_counted_as_a_template_match() -> None:
    plant = Planted("render", "baseline", "/product/<id>", "product")
    grade = run_demo_suite.grade_findings(
        [finding(FindingKind.RENDER_DEFECT, Axis.BASELINE, "http://127.0.0.1:8099/shop/cart")],
        [plant],
        site_name="shop",
    )

    assert grade.missed == [plant]
    assert len(grade.false_positives) == 1


def test_landing_page_matches_root_under_a_site_mount() -> None:
    plant = Planted("render", "baseline", "/", "landing")
    grade = run_demo_suite.grade_findings(
        [finding(FindingKind.RENDER_DEFECT, Axis.BASELINE, "http://127.0.0.1:8099/shop/")],
        [plant],
        site_name="shop",
    )

    assert grade.found == [plant]


def test_unmatched_finding_is_a_false_positive_including_for_a_control_site() -> None:
    item = finding(FindingKind.DEAD_SURFACE, Axis.BASELINE, "http://127.0.0.1:8099/control/reports")

    grade = run_demo_suite.grade_findings([item], [], site_name="control")

    assert grade.false_positives == [item]


def test_exit_code_fails_for_misses_or_false_positives() -> None:
    plant = Planted("render", "baseline", "/", "landing")

    assert run_demo_suite.exit_code({"site": run_demo_suite.grade_findings([], [plant])}) == 1
    assert run_demo_suite.exit_code({"site": run_demo_suite.grade_findings([finding(FindingKind.RENDER_DEFECT, Axis.BASELINE, "/")], [])}) == 1


def test_summary_writer_records_every_grade_and_plant_verdict(tmp_path) -> None:
    found = Planted("render", "baseline", "/", "landing")
    missed = Planted("escalation", "privilege", "/billing", "billing")
    grades = {
        "shop": run_demo_suite.Grade([found], [missed], [finding(FindingKind.DEAD_SURFACE, Axis.BASELINE, "/other")]),
        "control": run_demo_suite.Grade([], [], []),
    }
    path = tmp_path / "graded-summary.json"

    run_demo_suite.write_summary(grades, "http://127.0.0.1:8090", path, generated_at="2026-08-29T12:00:00+00:00")

    assert json.loads(path.read_text()) == {
        "host": "http://127.0.0.1:8090",
        "generated_at": "2026-08-29T12:00:00+00:00",
        "sites": {
            "shop": {
                "planted": 2, "found": 1, "missed": 1, "false_positives": 1,
                "plants": [
                    {"name": "landing", "defect": "render", "axis": "baseline", "route": "/", "verdict": "found"},
                    {"name": "billing", "defect": "escalation", "axis": "privilege", "route": "/billing", "verdict": "missed"},
                ],
            },
            "control": {"planted": 0, "found": 0, "missed": 0, "false_positives": 0, "plants": []},
        },
        "totals": {"planted": 2, "found": 1, "missed": 1, "false_positives": 1},
    }


def test_public_spec_example_is_emitted_from_a_real_finding() -> None:
    generated = run_demo_suite.generated_example_spec()
    published = (run_demo_suite.ROOT / "web" / "generated-example.spec.ts").read_text(encoding="utf-8")

    assert published == generated
    assert 'test("Parallax: escalation-privilege-' in generated


def test_storage_state_builder_turns_a_login_cookie_into_playwright_state() -> None:
    class FakeLoginResponse:
        headers = {"Set-Cookie": "session=owner-token; Path=/; HttpOnly; SameSite=Lax"}

    state = run_demo_suite.storage_state_from_login_response(FakeLoginResponse(), "http://127.0.0.1:8099")

    assert state == {
        "cookies": [{
            "name": "session", "value": "owner-token", "domain": "127.0.0.1", "path": "/",
            "httpOnly": True, "secure": False, "sameSite": "Lax",
        }],
        "origins": [],
    }


def test_storage_state_builder_uses_declared_accounts_without_reading_site_source(tmp_path, monkeypatch) -> None:
    requests = []

    class StubSite:
        name = "stub"
        accounts = [Account("reader", "declared@demo", "declared-password")]

    class Response:
        status = 302
        headers = {"Set-Cookie": "session=reader; Path=/; HttpOnly"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Opener:
        def open(self, request):
            requests.append(request)
            return Response()

    monkeypatch.setattr(run_demo_suite, "build_opener", lambda *handlers: Opener())

    states = run_demo_suite.build_storage_states(StubSite(), "http://127.0.0.1:8099", tmp_path)

    assert set(states) == {"reader"}
    assert parse_qs(requests[0].data.decode()) == {
        "email": ["declared@demo"], "username": ["declared@demo"], "password": ["declared-password"],
    }


def test_storage_state_builder_sweeps_sites_without_accounts_anonymously(tmp_path, monkeypatch) -> None:
    class StubSite:
        name = "public"
        accounts: list[Account] = []

    monkeypatch.setattr(run_demo_suite, "build_opener", lambda *handlers: (_ for _ in ()).throw(AssertionError("anonymous sites do not log in")))

    assert run_demo_suite.build_storage_states(StubSite(), "http://127.0.0.1:8099", tmp_path) == {}


def test_storage_state_builder_reports_failed_login_and_continues_with_other_accounts(tmp_path, monkeypatch, capsys) -> None:
    class StubSite:
        name = "stub"
        accounts = [Account("broken", "broken@demo", "wrong"), Account("member", "member@demo", "demo")]

    class Response:
        def __init__(self, cookie: str | None) -> None:
            self.status = 200 if cookie is None else 302
            self.headers = {} if cookie is None else {"Set-Cookie": cookie}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    responses = iter([Response(None), Response("session=member; Path=/; HttpOnly")])

    class Opener:
        def open(self, request):
            return next(responses)

    monkeypatch.setattr(run_demo_suite, "build_opener", lambda *handlers: Opener())

    states = run_demo_suite.build_storage_states(StubSite(), "http://127.0.0.1:8099", tmp_path)

    assert set(states) == {"member"}
    assert "site stub, role broken, server returned HTTP 200" in capsys.readouterr().err


def test_relational_scenarios_read_a_site_declaration_instead_of_its_name() -> None:
    class StubSite:
        name = "collaboration"
        relational_scenarios = [{
            "surface": "/threads",
            "sender": "owner",
            "receiver": "member",
            "action": {"type": "submit_form", "form": "form.composer", "fills": []},
            "effect": {"type": "visible", "selector": ".message"},
            "deadline_ms": 1000,
        }]

    scenarios = run_demo_suite._relational_scenarios(StubSite(), "http://127.0.0.1:8099")

    assert len(scenarios) == 1
    assert scenarios[0].surface.path == "http://127.0.0.1:8099/collaboration/threads"
