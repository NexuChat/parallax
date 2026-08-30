from __future__ import annotations

import json
import asyncio

import pytest

from parallax import __main__ as cli


def test_sweep_without_relational_scenario_file_keeps_conductor_default(monkeypatch) -> None:
    args = cli._parse(["https://app.example.test"])
    received: dict[str, object] = {}

    class FakeConductor:
        def __init__(self, _url, _out, **options):
            received.update(options)

        async def conduct(self):
            return object()

    monkeypatch.setattr(cli, "Conductor", FakeConductor)
    monkeypatch.setattr(cli, "_specialists", lambda _no_vision: [])
    asyncio.run(cli._conduct(args, object(), None))

    assert args.relational_scenarios is None
    assert "relational_scenarios" not in received


def test_relational_scenario_file_builds_safe_conductor_scenarios(tmp_path, monkeypatch) -> None:
    path = tmp_path / "relational.json"
    path.write_text(json.dumps({"scenarios": [{
        "surface": "/threads",
        "sender": "owner",
        "receiver": "member",
        "action": {
            "type": "submit_form",
            "form": "form.composer",
            "checks": ["input[value='quiet']"],
            "fills": [{"selector": "#message", "value": "Ship it"}],
        },
        "effect": {
            "type": "json_contains",
            "url": "api/messages?since=0",
            "items": "messages",
            "field": "text",
            "equals": "Ship it",
        },
        "deadline_ms": 3000,
    }]}), encoding="utf-8")

    scenarios = cli._relational_scenarios(path, "https://app.example.test/base/")
    received: dict[str, object] = {}

    class FakeConductor:
        def __init__(self, _url, _out, **options):
            received.update(options)

        async def conduct(self):
            return object()

    monkeypatch.setattr(cli, "Conductor", FakeConductor)
    monkeypatch.setattr(cli, "_specialists", lambda _no_vision: [])
    asyncio.run(cli._conduct(cli._parse(["https://app.example.test", "--relational-scenarios", str(path)]), object(), scenarios))

    assert len(scenarios) == 1
    scenario = scenarios[0]
    assert scenario.surface.path == "https://app.example.test/threads"
    assert scenario.sender.privilege.value == "owner"
    assert scenario.receiver.privilege.value == "member"
    assert scenario.deadline_ms == 3000
    assert scenario.replay is not None
    assert scenario.replay.action.form == "form.composer"
    assert scenario.replay.action.checks == ("input[value='quiet']",)
    assert scenario.replay.action.fills == (("#message", "Ship it"),)
    assert scenario.replay.effect.kind == "json_contains"
    assert scenario.replay.effect.url == "api/messages?since=0"
    assert received["relational_scenarios"] == scenarios


def test_revocation_scenario_uses_the_same_safe_action_and_effect_vocabulary(tmp_path) -> None:
    path = tmp_path / "revocation.json"
    path.write_text(json.dumps({"scenarios": [{
        "type": "revocation",
        "surface": "/workspace",
        "sender": "owner",
        "receiver": "member",
        "action": {"type": "submit_form", "form": "form.disable"},
        "effect": {"type": "visible", "selector": "#workspace"},
        "max_lag_ms": 50,
        "deadline_ms": 200,
    }]}), encoding="utf-8")

    scenario = cli._relational_scenarios(path, "https://app.example.test")[0]

    assert scenario.kind == "revocation"
    assert scenario.max_lag_ms == 50
    assert scenario.deadline_ms == 200
    assert scenario.replay is not None
    assert scenario.replay.max_lag_ms == 50
    assert scenario.replay.effect.selector == "#workspace"


def test_revocation_scenario_requires_an_explicit_acceptable_lag(tmp_path) -> None:
    path = tmp_path / "revocation.json"
    path.write_text(json.dumps({"scenarios": [{
        "type": "revocation",
        "surface": "/workspace",
        "sender": "owner",
        "receiver": "member",
        "action": {"type": "submit_form", "form": "form.disable"},
        "effect": {"type": "visible", "selector": "#workspace"},
        "deadline_ms": 200,
    }]}), encoding="utf-8")

    with pytest.raises(SystemExit, match="scenario 1.max_lag_ms must be a non-negative integer"):
        cli._relational_scenarios(path, "https://app.example.test")


def test_revocation_observation_window_must_exceed_acceptable_lag(tmp_path) -> None:
    path = tmp_path / "revocation.json"
    path.write_text(json.dumps({"scenarios": [{
        "type": "revocation",
        "surface": "/workspace",
        "sender": "owner",
        "receiver": "member",
        "action": {"type": "submit_form", "form": "form.disable"},
        "effect": {"type": "visible", "selector": "#workspace"},
        "max_lag_ms": 200,
        "deadline_ms": 200,
    }]}), encoding="utf-8")

    with pytest.raises(SystemExit, match="scenario 1.max_lag_ms must be below deadline_ms"):
        cli._relational_scenarios(path, "https://app.example.test")


def test_relational_scenario_rejects_unknown_scenario_types(tmp_path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps({"scenarios": [{"type": "javascript"}]}), encoding="utf-8")

    with pytest.raises(SystemExit, match="scenario 1.type"):
        cli._relational_scenarios(path, "https://app.example.test")


@pytest.mark.parametrize("payload, problem", [
    ({"scenarios": [{"surface": "/threads"}]}, "scenario 1.sender"),
    ({"scenarios": "not a list"}, "scenarios must be a list"),
])
def test_malformed_relational_scenario_file_names_the_problem(tmp_path, payload, problem) -> None:
    path = tmp_path / "relational.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit, match=problem):
        cli._relational_scenarios(path, "https://app.example.test")
