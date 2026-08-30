"""Run one sweep: discover an app, witness it from seven contexts, publish.

    python -m parallax https://app.example.com --out runs/first

Everything the run produces lands in one directory — the feed the console reads,
the mosaics it shows, and the failing Playwright specs the findings became.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from .conductor import Conductor, RelationalScenario
from .specialists import LayoutI18nSpecialist, RealtimeSpecialist
from .types import Context, Privilege, Severity, Surface, SurfaceKind


def _parse(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="parallax", description=__doc__.splitlines()[0])
    parser.add_argument("url", help="where the baseline witness starts")
    parser.add_argument("--out", default="runs/latest", type=Path, help="output directory")
    parser.add_argument("--max-surfaces", type=int, default=12)
    parser.add_argument("--settle-ms", type=int, default=500)
    parser.add_argument(
        "--relational-scenarios",
        type=Path,
        metavar="PATH",
        help="JSON file of sender/receiver scenarios to exercise concurrently",
    )
    parser.add_argument("--headed", action="store_true", help="show the browsers (a demo, not a run)")
    parser.add_argument(
        "--storage-state",
        action="append",
        default=[],
        metavar="ROLE=PATH",
        help="Playwright storage state per role, e.g. owner=.auth/owner.json (repeatable)",
    )
    parser.add_argument(
        "--no-vision",
        action="store_true",
        help="skip the Gemini lens; the deterministic ones still run",
    )
    return parser.parse_args(argv)


def _storage_states(pairs: list[str]) -> dict[Privilege | str, str]:
    states: dict[Privilege | str, str] = {}
    for pair in pairs:
        role, _, path = pair.partition("=")
        if not path:
            raise SystemExit(f"--storage-state expects ROLE=PATH, got {pair!r}")
        states[role.strip()] = path.strip()
    return states


def _specialists(no_vision: bool) -> list[object]:
    # The conductor always runs the differ, which owns escalation and inversion
    # judgement. AccessSpecialist remains an opt-in compatibility lens, never a
    # default CLI lens, so its projection cannot duplicate that work.
    lenses: list[object] = [RealtimeSpecialist()]
    if no_vision:
        print("vision lens disabled: --no-vision", file=sys.stderr)
        return lenses
    vision = LayoutI18nSpecialist()
    if vision.route == "disabled":
        print(
            "vision lens disabled: set GOOGLE_CLOUD_PROJECT for Vertex AI or GEMINI_API_KEY for AI Studio",
            file=sys.stderr,
        )
        return lenses
    print(f"vision lens route: {vision.route}", file=sys.stderr)
    lenses.append(vision)
    return lenses


def _scenario_error(source: str, problem: str) -> SystemExit:
    return SystemExit(f"relational scenarios {source}: {problem}")


def _string(value: Any, name: str, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _scenario_error(source, f"{name} must be a non-empty string")
    return value


def _action(spec: Any, name: str, source: str) -> object:
    if not isinstance(spec, dict):
        raise _scenario_error(source, f"{name}.action must be an object")
    if spec.get("type") != "submit_form":
        raise _scenario_error(source, f"{name}.action.type must be 'submit_form'")
    form = _string(spec.get("form"), f"{name}.action.form", source)
    checks = spec.get("checks", [])
    fills = spec.get("fills", [])
    if not isinstance(checks, list) or not all(isinstance(item, str) and item for item in checks):
        raise _scenario_error(source, f"{name}.action.checks must be a list of selectors")
    if not isinstance(fills, list):
        raise _scenario_error(source, f"{name}.action.fills must be a list")
    fields: list[tuple[str, str]] = []
    for index, fill in enumerate(fills, start=1):
        if not isinstance(fill, dict):
            raise _scenario_error(source, f"{name}.action.fills[{index}] must be an object")
        fields.append((
            _string(fill.get("selector"), f"{name}.action.fills[{index}].selector", source),
            _string(fill.get("value"), f"{name}.action.fills[{index}].value", source),
        ))

    async def submit_form(page: object) -> None:
        for selector in checks:
            await page.locator(selector).check()
        for selector, value in fields:
            await page.locator(selector).fill(value)
        await page.locator(form).evaluate("form => form.requestSubmit()")

    return submit_form


def _effect(spec: Any, name: str, source: str) -> object:
    if not isinstance(spec, dict):
        raise _scenario_error(source, f"{name}.effect must be an object")
    effect_type = spec.get("type")
    if effect_type == "visible":
        selector = _string(spec.get("selector"), f"{name}.effect.selector", source)

        async def visible(page: object) -> bool:
            return bool(await page.locator(selector).is_visible())

        return visible
    if effect_type == "json_contains":
        request = {
            "url": _string(spec.get("url"), f"{name}.effect.url", source),
            "items": _string(spec.get("items"), f"{name}.effect.items", source),
            "field": _string(spec.get("field"), f"{name}.effect.field", source),
            "equals": _string(spec.get("equals"), f"{name}.effect.equals", source),
        }

        async def json_contains(page: object) -> bool:
            return bool(await page.evaluate("""async (expectation) => {
              const response = await fetch(new URL(expectation.url, location.href));
              if (!response.ok) return false;
              const payload = await response.json();
              return Array.isArray(payload[expectation.items]) && payload[expectation.items]
                .some((item) => item && item[expectation.field] === expectation.equals);
            }""", request))

        return json_contains
    raise _scenario_error(source, f"{name}.effect.type must be 'visible' or 'json_contains'")


def _scenario_type(spec: dict[str, Any], name: str, source: str) -> str:
    scenario_type = spec.get("type", "propagation")
    if scenario_type not in ("propagation", "revocation"):
        raise _scenario_error(source, f"{name}.type must be 'propagation' or 'revocation'")
    return scenario_type


def relational_scenarios_from_data(data: Any, start_url: str, *, source: str = "declaration") -> list[RelationalScenario]:
    """Turn the restricted, data-only relational scenario format into conductor calls."""
    scenarios = data.get("scenarios") if isinstance(data, dict) else data
    if not isinstance(scenarios, list):
        raise _scenario_error(source, "scenarios must be a list")
    result: list[RelationalScenario] = []
    for index, spec in enumerate(scenarios, start=1):
        name = f"scenario {index}"
        if not isinstance(spec, dict):
            raise _scenario_error(source, f"{name} must be an object")
        scenario_type = _scenario_type(spec, name, source)
        surface = _string(spec.get("surface"), f"{name}.surface", source)
        try:
            sender = Context(privilege=Privilege(_string(spec.get("sender"), f"{name}.sender", source)))
            receiver = Context(privilege=Privilege(_string(spec.get("receiver"), f"{name}.receiver", source)))
        except ValueError as error:
            raise _scenario_error(source, f"{name}.sender and {name}.receiver must be anon, member, or owner") from error
        deadline_ms = spec.get("deadline_ms")
        if not isinstance(deadline_ms, int) or isinstance(deadline_ms, bool) or deadline_ms < 1:
            raise _scenario_error(source, f"{name}.deadline_ms must be a positive integer")
        distribution = spec.get("distribution")
        enforcement = spec.get("enforcement")
        scenario = RelationalScenario(
            Surface(SurfaceKind.ROUTE, urljoin(start_url, surface)), sender=sender, receiver=receiver,
            action=_action(spec.get("action"), name, source), effect=_effect(spec.get("effect"), name, source),
            deadline_ms=deadline_ms, kind=scenario_type,
            distribution=_effect(distribution, f"{name}.distribution", source) if distribution else None,
            enforcement=_effect(enforcement, f"{name}.enforcement", source) if enforcement else None,
        )
        result.append(scenario)
    return result


def _relational_scenarios(path: Path, start_url: str) -> list[RelationalScenario]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise _scenario_error(str(path), "file does not exist") from error
    except OSError as error:
        raise _scenario_error(str(path), f"could not read file: {error}") from error
    except json.JSONDecodeError as error:
        raise _scenario_error(str(path), f"invalid JSON at line {error.lineno}, column {error.colno}") from error
    return relational_scenarios_from_data(data, start_url, source=str(path))


async def _run(args: argparse.Namespace) -> int:
    from playwright.async_api import async_playwright

    relational_scenarios = _relational_scenarios(args.relational_scenarios, args.url) if args.relational_scenarios else None
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=not args.headed, args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        try:
            summary = await _conduct(args, browser, relational_scenarios)
        finally:
            await browser.close()

    counts: dict[str, int] = {}
    for finding in summary.findings:
        counts[finding.severity.value] = counts.get(finding.severity.value, 0) + 1
    exercised = [decision for decision in summary.axis_applicability if decision.applicable]
    not_applicable = [decision for decision in summary.axis_applicability if not decision.applicable]
    print(json.dumps({
        "surfaces": len(summary.surfaces),
        "testimonies": len(summary.testimonies),
        "findings": len(summary.findings),
        "by_severity": {level.value: counts.get(level.value, 0) for level in Severity},
        "feed": str(summary.feed_path),
        "specs": len(summary.spec_paths),
        "axis_summary": f"{len(exercised)} axes exercised, {len(not_applicable)} not applicable",
        "axis_applicability": [
            {"axis": decision.axis.value, "applicable": decision.applicable, "reason": decision.reason}
            for decision in summary.axis_applicability
        ],
        "relational_scenarios": {
            "ran": len(relational_scenarios or []),
            "findings": sum(finding.axis.value == "relational" for finding in summary.findings),
        },
    }, indent=2))
    print(f"\nconsole: open console/index.html?feed=../{summary.feed_path}", file=sys.stderr)
    # A run that found nothing is a finished run, not a failed one.
    return 0


async def _conduct(
    args: argparse.Namespace, browser: object, relational_scenarios: list[RelationalScenario] | None
) -> object:
    """Make the CLI-to-conductor contract testable without launching Chromium."""
    options: dict[str, object] = {
        "browser": browser,
        "specialists": _specialists(args.no_vision),
        "storage_states": _storage_states(args.storage_state) or None,
        "max_surfaces": args.max_surfaces,
        "settle_ms": args.settle_ms,
    }
    if relational_scenarios is not None:
        options["relational_scenarios"] = relational_scenarios
    return await Conductor(args.url, args.out, **options).conduct()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
