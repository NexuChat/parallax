"""Run and grade Parallax against every available demo site."""

from __future__ import annotations

import argparse
import asyncio
from http.cookies import SimpleCookie
import importlib
import inspect
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo"
if str(DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(DEMO_DIR))

from parallax.conductor import Conductor  # noqa: E402
from parallax.emitter import spec_for  # noqa: E402
from parallax.specialists import AccessSpecialist, LayoutI18nSpecialist, RealtimeSpecialist  # noqa: E402
from parallax.types import Axis, BASELINE, Finding, FindingKind, Outcome, Privilege, Severity, Surface, SurfaceKind, Testimony  # noqa: E402
from serve import discover_sites  # noqa: E402
from sites.base import Planted  # noqa: E402


@dataclass
class Grade:
    found: list[Planted]
    missed: list[Planted]
    false_positives: list[Finding]


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _route_matches(planted_route: str, finding_route: str, site_name: str | None) -> bool:
    expected = _path(planted_route)
    actual = _path(finding_route)
    if site_name and actual == f"/{site_name}":
        actual = "/"
    elif site_name and actual.startswith(f"/{site_name}/"):
        actual = actual[len(site_name) + 1 :]
    expected_parts = expected.split("/")
    actual_parts = actual.split("/")
    if len(expected_parts) != len(actual_parts):
        return False
    return all(
        bool(actual_part) if re.fullmatch(r"<[^/<>]+>", expected_part) else expected_part == actual_part
        for expected_part, actual_part in zip(expected_parts, actual_parts)
    )


def _path(value: str) -> str:
    path = urlsplit(value).path or "/"
    return path if path.startswith("/") else f"/{path}"


def _finding_defects(finding: Finding) -> set[str]:
    defects = {_value(finding.kind)}
    for testimony in finding.testimonies:
        defects.update(_value(defect) for defect in getattr(testimony, "defects", []))
    return defects


def _matches(plant: Planted, finding: Finding, site_name: str | None) -> bool:
    return (
        plant.defect in _finding_defects(finding)
        and plant.axis == _value(finding.axis)
        and _route_matches(plant.route, finding.surface.path, site_name)
    )


def grade_findings(findings: list[Finding], planted: list[Planted], site_name: str | None = None) -> Grade:
    unmatched = list(findings)
    found: list[Planted] = []
    missed: list[Planted] = []
    for plant in planted:
        match = next((item for item in unmatched if _matches(plant, item, site_name)), None)
        if match is None:
            missed.append(plant)
        else:
            found.append(plant)
            unmatched.remove(match)
    return Grade(found, missed, unmatched)


def exit_code(grades: dict[str, Grade]) -> int:
    return int(any(grade.missed or grade.false_positives for grade in grades.values()))


def summary_payload(grades: dict[str, Grade], host: str, generated_at: str | None = None) -> dict[str, object]:
    """Make the public, machine-readable account of one graded demo run."""
    sites: dict[str, dict[str, object]] = {}
    totals = {"planted": 0, "found": 0, "missed": 0, "false_positives": 0}
    for name, grade in grades.items():
        plants = [
            {"name": plant.note, "defect": plant.defect, "axis": plant.axis, "route": plant.route, "verdict": verdict}
            for verdict, group in (("found", grade.found), ("missed", grade.missed))
            for plant in group
        ]
        site = {
            "planted": len(plants), "found": len(grade.found), "missed": len(grade.missed),
            "false_positives": len(grade.false_positives), "plants": plants,
        }
        sites[name] = site
        for key in totals:
            totals[key] += int(site[key])
    return {
        "host": host.rstrip("/"),
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "sites": sites,
        "totals": totals,
    }


def write_summary(grades: dict[str, Grade], host: str, path: Path, *, generated_at: str | None = None) -> None:
    """Publish the completed demo grade where the public page can fetch it."""
    path.write_text(json.dumps(summary_payload(grades, host, generated_at), indent=2) + "\n", encoding="utf-8")


def generated_example_spec() -> str:
    """Generate the public output example from the same Finding model as a run."""
    surface = Surface(SurfaceKind.ROUTE, "https://demo.mlki.app/workspace/audit")
    anon = BASELINE.__class__(privilege=Privilege.ANON, varies=Axis.PRIVILEGE)
    finding = Finding(
        FindingKind.ESCALATION, Severity.HIGH, surface, Axis.PRIVILEGE,
        "Anonymous access to the workspace audit route.",
        [Testimony(surface, BASELINE, Outcome.REACHED), Testimony(surface, anon, Outcome.REACHED)],
    )
    return spec_for(finding)


def write_generated_example(path: Path) -> None:
    path.write_text(generated_example_spec(), encoding="utf-8")


def _specialists(no_vision: bool) -> list[object]:
    specialists: list[object] = [AccessSpecialist(), RealtimeSpecialist()]
    if not no_vision and os.environ.get("GEMINI_API_KEY"):
        specialists.append(LayoutI18nSpecialist())
    return specialists


def storage_state_from_login_response(response: object, origin: str) -> dict[str, object]:
    """Convert a plain HTTP login response into Playwright's storage-state shape."""
    headers = getattr(response, "headers", {})
    raw_cookies = headers.get_all("Set-Cookie") if hasattr(headers, "get_all") else None
    if not raw_cookies:
        raw_cookie = headers.get("Set-Cookie")
        raw_cookies = [raw_cookie] if raw_cookie else []
    host = urlsplit(origin).hostname
    if not host:
        raise ValueError(f"login origin has no host: {origin}")
    cookies: list[dict[str, object]] = []
    for raw_cookie in raw_cookies:
        parsed = SimpleCookie(str(raw_cookie))
        for morsel in parsed.values():
            same_site = morsel["samesite"].capitalize() if morsel["samesite"] else "Lax"
            cookies.append({
                "name": morsel.key,
                "value": morsel.value,
                "domain": host,
                "path": morsel["path"] or "/",
                "httpOnly": bool(morsel["httponly"]),
                "secure": bool(morsel["secure"]),
                "sameSite": same_site,
            })
    if not cookies:
        raise ValueError("login response did not set a session cookie")
    return {"cookies": cookies, "origins": []}


def _seeded_accounts(site: object) -> list[tuple[str, dict[str, str]]]:
    """Read demo credentials from the site module instead of embedding them here."""
    module = importlib.import_module(type(site).__module__)
    text = inspect.getdoc(module) or ""
    pairs = re.findall(r"``([^`/]+?)\s*/\s*([^`]+?)``", text)
    if not pairs:
        # Older demos omitted their account paragraph; still read credentials from
        # the module that owns them, never from this runner.
        source = inspect.getsource(module)
        login_rule = next((line for line in source.splitlines() if line.lstrip().startswith("if ") and "password" in line and " in " in line), "")
        pairs = re.findall(r"\(\s*[\"']([^\"']+)[\"']\s*,\s*[\"']([^\"']+)[\"']\s*\)", login_rule)
    if pairs:
        return [(name, {"username": name, "password": password}) for name, password in pairs]

    values = re.findall(r"``([^`]+)``", text)
    emails = [value for value in values if "@" in value]
    password = next((value for value in reversed(values) if "@" not in value), None)
    if emails and password:
        return [(email.split("@", 1)[0], {"email": email, "password": password}) for email in emails]
    return []


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request: Request, fp: object, code: int, msg: str, headers: object, newurl: str) -> None:
        return None

    def http_error_302(self, request: Request, fp: object, code: int, msg: str, headers: object) -> object:
        return fp

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def build_storage_states(site: object, host: str, run_dir: Path) -> dict[str, Path]:
    """Log in each documented seeded role over HTTP and persist its cookie state."""
    states: dict[str, Path] = {}
    run_dir.mkdir(parents=True, exist_ok=True)
    origin = host.rstrip("/")
    for role, credentials in _seeded_accounts(site):
        request = Request(
            f"{origin}/{getattr(site, 'name')}/login",
            data=urlencode(credentials).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with build_opener(_NoRedirect()).open(request) as response:
            state = storage_state_from_login_response(response, origin)
        path = run_dir / f"storage-{role}.json"
        path.write_text(json.dumps(state), encoding="utf-8")
        states[role] = path
    return states


async def run(args: argparse.Namespace) -> dict[str, Grade]:
    from playwright.async_api import async_playwright

    sites = [site for site in discover_sites() if args.only is None or site.name == args.only]
    if args.only and not sites:
        raise SystemExit(f"unknown or unavailable site: {args.only}")
    host = args.host.rstrip("/")
    grades: dict[str, Grade] = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            for site in sites:
                run_dir = ROOT / "runs" / site.name
                summary = await Conductor(
                    f"{host}/{site.name}/", run_dir, browser=browser,
                    specialists=_specialists(args.no_vision), max_surfaces=args.max_surfaces,
                    storage_states=build_storage_states(site, host, run_dir),
                ).conduct()
                grades[site.name] = grade_findings(summary.findings, site.planted, site.name)
        finally:
            await browser.close()
    return grades


def print_report(grades: dict[str, Grade]) -> None:
    print("site       found  missed  false+  details")
    for name, grade in grades.items():
        details = ", ".join([f"missed:{plant.defect}@{plant.route}" for plant in grade.missed] + [
            f"false+:{_value(finding.kind)}@{urlsplit(finding.surface.path).path}" for finding in grade.false_positives
        ]) or "ok"
        print(f"{name:<10} {len(grade.found):>5}  {len(grade.missed):>6}  {len(grade.false_positives):>6}  {details}")
    found = sum(len(grade.found) for grade in grades.values())
    missed = sum(len(grade.missed) for grade in grades.values())
    false_positives = sum(len(grade.false_positives) for grade in grades.values())
    code = exit_code(grades)
    result = "PASS" if code == 0 else "FAIL"
    print(f"total      {found:>5}  {missed:>6}  {false_positives:>6}  {result} (exit {code})")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="http://127.0.0.1:8080")
    parser.add_argument("--only")
    parser.add_argument("--no-vision", action="store_true")
    parser.add_argument("--max-surfaces", type=int, default=64)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    grades = asyncio.run(run(args))
    write_summary(grades, args.host, ROOT / "web" / "graded-summary.json")
    write_generated_example(ROOT / "web" / "generated-example.spec.ts")
    print_report(grades)
    return exit_code(grades)


if __name__ == "__main__":
    raise SystemExit(main())
