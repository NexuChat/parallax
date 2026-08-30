from __future__ import annotations

import json

from parallax.triage import GemmaTriage
from parallax.types import Axis, Finding, FindingKind, Severity, Surface, SurfaceKind


def finding(summary: str, kind: FindingKind = FindingKind.RENDER_DEFECT) -> Finding:
    return Finding(
        kind=kind,
        severity=Severity.MEDIUM,
        surface=Surface(SurfaceKind.ROUTE, f"https://app.example/{summary[:6].strip()}"),
        axis=Axis.VIEWPORT,
        summary=summary,
        testimonies=[],
    )


def test_disabled_without_an_endpoint_and_says_so() -> None:
    report = GemmaTriage(endpoint="").group([finding("overflow on the cart grid")])

    assert report.attempted is False
    assert report.groups == ()
    assert "no PARALLAX_GEMMA_URL" in report.summary


def test_groups_findings_by_the_ids_the_model_returns() -> None:
    first, second, third = finding("overflow on cart"), finding("overflow on checkout"), finding("contrast on faq")
    triage = GemmaTriage(
        endpoint="http://gemma.invalid",
        transport=lambda _prompt: '{"groups":[{"label":"Horizontal overflow","ids":[1,2]},'
                                  '{"label":"Low contrast","ids":[3]}]}',
    )

    report = triage.group([first, second, third])

    assert [group.label for group in report.groups] == ["Horizontal overflow", "Low contrast"]
    assert report.groups[0].finding_ids == (first.id, second.id)
    assert report.groups[1].finding_ids == (third.id,)
    assert report.summary == "3 findings grouped into 2 causes by gemma3:4b"


def test_an_id_the_model_was_never_given_is_discarded() -> None:
    """The grouper partitions its input; it cannot add to it."""
    only = finding("overflow on cart")
    triage = GemmaTriage(
        endpoint="http://gemma.invalid",
        transport=lambda _prompt: '{"groups":[{"label":"Invented","ids":[7,9]},{"label":"Real","ids":[1]}]}',
    )

    report = triage.group([only])

    assert [group.label for group in report.groups] == ["Real"]
    assert report.groups[0].finding_ids == (only.id,)


def test_a_finding_is_claimed_by_one_group_only() -> None:
    first, second = finding("overflow on cart"), finding("contrast on faq")
    triage = GemmaTriage(
        endpoint="http://gemma.invalid",
        transport=lambda _prompt: '{"groups":[{"label":"First","ids":[1,2]},{"label":"Second","ids":[2]}]}',
    )

    report = triage.group([first, second])

    assert [group.finding_ids for group in report.groups] == [(first.id, second.id)]


def test_fenced_json_is_accepted_because_chat_models_emit_it() -> None:
    only = finding("overflow on cart")
    triage = GemmaTriage(
        endpoint="http://gemma.invalid",
        transport=lambda _prompt: '```json\n{"groups":[{"label":"Overflow","ids":[1]}]}\n```',
    )

    assert triage.group([only]).groups[0].label == "Overflow"


def test_an_unreachable_grouper_is_reported_not_swallowed() -> None:
    """A run that grouped nothing must be distinguishable from one that could not."""
    def explode(_prompt: str) -> str:
        raise TimeoutError("no route to host")

    report = GemmaTriage(endpoint="http://gemma.invalid", transport=explode).group([finding("overflow")])

    assert report.attempted is True
    assert report.groups == ()
    assert "TimeoutError" in (report.error or "")
    assert "triage unavailable" in report.summary


def test_unparseable_output_yields_no_groups_rather_than_a_guess() -> None:
    triage = GemmaTriage(endpoint="http://gemma.invalid", transport=lambda _prompt: "I think they are all overflow.")

    assert triage.group([finding("overflow")]).groups == ()


def test_grouping_is_appended_to_the_feed_the_console_reads(tmp_path) -> None:
    """A grouping that only reaches stdout cannot be checked against evidence later."""
    from parallax.__main__ import _append_triage

    feed = tmp_path / "feed.jsonl"
    feed.write_text('{"kind":"status","at":"now","payload":{}}\n', encoding="utf-8")
    grouped = finding("overflow on the cart grid")
    report = GemmaTriage(
        endpoint="http://gemma.invalid",
        transport=lambda _prompt: '{"groups":[{"label":"Overflow","ids":[1]}]}',
    ).group([grouped])

    _append_triage(feed, report)

    events = [json.loads(line) for line in feed.read_text(encoding="utf-8").splitlines()]
    assert [event["kind"] for event in events] == ["status", "triage"]
    payload = events[-1]["payload"]
    assert payload["model"] == report.model
    assert payload["attempted"] is True
    assert payload["groups"] == [{"label": "Overflow", "finding_ids": [grouped.id]}]


def test_a_missing_feed_is_not_an_error(tmp_path) -> None:
    """The sweep already failed if there is no feed; do not mask it with a write error."""
    from parallax.__main__ import _append_triage

    _append_triage(tmp_path / "absent.jsonl", GemmaTriage(endpoint="").group([]))
