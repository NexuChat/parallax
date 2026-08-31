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
from .capability import CapabilityScenario
from .contracts import FeedEvent
from .delivery import DeliveryReport, PullRequestDelivery
from .differ import configure_semantics
from .proposer import ProposalReport, ScenarioProposer
from .semantics import SemanticComparator
from .specialists import LayoutI18nSpecialist, RealtimeSpecialist
from .triage import GemmaTriage, TriageReport
from .types import EffectExpectation, FormAction, Context, Privilege, RelationalReplay, Severity, Surface, SurfaceKind


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
    parser.add_argument(
        "--propose-scenarios",
        action="store_true",
        help="ask Gemini to propose observed-data relational scenarios",
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
        "--open-pr",
        nargs="?",
        const="",
        metavar="OWNER/REPO",
        help="deliver the generated specs as a pull request (needs GITHUB_TOKEN)",
    )
    parser.add_argument(
        "--pr-base",
        metavar="BRANCH",
        help="branch to open the pull request against; defaults to the repository default",
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


def _model_report(specialists: list[object]) -> dict[str, object]:
    """State what the vision lens actually did, so its silence is never ambiguous."""
    for lens in specialists:
        if not hasattr(lens, "calls_attempted"):
            continue
        report: dict[str, object] = {
            "name": getattr(lens, "model", "unknown"),
            "route": getattr(lens, "route", "unknown"),
            "calls_attempted": lens.calls_attempted,
            "calls_succeeded": lens.calls_succeeded,
        }
        if lens.last_error:
            report["last_error"] = lens.last_error
        return report
    return {"route": "disabled", "calls_attempted": 0, "calls_succeeded": 0}


def _append_triage(feed_path: Path, triage: TriageReport) -> None:
    """Record the grouping pass in the feed the console actually reads."""
    if not feed_path.exists():
        return
    event = FeedEvent(
        "triage",
        {
            "model": triage.model,
            "attempted": triage.attempted,
            "summary": triage.summary,
            "error": triage.error,
            "groups": [
                {"label": group.label, "finding_ids": list(group.finding_ids)}
                for group in triage.groups
            ],
        },
    )
    with feed_path.open("a", encoding="utf-8") as feed:
        feed.write(json.dumps(event.to_json(), separators=(",", ":")) + "\n")


def _deliver(args: argparse.Namespace, summary: Any) -> DeliveryReport:
    """Turn the findings into a pull request, or say precisely why not."""
    if args.open_pr is None:
        return DeliveryReport(note="not requested")
    delivery = PullRequestDelivery(args.open_pr or None, base=args.pr_base)
    report = delivery.deliver(summary.findings, summary.spec_paths)
    if report.error:
        print(f"pull request delivery failed: {report.error}", file=sys.stderr)
    elif report.note:
        print(f"pull request delivery skipped: {report.note}", file=sys.stderr)
    elif report.pull_request_url:
        state = "already open" if report.already_open else "opened"
        print(f"pull request {state}: {report.pull_request_url}", file=sys.stderr)
    return report


def _scenario_proposer(enabled: bool) -> ScenarioProposer | None:
    if not enabled:
        return None
    proposer = ScenarioProposer()
    if proposer.route == "disabled":
        print("scenario proposer disabled: set GOOGLE_CLOUD_PROJECT for Vertex AI", file=sys.stderr)
    else:
        print(f"scenario proposer route: {proposer.route}", file=sys.stderr)
    return proposer


def _proposal_report(report: ProposalReport) -> dict[str, object]:
    """State whether Gemini proposed useful scenarios and why it did not."""
    payload: dict[str, object] = {
        "enabled": report.enabled,
        "proposed": report.proposed,
        "validated": report.validated,
        "rejected": [{"index": item.index, "reason": item.reason} for item in report.rejections],
        "calls_attempted": report.calls_attempted,
        "calls_succeeded": report.calls_succeeded,
        "route": report.route,
    }
    if report.last_error:
        payload["last_error"] = report.last_error
    if report.note:
        payload["note"] = report.note
    return payload


def _scenario_error(source: str, problem: str) -> SystemExit:
    return SystemExit(f"relational scenarios {source}: {problem}")


def _string(value: Any, name: str, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _scenario_error(source, f"{name} must be a non-empty string")
    return value


def _action(spec: Any, name: str, source: str) -> tuple[object, FormAction]:
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

    return submit_form, FormAction(form, tuple(checks), tuple(fields))


def _effect(spec: Any, name: str, source: str) -> tuple[object, EffectExpectation]:
    if not isinstance(spec, dict):
        raise _scenario_error(source, f"{name}.effect must be an object")
    effect_type = spec.get("type")
    if effect_type == "visible":
        selector = _string(spec.get("selector"), f"{name}.effect.selector", source)

        async def visible(page: object) -> bool:
            return bool(await page.locator(selector).is_visible())

        return visible, EffectExpectation("visible", selector=selector)
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

        return json_contains, EffectExpectation("json_contains", **request)
    raise _scenario_error(source, f"{name}.effect.type must be 'visible' or 'json_contains'")


def _scenario_type(spec: dict[str, Any], name: str, source: str) -> str:
    scenario_type = spec.get("type", "propagation")
    if scenario_type not in ("propagation", "revocation"):
        raise _scenario_error(source, f"{name}.type must be 'propagation' or 'revocation'")
    return scenario_type


def capability_scenarios_from_data(data: Any, start_url: str, *, source: str = "declaration") -> list[CapabilityScenario]:
    """Parse capability declarations with the same validated action grammar.

    A capability names the roles to try the action as and which of them are
    supposed to succeed. Everything else — the form, the fills, the effect — is
    the identical vocabulary a relational scenario uses, so nothing here widens
    what Parallax is willing to execute.
    """
    entries = data.get("capabilities") if isinstance(data, dict) else data
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise _scenario_error(source, "capabilities must be a list")
    result: list[CapabilityScenario] = []
    for index, spec in enumerate(entries, start=1):
        name = f"capability {index}"
        if not isinstance(spec, dict):
            raise _scenario_error(source, f"{name} must be an object")
        surface = _string(spec.get("surface"), f"{name}.surface", source)
        label = spec.get("label") if isinstance(spec.get("label"), str) and spec.get("label") else "action"
        deadline_ms = spec.get("deadline_ms")
        if not isinstance(deadline_ms, int) or isinstance(deadline_ms, bool) or deadline_ms < 1:
            raise _scenario_error(source, f"{name}.deadline_ms must be a positive integer")
        roles = _roles(spec.get("roles"), f"{name}.roles", source)
        allowed = _roles(spec.get("allowed", []), f"{name}.allowed", source, allow_empty=True)
        if unknown := set(allowed) - set(roles):
            raise _scenario_error(
                source, f"{name}.allowed names {sorted(r.value for r in unknown)[0]}, which is not in {name}.roles"
            )
        action, _ = _action(spec.get("action"), name, source)
        effect, _ = _effect(spec.get("effect"), name, source)
        result.append(CapabilityScenario(
            surface=Surface(SurfaceKind.ROUTE, urljoin(start_url, surface)),
            action=action, effect=effect,
            roles=tuple(roles), allowed=frozenset(allowed),
            deadline_ms=deadline_ms, label=label,
        ))
    return result


def _roles(value: Any, name: str, source: str, *, allow_empty: bool = False) -> list[Privilege]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise _scenario_error(source, f"{name} must be a non-empty list of roles")
    try:
        return [Privilege(_string(item, name, source)) for item in value]
    except ValueError as error:
        raise _scenario_error(source, f"{name} must contain only anon, member, or owner") from error


def relational_scenarios_from_data(data: Any, start_url: str, *, source: str = "declaration") -> list[RelationalScenario]:
    """Turn the restricted, data-only relational scenario format into conductor calls."""
    scenarios = data.get("scenarios") if isinstance(data, dict) else data
    # A file may declare capabilities and no relational scenarios. Demanding an
    # empty "scenarios" key to say so would be a trap, not a contract.
    if scenarios is None and isinstance(data, dict) and "capabilities" in data:
        return []
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
        max_lag_ms = spec.get("max_lag_ms") if scenario_type == "revocation" else None
        if scenario_type == "revocation" and (
            not isinstance(max_lag_ms, int) or isinstance(max_lag_ms, bool) or max_lag_ms < 0
        ):
            raise _scenario_error(source, f"{name}.max_lag_ms must be a non-negative integer")
        if scenario_type == "revocation" and max_lag_ms >= deadline_ms:
            raise _scenario_error(source, f"{name}.max_lag_ms must be below deadline_ms")
        distribution = spec.get("distribution")
        enforcement = spec.get("enforcement")
        action, replay_action = _action(spec.get("action"), name, source)
        effect, replay_effect = _effect(spec.get("effect"), name, source)
        scenario = RelationalScenario(
            Surface(SurfaceKind.ROUTE, urljoin(start_url, surface)), sender=sender, receiver=receiver,
            action=action, effect=effect,
            deadline_ms=deadline_ms, kind=scenario_type,
            max_lag_ms=max_lag_ms,
            distribution=_effect(distribution, f"{name}.distribution", source)[0] if distribution else None,
            enforcement=_effect(enforcement, f"{name}.enforcement", source)[0] if enforcement else None,
            replay=RelationalReplay(
                sender=sender.privilege,
                receiver=receiver.privilege,
                action=replay_action,
                effect=replay_effect,
                deadline_ms=deadline_ms,
                max_lag_ms=max_lag_ms,
            ),
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
    capability_scenarios = (
        capability_scenarios_from_data(
            json.loads(args.relational_scenarios.read_text(encoding="utf-8")),
            args.url,
            source=str(args.relational_scenarios),
        )
        if args.relational_scenarios
        else []
    )
    # Built once and kept, because the run summary has to report what the lens
    # actually did and cannot ask a list the conductor threw away.
    specialists = _specialists(args.no_vision)
    semantics = SemanticComparator()
    configure_semantics(semantics)
    proposer = _scenario_proposer(args.propose_scenarios)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=not args.headed, args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        try:
            summary = await _conduct(
                args, browser, relational_scenarios, specialists, proposer,
                capability_scenarios=capability_scenarios,
            )
        finally:
            await browser.close()

    counts: dict[str, int] = {}
    for finding in summary.findings:
        counts[finding.severity.value] = counts.get(finding.severity.value, 0) + 1
    delivery = _deliver(args, summary)
    triage = GemmaTriage().group(summary.findings)
    # The console reads the feed, not this process's stdout. A grouping that
    # exists only in the terminal cannot be checked against the published
    # evidence later, so it is appended to the feed as its own event — carrying
    # the finding ids, so a reader can confirm the model only ever partitioned
    # findings the deterministic layers had already produced.
    _append_triage(summary.feed_path, triage)
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
        "capabilities": {
            "ran": len(capability_scenarios),
            "roles_exercised": sum(len(c.roles) for c in capability_scenarios),
        },
        "relational_scenarios": {
            "ran": summary.scenarios_exercised,
            "declared": len(relational_scenarios or []),
            "proposed_by_model": summary.scenarios_proposed_exercised,
            "findings": sum(finding.axis.value == "relational" for finding in summary.findings),
        },
        # Whether the mandatory model was actually reached, not whether a key
        # happened to be set. A run that could not call it says so here.
        "model": _model_report(specialists),
        "semantics": semantics.report(),
        "proposal": _proposal_report(summary.proposal_report),
        # Grouping is a wording judgement, not a measurement, so it is reported
        # separately from the findings themselves and never alters them.
        "delivery": delivery.report(),
        "triage": {
            "summary": triage.summary,
            "groups": [
                {"label": group.label, "findings": len(group.finding_ids)}
                for group in triage.groups
            ],
        },
    }, indent=2))
    print(f"\nconsole: open console/index.html?feed=../{summary.feed_path}", file=sys.stderr)
    # A run that found nothing is a finished run, not a failed one.
    return 0


async def _conduct(
    args: argparse.Namespace, browser: object, relational_scenarios: list[RelationalScenario] | None,
    specialists: list[object] | None = None,
    proposer: ScenarioProposer | None = None,
    capability_scenarios: list[CapabilityScenario] | None = None,
) -> object:
    """Make the CLI-to-conductor contract testable without launching Chromium."""
    options: dict[str, object] = {
        "browser": browser,
        "specialists": _specialists(args.no_vision) if specialists is None else specialists,
        "storage_states": _storage_states(args.storage_state) or None,
        "max_surfaces": args.max_surfaces,
        "settle_ms": args.settle_ms,
    }
    if relational_scenarios is not None:
        options["relational_scenarios"] = relational_scenarios
    if capability_scenarios:
        options["capability_scenarios"] = capability_scenarios
    if args.propose_scenarios:
        options["scenario_proposer"] = proposer or ScenarioProposer()
        options["proposal_validator"] = relational_scenarios_from_data
    return await Conductor(args.url, args.out, **options).conduct()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
