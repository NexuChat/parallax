from __future__ import annotations

import json

from parallax.proposer import BaselineObservation, ObservedAffordance, ScenarioProposer


class FakeModels:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response: object) -> None:
        self.models = FakeModels(response)


class TextResponse:
    def __init__(self, text: str) -> None:
        self.text = text


def observation() -> BaselineObservation:
    return BaselineObservation(
        start_url="https://app.example.test/workspace",
        routes=("https://app.example.test/workspace/threads",),
        affordances=(
            ObservedAffordance(
                "https://app.example.test/workspace/threads", "form.revoke-form", "Remove from workspace", "form"
            ),
            ObservedAffordance(
                "https://app.example.test/workspace/threads", "#message", "Write a message", "control"
            ),
        ),
        endpoints=("https://app.example.test/workspace/api/messages",),
        roles=("owner", "member", "anon"),
    )


def candidate(**overrides: object) -> dict[str, object]:
    scenario: dict[str, object] = {
        "type": "revocation",
        "surface": "/workspace/threads",
        "sender": "owner",
        "receiver": "member",
        "action": {"type": "submit_form", "form": "form.revoke-form", "checks": [], "fills": []},
        "effect": {
            "type": "json_contains",
            "url": "api/messages?since=0",
            "items": "messages",
            "field": "text",
            "equals": "Existing message",
        },
        "max_lag_ms": 100,
        "deadline_ms": 3_000,
    }
    scenario.update(overrides)
    return scenario


def test_proposer_uses_an_injected_client_and_keeps_only_observed_references() -> None:
    fake = FakeClient(TextResponse('{"scenarios": [' + json.dumps(candidate()) + "]}"))

    result = ScenarioProposer(client=fake).propose(observation())

    assert result.proposed == 1
    assert len(result.candidates) == 1
    assert result.rejections == ()
    assert result.note is None
    assert len(fake.models.calls) == 1
    assert fake.models.calls[0]["model"] == "gemini-3.6-flash"
    assert "form.revoke-form" in fake.models.calls[0]["contents"]


def test_proposer_drops_invented_roles_routes_and_selectors_before_validation() -> None:
    invented_role = candidate(sender="admin")
    invented_route = candidate(surface="/workspace/hidden")
    invented_selector = candidate(action={"type": "submit_form", "form": "form.destroy", "checks": [], "fills": []})
    fake = FakeClient(TextResponse(json.dumps({"scenarios": [invented_role, invented_route, invented_selector]})))

    result = ScenarioProposer(client=fake).propose(observation())

    assert result.proposed == 3
    assert result.candidates == ()
    assert [rejection.index for rejection in result.rejections] == [1, 2, 3]
    assert "role" in result.rejections[0].reason
    assert "surface" in result.rejections[1].reason
    assert "form" in result.rejections[2].reason


def test_proposer_reports_a_bad_model_response_instead_of_silently_returning_zero() -> None:
    fake = FakeClient(TextResponse("not JSON"))
    proposer = ScenarioProposer(client=fake)

    result = proposer.propose(observation())

    assert result.proposed == 0
    assert result.candidates == ()
    assert result.note == "Gemini did not return a JSON scenarios list"
    assert proposer.calls_attempted == proposer.calls_succeeded == 1
    assert proposer.last_error == "Gemini did not return a JSON scenarios list"


def test_proposer_rejects_model_fields_outside_the_data_only_grammar() -> None:
    fake = FakeClient(TextResponse(json.dumps({"scenarios": [candidate(script="alert('no')")]})))

    result = ScenarioProposer(client=fake).propose(observation())

    assert result.candidates == ()
    assert result.rejections[0].reason == "script is outside the relational scenario grammar"


def test_proposer_selects_vertex_without_an_ai_studio_fallback(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "configured-project")
    monkeypatch.setenv("GEMINI_API_KEY", "depleted-key")
    captured: dict[str, object] = {}
    fake = FakeClient(TextResponse('{"scenarios": []}'))

    def factory(**kwargs: object) -> FakeClient:
        captured.update(kwargs)
        return fake

    proposer = ScenarioProposer(token_fetcher=lambda: "test-bearer-token", client_factory=factory)
    proposer.propose(observation())

    assert proposer.route == "vertex"
    assert captured["vertexai"] is True
    assert captured["project"] == "configured-project"
    assert captured["credentials"].token == "test-bearer-token"
