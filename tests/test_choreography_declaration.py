"""The declaration format for ordered protocols, and its refusals.

A choreography is the only declaration whose parts refer to each other: a step
names an actor, an expectation names an observer, and both are only meaningful
against the participant list. Resolving those names at parse time is what keeps
a typo from being reported as a finding about the application.
"""

from __future__ import annotations

import pytest

from parallax.__main__ import choreographies_from_data
from parallax.types import Privilege


HOST = "http://app.example/"


def declaration(**overrides: object) -> dict[str, object]:
    spec: dict[str, object] = {
        "label": "invite and play",
        "surface": "/game",
        "participants": [{"name": "amira"}, {"name": "samir", "privilege": "owner"}],
        "steps": [{
            "label": "amira invites samir",
            "actor": "amira",
            "action": {"type": "click", "selector": "#send-invite"},
            "expect": [{"participant": "samir", "effect": {"type": "visible", "selector": "#accept"}}],
        }],
    }
    spec.update(overrides)
    return {"choreographies": [spec]}


def parse(data: dict[str, object]) -> list[object]:
    return choreographies_from_data(data, HOST, source="test")


def test_a_declaration_becomes_a_playable_protocol() -> None:
    [choreography] = parse(declaration())

    assert choreography.label == "invite and play"
    assert choreography.surface.path == "http://app.example/game"
    assert [p.name for p in choreography.participants] == ["amira", "samir"]
    assert choreography.participants[1].context.privilege is Privilege.OWNER
    assert choreography.steps[0].expect[0].visible is True


def test_each_participant_may_open_their_own_address() -> None:
    """Identity is part of the URL in a fixture with no accounts."""
    [choreography] = parse(declaration(participants=[
        {"name": "amira", "surface": "/game?me=amira"},
        {"name": "samir", "surface": "/game?me=samir"},
    ]))

    assert choreography.participants[0].surface.path == "http://app.example/game?me=amira"
    assert choreography.participants[1].surface.path == "http://app.example/game?me=samir"


def test_a_participant_without_an_address_shares_the_choreography_surface() -> None:
    [choreography] = parse(declaration())

    assert choreography.participants[0].surface is None


def test_a_negative_expectation_survives_the_parse() -> None:
    """An invitation everybody can see is not an invitation."""
    [choreography] = parse(declaration(steps=[{
        "label": "amira invites samir",
        "actor": "amira",
        "action": {"type": "click", "selector": "#send-invite"},
        "expect": [{
            "participant": "amira",
            "effect": {"type": "visible", "selector": "#accept"},
            "visible": False,
            "note": "and must not be offered to its sender",
        }],
    }]))

    expect = choreography.steps[0].expect[0]
    assert expect.visible is False
    assert expect.note == "and must not be offered to its sender"


def test_a_step_naming_an_undeclared_actor_is_refused_at_parse_time() -> None:
    """Otherwise the run reports a typo as a fault in the application."""
    with pytest.raises(SystemExit) as error:
        parse(declaration(steps=[{
            "label": "ghost moves",
            "actor": "ghost",
            "action": {"type": "click", "selector": "#cell-0"},
        }]))

    assert "names 'ghost', which is not a participant" in str(error.value)


def test_an_expectation_naming_an_undeclared_observer_is_refused() -> None:
    with pytest.raises(SystemExit) as error:
        parse(declaration(steps=[{
            "label": "amira invites",
            "actor": "amira",
            "action": {"type": "click", "selector": "#send-invite"},
            "expect": [{"participant": "nobody", "effect": {"type": "visible", "selector": "#accept"}}],
        }]))

    assert "names 'nobody', which is not a participant" in str(error.value)


def test_a_protocol_needs_more_than_one_session_to_be_a_protocol() -> None:
    with pytest.raises(SystemExit) as error:
        parse(declaration(participants=[{"name": "alone"}]))

    assert "at least two participants" in str(error.value)


def test_two_participants_may_not_share_a_name() -> None:
    """Names are the only thing binding a step to a session."""
    with pytest.raises(SystemExit) as error:
        parse(declaration(participants=[{"name": "amira"}, {"name": "amira"}]))

    assert "distinct names" in str(error.value)


def test_a_protocol_with_no_steps_is_refused() -> None:
    with pytest.raises(SystemExit) as error:
        parse(declaration(steps=[]))

    assert "non-empty list" in str(error.value)


def test_a_file_with_no_choreographies_declares_none() -> None:
    assert choreographies_from_data({"scenarios": []}, HOST, source="test") == []
    assert choreographies_from_data({}, HOST, source="test") == []


def test_a_declaration_cannot_smuggle_in_script() -> None:
    """The grammar admits selectors, never code — the reason it is data-only."""
    with pytest.raises(SystemExit) as error:
        parse(declaration(steps=[{
            "label": "run something",
            "actor": "amira",
            "action": {"type": "evaluate", "script": "fetch('https://evil.example')"},
        }]))

    assert "action.type must be" in str(error.value)
