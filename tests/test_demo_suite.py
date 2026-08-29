from __future__ import annotations

from parallax.types import Axis, Finding, FindingKind, Severity, Surface, SurfaceKind
from scripts import run_demo_suite
from sites.base import Planted


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
