"""Declared axis values: the questions are fixed, the vocabulary is yours.

The one-axis derivation rule is the architecture and stays closed. What these
tests pin is that the *values* on the locale and viewport axes are open — any
BCP 47 tag, any WIDTHxHEIGHT — exactly as the privilege axis was opened to
declared roles, and that leaving everything undeclared produces byte-identical
behaviour to what shipped before the axes were declarable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from parallax import cli, config
from parallax.__main__ import _declared_locales, _declared_viewports, _parse
from parallax.compositor import Compositor
from parallax.types import (
    Axis,
    Locale,
    LocaleSpec,
    Viewport,
    derive_witnesses,
)

from tests.test_cli import _captured, write_config


# ---------------------------------------------------------------- direction

def test_direction_is_derived_from_the_language_not_declared() -> None:
    assert LocaleSpec("he").direction == "rtl"
    assert LocaleSpec("fa").direction == "rtl"
    assert LocaleSpec("ur").direction == "rtl"
    assert LocaleSpec("ar-EG").direction == "rtl"
    assert LocaleSpec("fr").direction == "ltr"
    assert LocaleSpec("ja").direction == "ltr"


def test_a_locale_needs_a_tag() -> None:
    with pytest.raises(ValueError):
        LocaleSpec("  ")


# ---------------------------------------------------------------- derivation

def test_undeclared_axes_derive_exactly_what_they_always_did() -> None:
    assert [context.name for context in derive_witnesses()] == [
        context.name for context in derive_witnesses(locales=None, viewports=None)
    ]
    assert len(derive_witnesses()) == 7


def test_declared_values_add_one_witness_each_never_a_product() -> None:
    witnesses = derive_witnesses(
        locales=[LocaleSpec("fr"), LocaleSpec("he")],
        viewports=[Viewport("320x568", 320, 568)],
    )
    locale_witnesses = [w for w in witnesses if w.varies is Axis.LOCALE]
    viewport_witnesses = [w for w in witnesses if w.varies is Axis.VIEWPORT]
    assert [w.locale.value for w in locale_witnesses] == ["fr", "he"]
    assert [w.viewport.width for w in viewport_witnesses] == [320]
    # Two locales and one viewport changed the count linearly: 7 - 1 - 2 + 2 + 1.
    assert len(witnesses) == 7

    # Every witness still varies exactly one axis from the same baseline.
    baseline = witnesses[0]
    for witness in locale_witnesses:
        assert (witness.theme, witness.viewport, witness.privilege) == (
            baseline.theme, baseline.viewport, baseline.privilege,
        )


def test_an_empty_declaration_is_a_decision_not_an_omission() -> None:
    witnesses = derive_witnesses(locales=[], viewports=[])
    assert not [w for w in witnesses if w.varies in {Axis.LOCALE, Axis.VIEWPORT}]


# ---------------------------------------------------------------- the wall

def test_the_wall_grows_rows_for_declared_witnesses() -> None:
    ten = [f"witness-{index}" for index in range(10)]
    compositor = Compositor(ten, tile_size=(40, 30))
    wall = compositor._paint_wall({})
    assert wall.size == (4 * 40, 3 * 30)

    seven = Compositor([f"w{index}" for index in range(7)], tile_size=(40, 30))
    assert seven._paint_wall({}).size == (4 * 40, 2 * 30)


# ---------------------------------------------------------------- the flags

def test_flags_parse_into_typed_values() -> None:
    args = _parse(["https://x.test", "--locale", "he", "--viewport", "320x568"])
    assert [tag.value for tag in _declared_locales(args.locale)] == ["he"]
    [viewport] = _declared_viewports(args.viewport)
    assert (viewport.width, viewport.height, viewport.name) == (320, 568, "320x568")


def test_absent_flags_stay_none_so_defaults_survive() -> None:
    args = _parse(["https://x.test"])
    assert _declared_locales(args.locale) is None
    assert _declared_viewports(args.viewport) is None


def test_a_malformed_viewport_names_the_expected_shape() -> None:
    with pytest.raises(SystemExit, match="WIDTHxHEIGHT"):
        _declared_viewports(["wide"])


# ---------------------------------------------------------------- the file

def test_axes_declared_in_the_project_file_become_flags(tmp_path: Path, monkeypatch) -> None:
    write_config(
        tmp_path,
        '[target]\nurl = "https://app.test"\n'
        '[axes]\nlocales = ["fr", "he"]\nviewports = ["320x568"]\n',
    )
    calls = _captured(monkeypatch)
    monkeypatch.chdir(tmp_path)

    assert cli.main(["sweep"]) == 0
    [argv] = calls
    assert argv[argv.index("--locale") : argv.index("--locale") + 2] == ["--locale", "fr"]
    assert argv.count("--locale") == 2
    assert argv[argv.index("--viewport") : argv.index("--viewport") + 2] == ["--viewport", "320x568"]


def test_an_absent_axes_table_declares_nothing(tmp_path: Path, monkeypatch) -> None:
    write_config(tmp_path, '[target]\nurl = "https://app.test"\n')
    calls = _captured(monkeypatch)
    monkeypatch.chdir(tmp_path)

    assert cli.main(["sweep"]) == 0
    [argv] = calls
    assert "--locale" not in argv
    assert "--viewport" not in argv
    settings = config.load(tmp_path / config.CONFIG_NAME)
    assert settings.locales is None
    assert settings.viewports is None
