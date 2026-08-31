"""The command's own logic, separate from the browser work it orchestrates.

Everything here is what a caller sees before and after a sweep: how roles and
files are read, what the run reports about the models it used, and why a
delivery or a proposal did not happen. None of it needs Chromium, and all of it
is what somebody reads when a run does not do what they expected.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from parallax.__main__ import (
    _declaration,
    _deliver,
    _model_report,
    _scenario_proposer,
    _storage_states,
)


class Namespace:
    def __init__(self, **fields: object) -> None:
        self.__dict__.update(fields)


class Lens:
    def __init__(self, *, attempted: int, succeeded: int, error: str | None = None) -> None:
        self.model = "gemini-3.7-flash"
        self.route = "vertex"
        self.calls_attempted = attempted
        self.calls_succeeded = succeeded
        self.last_error = error


def test_roles_are_read_as_role_equals_path() -> None:
    assert _storage_states(["owner=.auth/owner.json", " member = /tmp/m.json "]) == {
        "owner": ".auth/owner.json",
        "member": "/tmp/m.json",
    }


def test_a_role_without_a_path_is_refused_rather_than_ignored() -> None:
    """A silently dropped role produces a sweep that cannot see what it was asked to."""
    with pytest.raises(SystemExit) as error:
        _storage_states(["owner"])

    assert "--storage-state expects ROLE=PATH" in str(error.value)


def test_a_later_role_replaces_an_earlier_one_of_the_same_name() -> None:
    assert _storage_states(["owner=a.json", "owner=b.json"]) == {"owner": "b.json"}


def test_the_run_reports_how_many_model_calls_succeeded() -> None:
    """A run that silently lost the model must not look like a run that found nothing."""
    report = _model_report([object(), Lens(attempted=25, succeeded=25)])

    assert report == {
        "name": "gemini-3.7-flash",
        "route": "vertex",
        "calls_attempted": 25,
        "calls_succeeded": 25,
    }


def test_a_failing_model_reports_its_last_error() -> None:
    report = _model_report([Lens(attempted=4, succeeded=1, error="429 exhausted")])

    assert report["calls_succeeded"] == 1
    assert report["last_error"] == "429 exhausted"


def test_no_vision_lens_reports_disabled_rather_than_zero_findings() -> None:
    report = _model_report([object()])

    assert report == {"route": "disabled", "calls_attempted": 0, "calls_succeeded": 0}


def test_delivery_not_requested_says_so() -> None:
    report = _deliver(Namespace(open_pr=None, pr_base=None), summary=object())

    assert report.note == "not requested"
    assert report.attempted is False


def test_a_proposer_is_not_built_when_it_was_not_asked_for() -> None:
    assert _scenario_proposer(False) is None


def test_a_declaration_file_is_read_once_and_returned_whole(tmp_path: Path) -> None:
    """Every scenario shape shares one file; four parsers must see one read."""
    path = tmp_path / "scenarios.json"
    path.write_text(json.dumps({"scenarios": [], "capabilities": [], "choreographies": []}), encoding="utf-8")

    assert _declaration(path) == {"scenarios": [], "capabilities": [], "choreographies": []}


def test_a_missing_declaration_file_names_the_path(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as error:
        _declaration(tmp_path / "absent.json")

    assert "file does not exist" in str(error.value)
    assert "absent.json" in str(error.value)


def test_malformed_json_reports_where_it_broke(tmp_path: Path) -> None:
    """'invalid JSON' without a position is a worse message than no message."""
    path = tmp_path / "broken.json"
    path.write_text('{"scenarios": [},', encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        _declaration(path)

    assert "invalid JSON at line" in str(error.value)
    assert "column" in str(error.value)


def test_a_directory_given_where_a_file_was_expected_is_reported(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as error:
        _declaration(tmp_path)

    assert "could not read file" in str(error.value)


def test_the_run_report_counts_every_shape_it_exercised() -> None:
    """This dict is the run's primary artifact, and it had never been checked.

    It was a literal inside an async function that needed Chromium to evaluate,
    so no test could reach it; extracting it immediately surfaced a name the
    body referenced and no longer defined.
    """
    from parallax.conductor import ConductSummary
    from parallax.proposer import ProposalReport
    from parallax.types import (
        Axis,
        AxisApplicability,
        BASELINE,
        Finding,
        FindingKind,
        Outcome,
        Severity,
        Surface,
        SurfaceKind,
        Testimony,
    )
    from parallax.__main__ import run_summary

    surface = Surface(SurfaceKind.ROUTE, "https://app.example/threads")
    finding = Finding(
        kind=FindingKind.PROPAGATION_FAILURE,
        severity=Severity.HIGH,
        surface=surface,
        axis=Axis.RELATIONAL,
        summary="the receiver never saw it",
        testimonies=[Testimony(surface, BASELINE, Outcome.REACHED)],
    )
    summary = ConductSummary(
        surfaces=[surface],
        testimonies=[Testimony(surface, BASELINE, Outcome.REACHED)],
        findings=[finding],
        spec_paths=[],
        feed_path=Path("runs/x/feed.jsonl"),
        axis_applicability=[
            AxisApplicability(Axis.PRIVILEGE, True, "two role states were supplied"),
            AxisApplicability(Axis.LOCALE, False, "no localized alternate observed"),
        ],
        proposal_report=ProposalReport(enabled=False, proposed=0, validated=0),
        scenarios_exercised=2,
        capabilities_exercised=1,
        capability_roles_exercised=3,
        audiences_exercised=1,
        audience_observers_exercised=3,
        choreographies_exercised=1,
        choreography_steps_exercised=7,
    )

    class Reportable:
        def report(self) -> dict[str, object]:
            return {"ok": True}

    class Triage:
        summary = "grouped into 1 cause"
        groups: list[object] = []

    report = run_summary(
        summary,
        sign_ins=[],
        locale=Reportable(),
        capability_scenarios=[object()],
        audiences=[object()],
        choreographies=[object()],
        relational_scenarios=[object(), object()],
        specialists=[],
        semantics=Reportable(),
        delivery=Reportable(),
        triage=Triage(),
    )

    assert report["findings"] == 1
    assert report["by_severity"]["high"] == 1
    assert report["axis_summary"] == "1 axes exercised, 1 not applicable"
    assert report["choreographies"] == {"ran": 1, "declared": 1, "steps": 7}
    assert report["audiences"] == {"ran": 1, "declared": 1, "observers": 3}
    assert report["relational_scenarios"]["findings"] == 1
    # A run that never reached the model must say so rather than look like a run
    # that reached it and found nothing.
    assert report["model"] == {"route": "disabled", "calls_attempted": 0, "calls_succeeded": 0}


def test_the_run_report_is_json_serialisable() -> None:
    """It is printed with json.dumps; a stray object there aborts the whole run."""
    from parallax.conductor import ConductSummary
    from parallax.proposer import ProposalReport
    from parallax.__main__ import run_summary

    class Reportable:
        def report(self) -> dict[str, object]:
            return {"ok": True}

    class Triage:
        summary = "nothing to group"
        groups: list[object] = []

    report = run_summary(
        ConductSummary([], [], [], [], Path("f.jsonl"), [], ProposalReport(enabled=False, proposed=0, validated=0)),
        sign_ins=[], locale=Reportable(), capability_scenarios=[], audiences=[],
        choreographies=[], relational_scenarios=None, specialists=[],
        semantics=Reportable(), delivery=Reportable(), triage=Triage(),
    )

    assert json.loads(json.dumps(report))["findings"] == 0
