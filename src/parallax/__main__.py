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
from .audience import AudienceScenario, Observer
from .choreography import Choreography, Expect, Participant, Step
from .contracts import FeedEvent
from .delivery import DeliveryReport, PullRequestDelivery
from .differ import configure_semantics
from .media import MediaExpectation, media_probe, perceived
from .discovery import SessionDiscovery, credentials_from_data
from .proposer import ProposalReport, ScenarioProposer
from .semantics import SemanticComparator
from .specialists import LayoutI18nSpecialist, RealtimeSpecialist
from .triage import GemmaTriage, TriageReport
from .types import (
    Axis, EffectExpectation, FormAction, Context, Privilege, RelationalReplay, Severity, Surface, SurfaceKind,
)


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
    parser.add_argument(
        "--deny",
        action="append",
        default=[],
        metavar="PATTERN",
        help="never visit a route or press a control matching PATTERN (repeatable); "
             "plain text matches anywhere, glob characters match the whole value",
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
        "--credentials",
        type=Path,
        metavar="PATH",
        help="JSON of role -> {identifier, secret}; Parallax finds the sign-in surface itself",
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


async def _discover_sessions(
    args: argparse.Namespace, browser: Any
) -> tuple[list[dict[str, object]], dict[str, Any], Any]:
    """Sign in for every supplied role, then learn how the app changes language.

    This is the difference between a tool that is handed its sessions and one
    that is pointed at a URL. Nothing here is declared: the sign-in surface, the
    fields on it, and the language control are all found by looking.
    """
    from .discovery import LocaleMechanism

    if not args.credentials:
        return [], {}, LocaleMechanism("none", "no credentials were supplied")
    try:
        credentials = credentials_from_data(
            json.loads(args.credentials.read_text(encoding="utf-8")), source=str(args.credentials)
        )
    except (ValueError, OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"credentials: {error}") from error

    discovery = SessionDiscovery(browser, args.url)
    reports: list[dict[str, object]] = []
    states: dict[str, Any] = {}
    for credential in credentials:
        report, state = await discovery.sign_in(credential)
        reports.append(report.report())
        print(
            f"sign-in {credential.role}: "
            + (f"succeeded via {report.route}" if report.succeeded else f"failed — {report.error}"),
            file=sys.stderr,
        )
        if state is not None:
            states[credential.role] = state
    # Discovered while signed in, because a language control usually lives in a
    # signed-in user's settings rather than on the public page.
    locale = await discovery.locale_mechanism(next(iter(states.values()), None))
    print(f"locale mechanism: {locale.kind} — {locale.detail}", file=sys.stderr)
    return reports, states, locale


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
    if spec.get("type") == "click":
        # A protocol is played by pressing things. This stays inside the same
        # restriction as submit_form — a selector naming an element on the page,
        # never a string of script — so widening the grammar to cover ordered
        # protocols does not widen what a declaration is able to execute.
        selector = _string(spec.get("selector"), f"{name}.action.selector", source)

        async def click(page: object) -> None:
            await page.locator(selector).click()

        return click, FormAction(selector, (), (), kind="click")
    if spec.get("type") != "submit_form":
        raise _scenario_error(source, f"{name}.action.type must be 'submit_form' or 'click'")
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


def _positive_number(value: Any, name: str, source: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise _scenario_error(source, f"{name} must be a non-negative number")
    return float(value)


def _positive_int(value: Any, name: str, source: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _scenario_error(source, f"{name} must be a non-negative integer")
    return value


def _effect(spec: Any, name: str, source: str) -> tuple[object, EffectExpectation]:
    if not isinstance(spec, dict):
        raise _scenario_error(source, f"{name}.effect must be an object")
    effect_type = spec.get("type")
    if effect_type == "visible":
        selector = _string(spec.get("selector"), f"{name}.effect.selector", source)

        async def visible(page: object) -> bool:
            return bool(await page.locator(selector).is_visible())

        return visible, EffectExpectation("visible", selector=selector)
    if effect_type == "text_equals":
        # Presence is not content. A board cell, a status line and a counter are
        # all permanently "visible"; what changes is what they say.
        selector = _string(spec.get("selector"), f"{name}.effect.selector", source)
        expected = _string(spec.get("equals"), f"{name}.effect.equals", source)

        async def text_equals(page: object) -> bool:
            return (await page.locator(selector).inner_text()).strip() == expected

        return text_equals, EffectExpectation("text_equals", selector=selector, equals=expected)
    if effect_type in {"audio_received", "audio_audible", "video_received"}:
        # Presence is not perception. A muted participant negotiates the call and
        # receives packets exactly like a listening one, so the threshold is on
        # energy and decoded frames rather than on a track existing.
        expectation = MediaExpectation(
            kind=effect_type,
            min_level=_positive_number(spec.get("min_level", 0.01), f"{name}.effect.min_level", source),
            min_packets=_positive_int(spec.get("min_packets", 5), f"{name}.effect.min_packets", source),
            min_frames=_positive_int(spec.get("min_frames", 5), f"{name}.effect.min_frames", source),
        )
        script, arguments = media_probe(expectation)

        async def media(page: object) -> bool:
            return perceived(expectation, await page.evaluate(script, arguments))

        media.__name__ = expectation.describe()
        return media, EffectExpectation(effect_type)
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
    raise _scenario_error(
        source, f"{name}.effect.type must be 'visible', 'text_equals', 'json_contains', or a media kind"
    )


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


def audiences_from_data(data: Any, start_url: str, *, source: str = "declaration") -> list[AudienceScenario]:
    """Parse one-actor, many-observer declarations from the same vocabulary.

    An audience differs from a capability in what it is asking. A capability
    repeats the same action as several roles and asks who may perform it. An
    audience performs the action once and asks who perceives it — which is why
    the observers run concurrently and why each carries its own expectation,
    including a negative one. "Nobody outside the thread saw it" is a claim that
    can only be made by watching the people who should not have.
    """
    entries = data.get("audiences") if isinstance(data, dict) else data
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise _scenario_error(source, "audiences must be a list")
    result: list[AudienceScenario] = []
    for index, spec in enumerate(entries, start=1):
        name = f"audience {index}"
        if not isinstance(spec, dict):
            raise _scenario_error(source, f"{name} must be an object")
        label = spec.get("label") if isinstance(spec.get("label"), str) and spec.get("label") else name
        surface = Surface(SurfaceKind.ROUTE, urljoin(start_url, _string(spec.get("surface"), f"{name}.surface", source)))
        deadline_ms = spec.get("deadline_ms", 5_000)
        if not isinstance(deadline_ms, int) or isinstance(deadline_ms, bool) or deadline_ms < 1:
            raise _scenario_error(source, f"{name}.deadline_ms must be a positive integer")
        action, _ = _action(spec.get("action"), name, source)

        actor_spec = spec.get("actor")
        if not isinstance(actor_spec, dict):
            raise _scenario_error(source, f"{name}.actor must be an object")
        actor = _audience_context(actor_spec, f"{name}.actor", source)
        actor_surface = actor_spec.get("surface")

        declared = spec.get("observers")
        if not isinstance(declared, list) or not declared:
            raise _scenario_error(source, f"{name}.observers must be a non-empty list")
        observers: list[Observer] = []
        for position, entry in enumerate(declared, start=1):
            where = f"{name}.observers[{position}]"
            if not isinstance(entry, dict):
                raise _scenario_error(source, f"{where} must be an object")
            effect, _ = _effect(entry.get("effect"), where, source)
            expect_visible = entry.get("expect_visible", True)
            if not isinstance(expect_visible, bool):
                raise _scenario_error(source, f"{where}.expect_visible must be true or false")
            own = entry.get("surface")
            observers.append(Observer(
                name=_string(entry.get("name"), f"{where}.name", source),
                context=_audience_context(entry, where, source),
                effect=effect,
                expect_visible=expect_visible,
                surface=(
                    Surface(SurfaceKind.ROUTE, urljoin(start_url, own))
                    if isinstance(own, str) and own else None
                ),
            ))
        if len({observer.name for observer in observers}) != len(observers):
            raise _scenario_error(source, f"{name}.observers must have distinct names")
        result.append(AudienceScenario(
            surface=(
                Surface(SurfaceKind.ROUTE, urljoin(start_url, actor_surface))
                if isinstance(actor_surface, str) and actor_surface else surface
            ),
            actor=actor, action=action, observers=tuple(observers), deadline_ms=deadline_ms, label=label,
        ))
    return result


def _audience_context(spec: dict[str, Any], name: str, source: str) -> Context:
    privilege = spec.get("privilege", "member")
    try:
        return Context(privilege=Privilege(privilege), varies=Axis.RELATIONAL)
    except ValueError as error:
        raise _scenario_error(source, f"{name}.privilege must be anon, member, or owner") from error


def choreographies_from_data(data: Any, start_url: str, *, source: str = "declaration") -> list[Choreography]:
    """Parse ordered multi-session protocols from the same restricted vocabulary.

    A choreography differs from every other declaration in one way that matters:
    its participants are named, and the names are the only thing tying a step's
    actor and its expectations together. So the names are resolved here, at parse
    time, rather than at play time — a step naming a participant who was never
    declared is a broken declaration, not a finding about the application.
    """
    entries = data.get("choreographies") if isinstance(data, dict) else data
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise _scenario_error(source, "choreographies must be a list")
    result: list[Choreography] = []
    for index, spec in enumerate(entries, start=1):
        name = f"choreography {index}"
        if not isinstance(spec, dict):
            raise _scenario_error(source, f"{name} must be an object")
        label = spec.get("label") if isinstance(spec.get("label"), str) and spec.get("label") else name
        surface = Surface(SurfaceKind.ROUTE, urljoin(start_url, _string(spec.get("surface"), f"{name}.surface", source)))

        declared = spec.get("participants")
        if not isinstance(declared, list) or len(declared) < 2:
            raise _scenario_error(source, f"{name}.participants must be a list of at least two participants")
        participants: list[Participant] = []
        for position, entry in enumerate(declared, start=1):
            where = f"{name}.participants[{position}]"
            if not isinstance(entry, dict):
                raise _scenario_error(source, f"{where} must be an object")
            privilege = entry.get("privilege", "member")
            try:
                context = Context(privilege=Privilege(privilege), varies=Axis.RELATIONAL)
            except ValueError as error:
                raise _scenario_error(source, f"{where}.privilege must be anon, member, or owner") from error
            own_surface = entry.get("surface")
            participants.append(Participant(
                name=_string(entry.get("name"), f"{where}.name", source),
                context=context,
                storage_state=None,
                surface=(
                    Surface(SurfaceKind.ROUTE, urljoin(start_url, own_surface))
                    if isinstance(own_surface, str) and own_surface else None
                ),
            ))
        names = {participant.name for participant in participants}
        if len(names) != len(participants):
            raise _scenario_error(source, f"{name}.participants must have distinct names")

        declared_steps = spec.get("steps")
        if not isinstance(declared_steps, list) or not declared_steps:
            raise _scenario_error(source, f"{name}.steps must be a non-empty list")
        steps: list[Step] = []
        for position, entry in enumerate(declared_steps, start=1):
            where = f"{name}.steps[{position}]"
            if not isinstance(entry, dict):
                raise _scenario_error(source, f"{where} must be an object")
            actor = _string(entry.get("actor"), f"{where}.actor", source)
            if actor not in names:
                raise _scenario_error(source, f"{where}.actor names {actor!r}, which is not a participant")
            action, _ = _action(entry.get("action"), where, source)
            deadline_ms = entry.get("deadline_ms", 5_000)
            if not isinstance(deadline_ms, int) or isinstance(deadline_ms, bool) or deadline_ms < 1:
                raise _scenario_error(source, f"{where}.deadline_ms must be a positive integer")
            expectations = entry.get("expect", [])
            if not isinstance(expectations, list):
                raise _scenario_error(source, f"{where}.expect must be a list")
            expects: list[Expect] = []
            for slot, want in enumerate(expectations, start=1):
                spot = f"{where}.expect[{slot}]"
                if not isinstance(want, dict):
                    raise _scenario_error(source, f"{spot} must be an object")
                who = _string(want.get("participant"), f"{spot}.participant", source)
                if who not in names:
                    raise _scenario_error(source, f"{spot}.participant names {who!r}, which is not a participant")
                effect, _ = _effect(want.get("effect"), spot, source)
                visible = want.get("visible", True)
                if not isinstance(visible, bool):
                    raise _scenario_error(source, f"{spot}.visible must be true or false")
                note = want.get("note", "")
                if not isinstance(note, str):
                    raise _scenario_error(source, f"{spot}.note must be a string")
                expects.append(Expect(participant=who, effect=effect, visible=visible, note=note))
            steps.append(Step(
                label=_string(entry.get("label"), f"{where}.label", source),
                actor=actor, action=action, expect=tuple(expects), deadline_ms=deadline_ms,
            ))
        result.append(Choreography(
            surface=surface, participants=tuple(participants), steps=tuple(steps), label=label,
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
    if scenarios is None and isinstance(data, dict) and ({"capabilities", "choreographies", "audiences"} & set(data)):
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


def _declaration(path: Path) -> Any:
    """Read the scenario file once, reporting where it is malformed."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise _scenario_error(str(path), "file does not exist") from error
    except OSError as error:
        raise _scenario_error(str(path), f"could not read file: {error}") from error
    except json.JSONDecodeError as error:
        raise _scenario_error(str(path), f"invalid JSON at line {error.lineno}, column {error.colno}") from error


def _relational_scenarios(path: Path, start_url: str) -> list[RelationalScenario]:
    return relational_scenarios_from_data(_declaration(path), start_url, source=str(path))


def run_summary(
    summary: Any,
    *,
    sign_ins: list[dict[str, object]],
    locale: Any,
    capability_scenarios: list[Any],
    audiences: list[Any],
    choreographies: list[Any],
    relational_scenarios: list[Any] | None,
    specialists: list[Any],
    semantics: Any,
    delivery: Any,
    triage: Any,
) -> dict[str, Any]:
    """Assemble the run report.

    Extracted from the command so it can be checked without launching a browser.
    This dict is the run's primary artifact — the thing a reader opens to decide
    whether a sweep did what it claims — and it was previously a literal inside
    an async function that needed Chromium to evaluate at all.
    """
    counts: dict[str, int] = {}
    for finding in summary.findings:
        counts[finding.severity.value] = counts.get(finding.severity.value, 0) + 1
    exercised = [decision for decision in summary.axis_applicability if decision.applicable]
    not_applicable = [decision for decision in summary.axis_applicability if not decision.applicable]
    return {
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
        "discovery": {
            "sign_ins": sign_ins,
            "locale_mechanism": locale.report(),
        },
        "capabilities": {
            "ran": summary.capabilities_exercised,
            "declared": len(capability_scenarios),
            "proposed_by_model": summary.capabilities_proposed_exercised,
            "roles_exercised": summary.capability_roles_exercised,
        },
        "audiences": {
            "ran": summary.audiences_exercised,
            "declared": len(audiences),
            "observers": summary.audience_observers_exercised,
        },
        "choreographies": {
            "ran": summary.choreographies_exercised,
            "declared": len(choreographies),
            "steps": summary.choreography_steps_exercised,
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
    }


async def _run(args: argparse.Namespace) -> int:
    from playwright.async_api import async_playwright

    # Read once. Every scenario shape lives in the same file, and each used to
    # re-open and re-parse it: four reads of one path, and four chances for the
    # four parsers to disagree about a file somebody edited between them.
    declaration = _declaration(args.relational_scenarios) if args.relational_scenarios else None
    source = str(args.relational_scenarios) if args.relational_scenarios else "declaration"
    relational_scenarios = (
        relational_scenarios_from_data(declaration, args.url, source=source)
        if declaration is not None else None
    )
    audiences = audiences_from_data(declaration, args.url, source=source) if declaration is not None else []
    choreographies = (
        choreographies_from_data(declaration, args.url, source=source) if declaration is not None else []
    )
    capability_scenarios = (
        capability_scenarios_from_data(declaration, args.url, source=source) if declaration is not None else []
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
            sign_ins, discovered_states, locale = await _discover_sessions(args, browser)
            summary = await _conduct(
                args, browser, relational_scenarios, specialists, proposer,
                capability_scenarios=capability_scenarios,
                choreographies=choreographies,
                audiences=audiences,
                discovered_states=discovered_states,
                locale_kind=locale.kind,
            )
        finally:
            await browser.close()

    delivery = _deliver(args, summary)
    triage = GemmaTriage().group(summary.findings)
    # The console reads the feed, not this process's stdout. A grouping that
    # exists only in the terminal cannot be checked against the published
    # evidence later, so it is appended to the feed as its own event — carrying
    # the finding ids, so a reader can confirm the model only ever partitioned
    # findings the deterministic layers had already produced.
    _append_triage(summary.feed_path, triage)
    print(json.dumps(run_summary(
        summary,
        sign_ins=sign_ins,
        locale=locale,
        capability_scenarios=capability_scenarios,
        audiences=audiences,
        choreographies=choreographies,
        relational_scenarios=relational_scenarios,
        specialists=specialists,
        semantics=semantics,
        delivery=delivery,
        triage=triage,
    ), indent=2))
    print(f"\nconsole: open console/index.html?feed=../{summary.feed_path}", file=sys.stderr)
    # A run that found nothing is a finished run, not a failed one.
    return 0


async def _conduct(
    args: argparse.Namespace, browser: object, relational_scenarios: list[RelationalScenario] | None,
    specialists: list[object] | None = None,
    proposer: ScenarioProposer | None = None,
    capability_scenarios: list[CapabilityScenario] | None = None,
    choreographies: list[Choreography] | None = None,
    audiences: list[AudienceScenario] | None = None,
    discovered_states: dict[str, Any] | None = None,
    locale_kind: str | None = None,
) -> object:
    """Make the CLI-to-conductor contract testable without launching Chromium."""
    options: dict[str, object] = {
        "browser": browser,
        "specialists": _specialists(args.no_vision) if specialists is None else specialists,
        # Declared states win over discovered ones: an explicit --storage-state
        # is a caller saying they already know better than the discovery pass.
        "storage_states": {**(discovered_states or {}), **_storage_states(args.storage_state)} or None,
        "max_surfaces": args.max_surfaces,
        "settle_ms": args.settle_ms,
        "deny": args.deny,
    }
    if relational_scenarios is not None:
        options["relational_scenarios"] = relational_scenarios
    if capability_scenarios:
        options["capability_scenarios"] = capability_scenarios
    if choreographies:
        options["choreographies"] = choreographies
    if audiences:
        options["audiences"] = audiences
    if args.propose_scenarios:
        options["scenario_proposer"] = proposer or ScenarioProposer()
        options["proposal_validator"] = relational_scenarios_from_data
        options["capability_validator"] = capability_scenarios_from_data
    conductor = Conductor(args.url, args.out, **options)
    # What the discovery pass established about this application, handed to the
    # gate that decides whether the locale axis is worth judging at all.
    conductor.locale_mechanism = locale_kind
    return await conductor.conduct()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
