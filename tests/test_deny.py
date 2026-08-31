"""The written "never this" an agent needs before it presses things.

Discovery clicks links and queues controls on a live application. Everything
else about a sweep is read-only observation; navigation and control-pressing
are not, and a tool pointed at production has to be tellable — in the project
file, reviewably — that some routes and some buttons are off limits.
"""

from __future__ import annotations

from pathlib import Path

from parallax.conductor import Conductor
from parallax.config import _settings_from


def conductor(*patterns: str) -> Conductor:
    return Conductor("https://app.example/", "/tmp/parallax-deny-test", browser=None, deny=list(patterns))


def test_plain_text_matches_anywhere_case_insensitively() -> None:
    """Whoever writes "delete" means every delete button, not one exact path."""
    subject = conductor("delete")

    assert subject._denied("/admin/delete-user")
    assert subject._denied("#btn-Delete-Account")
    assert subject._denied("Delete my workspace")
    assert not subject._denied("/admin/reports")


def test_glob_patterns_match_the_whole_value() -> None:
    subject = conductor("/admin/*")

    assert subject._denied("/admin/purge")
    assert not subject._denied("/blog/admin-tips")


def test_no_patterns_denies_nothing() -> None:
    assert not conductor()._denied("/logout")


def test_blank_patterns_are_dropped_rather_than_matching_everything() -> None:
    """An empty string is a substring of every value; keeping one would deny the site."""
    subject = conductor("", "  ", "logout")

    assert subject.deny == ["logout"]
    assert subject._denied("/logout")
    assert not subject._denied("/threads")


def test_the_config_file_carries_deny_under_constraints(tmp_path: Path) -> None:
    settings = _settings_from(
        {"constraints": {"deny": ["logout", "/admin/*", "  ", 7]}},
        tmp_path / "parallax.toml",
    )

    # Non-strings and blanks are dropped; what survives is exactly what a
    # reviewer of the file would expect to be enforced.
    assert settings.deny == ["logout", "/admin/*"]


def test_a_missing_constraints_table_means_no_denials(tmp_path: Path) -> None:
    assert _settings_from({}, tmp_path / "parallax.toml").deny == []
