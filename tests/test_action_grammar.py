"""The action and effect vocabulary a declaration is allowed to use.

Every scenario kind — relational, capability, choreography — shares one parser,
so widening the grammar for one widens what all of them can execute. These tests
pin the boundary: selectors and literal values, never a string of script.
"""

from __future__ import annotations

import asyncio

import pytest

from parallax.__main__ import _action, _effect
from parallax.emitter import _effect_expression
from parallax.types import EffectExpectation, FormAction


class FakeLocator:
    def __init__(self, log: list[str], selector: str, text: str = "") -> None:
        self._log, self._selector, self._text = log, selector, text

    async def click(self) -> None:
        self._log.append(f"click:{self._selector}")

    async def inner_text(self) -> str:
        return self._text

    async def is_visible(self) -> bool:
        return True


class FakePage:
    def __init__(self, text: str = "") -> None:
        self.log: list[str] = []
        self._text = text

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self.log, selector, self._text)


def test_a_click_action_presses_exactly_what_it_names() -> None:
    action, replay = _action({"type": "click", "selector": "#accept"}, "step", "test")
    page = FakePage()

    asyncio.run(action(page))

    assert page.log == ["click:#accept"]
    assert replay == FormAction("#accept", (), (), kind="click")


def test_a_click_replays_as_a_click_rather_than_a_form_submission() -> None:
    """requestSubmit() on a button throws — a spec that fails for the wrong reason."""
    from parallax.emitter import _action_lines

    # Only the action is read here, so a stand-in avoids building a whole run.
    clicked = type("Replay", (), {"action": FormAction("#accept", (), (), kind="click")})()
    submitted = type("Replay", (), {"action": FormAction("form.composer")})()

    assert ".click();" in _action_lines("page", clicked)
    assert "requestSubmit" not in _action_lines("page", clicked)
    assert "requestSubmit" in _action_lines("page", submitted)


def test_text_equals_compares_content_not_presence() -> None:
    """A board cell is always visible; what changes is what it says."""
    effect, replay = _effect({"type": "text_equals", "selector": "#cell-4", "equals": "X"}, "step", "test")

    assert asyncio.run(effect(FakePage("X"))) is True
    assert asyncio.run(effect(FakePage("O"))) is False
    assert replay == EffectExpectation("text_equals", selector="#cell-4", equals="X")


def test_text_equals_ignores_the_whitespace_a_template_adds() -> None:
    effect, _ = _effect({"type": "text_equals", "selector": "#status", "equals": "playing"}, "step", "test")

    assert asyncio.run(effect(FakePage("\n  playing \n"))) is True


def test_text_equals_becomes_a_generated_assertion() -> None:
    expression = _effect_expression("page", EffectExpectation("text_equals", selector="#status", equals="playing"))

    assert expression is not None
    assert "innerText()" in expression and '"playing"' in expression


def test_an_unknown_action_type_is_refused() -> None:
    with pytest.raises(SystemExit) as error:
        _action({"type": "evaluate", "script": "alert(1)"}, "step", "test")

    assert "must be 'submit_form' or 'click'" in str(error.value)


def test_an_unknown_effect_type_is_refused_and_says_what_is_allowed() -> None:
    with pytest.raises(SystemExit) as error:
        _effect({"type": "regex_matches", "pattern": ".*"}, "step", "test")

    assert "text_equals" in str(error.value)


def test_a_click_without_a_selector_is_refused() -> None:
    with pytest.raises(SystemExit) as error:
        _action({"type": "click"}, "step", "test")

    assert "action.selector must be a non-empty string" in str(error.value)
