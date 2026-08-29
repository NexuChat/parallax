"""Run and grade Parallax against every available demo site."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo"
if str(DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(DEMO_DIR))

from parallax.conductor import Conductor  # noqa: E402
from parallax.specialists import AccessSpecialist, LayoutI18nSpecialist, RealtimeSpecialist  # noqa: E402
from parallax.types import Finding  # noqa: E402
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
    expected = urlsplit(planted_route).path or "/"
    actual = urlsplit(finding_route).path or "/"
    if site_name and actual == f"/{site_name}":
        actual = "/"
    elif site_name and actual.startswith(f"/{site_name}/"):
        actual = actual[len(site_name) + 1 :]
    expected = "/" + expected.strip("/") if expected != "/" else "/"
    actual = "/" + actual.strip("/") if actual != "/" else "/"
    return expected == actual


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


def _specialists(no_vision: bool) -> list[object]:
    specialists: list[object] = [AccessSpecialist(), RealtimeSpecialist()]
    if not no_vision and os.environ.get("GEMINI_API_KEY"):
        specialists.append(LayoutI18nSpecialist())
    return specialists


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
                summary = await Conductor(
                    f"{host}/{site.name}/", ROOT / "runs" / site.name, browser=browser,
                    specialists=_specialists(args.no_vision), max_surfaces=args.max_surfaces,
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="http://127.0.0.1:8080")
    parser.add_argument("--only")
    parser.add_argument("--no-vision", action="store_true")
    parser.add_argument("--max-surfaces", type=int, default=12)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    grades = asyncio.run(run(parse_args(argv)))
    print_report(grades)
    return exit_code(grades)


if __name__ == "__main__":
    raise SystemExit(main())
