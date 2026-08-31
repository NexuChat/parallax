from __future__ import annotations

import asyncio
import errno
import json
import os
import stat
from urllib.parse import parse_qs

import pytest

from parallax.types import Axis, Context, Defect, Finding, FindingKind, Outcome, Severity, Surface, SurfaceKind
from parallax.types import Testimony as WitnessTestimony
from scripts import run_demo_suite
from sites.base import Account, Planted


def finding(kind: FindingKind, axis: Axis, url: str) -> Finding:
    return Finding(kind, Severity.HIGH, Surface(SurfaceKind.ROUTE, url), axis, "test", [])


def test_template_route_matches_a_concrete_url_under_a_site_mount() -> None:
    plant = Planted("render", "baseline", "/product/<id>", "product")
    grade = run_demo_suite.grade_findings(
        [finding(FindingKind.RENDER_DEFECT, Axis.BASELINE, "http://127.0.0.1:8099/shop/product/ledger")],
        [plant],
        site_name="shop",
    )

    assert grade.found == [plant]


def test_template_plant_absorbs_all_matching_concrete_findings() -> None:
    plant = Planted("render", "baseline", "/product/<id>", "product")
    matching = [
        finding(FindingKind.RENDER_DEFECT, Axis.BASELINE, "http://127.0.0.1:8099/shop/product/ledger"),
        finding(FindingKind.RENDER_DEFECT, Axis.BASELINE, "http://127.0.0.1:8099/shop/product/organizer"),
    ]
    unrelated = finding(FindingKind.RENDER_DEFECT, Axis.BASELINE, "http://127.0.0.1:8099/shop/cart")

    grade = run_demo_suite.grade_findings([*matching, unrelated], [plant], site_name="shop")

    assert grade.found == [plant]
    assert grade.false_positives == [unrelated]


def test_grading_uses_the_render_finding_defect_when_testimony_is_minimal() -> None:
    plant = Planted("small_tap_target", "viewport", "/cart", "stepper")
    item = Finding(
        FindingKind.RENDER_DEFECT,
        Severity.MEDIUM,
        Surface(SurfaceKind.ROUTE, "http://127.0.0.1:8099/shop/cart"),
        Axis.VIEWPORT,
        "small stepper",
        [],
        defect=Defect.SMALL_TAP_TARGET,
    )

    grade = run_demo_suite.grade_findings([item], [plant], site_name="shop")

    assert grade.found == [plant]
    assert grade.false_positives == []


def test_grading_does_not_let_one_render_plant_consume_another_defect() -> None:
    surface = Surface(SurfaceKind.ROUTE, "http://127.0.0.1:8099/shop/cart")
    testimony = WitnessTestimony(
        surface,
        Context(varies=Axis.VIEWPORT),
        Outcome.PARTIAL,
        defects=[Defect.HORIZONTAL_OVERFLOW, Defect.SMALL_TAP_TARGET],
    )
    findings = [
        Finding(
            FindingKind.RENDER_DEFECT, Severity.MEDIUM, surface, Axis.VIEWPORT,
            "overflow", [testimony], defect=Defect.HORIZONTAL_OVERFLOW,
        ),
        Finding(
            FindingKind.RENDER_DEFECT, Severity.MEDIUM, surface, Axis.VIEWPORT,
            "small target", [testimony], defect=Defect.SMALL_TAP_TARGET,
        ),
    ]
    plants = [
        Planted("horizontal_overflow", "viewport", "/cart", "overflow"),
        Planted("small_tap_target", "viewport", "/cart", "stepper"),
    ]

    grade = run_demo_suite.grade_findings(findings, plants, site_name="shop")

    assert grade.found == plants
    assert grade.missed == []
    assert grade.false_positives == []


def test_different_route_is_not_counted_as_a_template_match() -> None:
    plant = Planted("render", "baseline", "/product/<id>", "product")
    grade = run_demo_suite.grade_findings(
        [finding(FindingKind.RENDER_DEFECT, Axis.BASELINE, "http://127.0.0.1:8099/shop/cart")],
        [plant],
        site_name="shop",
    )

    assert grade.missed == [plant]
    assert len(grade.false_positives) == 1


def test_landing_page_matches_root_under_a_site_mount() -> None:
    plant = Planted("render", "baseline", "/", "landing")
    grade = run_demo_suite.grade_findings(
        [finding(FindingKind.RENDER_DEFECT, Axis.BASELINE, "http://127.0.0.1:8099/shop/")],
        [plant],
        site_name="shop",
    )

    assert grade.found == [plant]


def test_unmatched_finding_is_a_false_positive_including_for_a_control_site() -> None:
    item = finding(FindingKind.DEAD_SURFACE, Axis.BASELINE, "http://127.0.0.1:8099/control/reports")

    grade = run_demo_suite.grade_findings([item], [], site_name="control")

    assert grade.false_positives == [item]


def test_exit_code_fails_for_misses_or_false_positives() -> None:
    plant = Planted("render", "baseline", "/", "landing")

    assert run_demo_suite.exit_code({"site": run_demo_suite.grade_findings([], [plant])}) == 1
    assert run_demo_suite.exit_code({"site": run_demo_suite.grade_findings([finding(FindingKind.RENDER_DEFECT, Axis.BASELINE, "/")], [])}) == 1


def test_summary_writer_records_every_grade_and_plant_verdict(tmp_path) -> None:
    found = Planted("render", "baseline", "/", "landing")
    missed = Planted("escalation", "privilege", "/billing", "billing")
    grades = {
        "shop": run_demo_suite.Grade([found], [missed], [finding(FindingKind.DEAD_SURFACE, Axis.BASELINE, "/other")]),
        "control": run_demo_suite.Grade([], [], []),
    }
    path = tmp_path / "graded-summary.json"

    run_demo_suite.write_summary(grades, "http://127.0.0.1:8090", path, generated_at="2026-08-29T12:00:00+00:00")

    assert json.loads(path.read_text()) == {
        "host": "http://127.0.0.1:8090",
        "generated_at": "2026-08-29T12:00:00+00:00",
        "sites": {
            "shop": {
                "planted": 2, "found": 1, "missed": 1, "false_positives": 1,
                "plants": [
                    {"name": "landing", "defect": "render", "axis": "baseline", "route": "/", "verdict": "found"},
                    {"name": "billing", "defect": "escalation", "axis": "privilege", "route": "/billing", "verdict": "missed"},
                ],
            },
            "control": {"planted": 0, "found": 0, "missed": 0, "false_positives": 0, "plants": []},
        },
        "totals": {"planted": 2, "found": 1, "missed": 1, "false_positives": 1},
    }


def test_public_spec_example_is_emitted_from_a_real_finding() -> None:
    generated = run_demo_suite.generated_example_spec()
    published = (run_demo_suite.ROOT / "web" / "generated-example.spec.ts").read_text(encoding="utf-8")

    assert published == generated
    assert 'test("Parallax: escalation-privilege-' in generated


def test_publish_sweeps_replaces_stale_artifacts_without_publishing_credentials(tmp_path) -> None:
    runs_root = tmp_path / "runs"
    public_root = tmp_path / "console" / "runs"
    source = runs_root / "workspace"
    (source / "mosaics").mkdir(parents=True)
    (source / "specs").mkdir()
    events = [
        {"kind": "mosaic", "payload": {"surface_id": "surface-1", "seq": 1}},
        {"kind": "finding", "payload": {"id": "finding-1", "severity": "high", "kind": "revocation"}},
        {"kind": "finding", "payload": {"id": "finding-1", "severity": "high", "kind": "revocation"}},
    ]
    (source / "feed.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    (source / "mosaics" / "frame.jpg").write_bytes(b"frame")
    (source / "specs" / "fresh.spec.ts").write_text("// current\n", encoding="utf-8")
    stale = public_root / "workspace"
    (stale / "specs").mkdir(parents=True)
    (stale / "specs" / "stale.spec.ts").write_text("// obsolete\n", encoding="utf-8")
    (stale / "storage-member.json").write_text('{"cookies": []}', encoding="utf-8")

    index = run_demo_suite.publish_sweeps(runs_root, public_root, ["workspace"])

    assert (public_root / "workspace" / "specs" / "fresh.spec.ts").read_text() == "// current\n"
    assert not (public_root / "workspace" / "specs" / "stale.spec.ts").exists()
    assert not list(public_root.glob("*/storage-*.json"))
    assert (public_root / "latest" / "feed.jsonl").read_text() == (source / "feed.jsonl").read_text()
    assert index == {
        "workspace": {
            "feed": "runs/workspace/feed.jsonl",
            "mosaics": 1,
            "findings": 1,
            "by_severity": {"high": 1},
            "by_kind": {"revocation": 1},
        }
    }
    assert json.loads((public_root / "index.json").read_text()) == index


def test_publish_sweeps_rejects_unexpected_credentials_in_the_run_tree(tmp_path) -> None:
    runs_root = tmp_path / "runs"
    source = runs_root / "workspace"
    source.mkdir(parents=True)
    (source / "feed.jsonl").write_text("", encoding="utf-8")
    (source / "storage-owner.json").write_text('{"cookies": [{"value": "secret"}]}', encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected artifact"):
        run_demo_suite.publish_sweeps(runs_root, tmp_path / "public", ["workspace"])


def test_publish_sweeps_rejects_sensitive_values_in_public_feed_and_urls(tmp_path) -> None:
    runs_root = tmp_path / "runs"
    source = runs_root / "workspace"
    source.mkdir(parents=True)
    (source / "feed.jsonl").write_text(
        json.dumps({"kind": "status", "payload": {"surface": "https://demo.example/?access_token=leaked"}}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="sensitive"):
        run_demo_suite.publish_sweeps(runs_root, tmp_path / "public", ["workspace"])


def test_publish_sweeps_rejects_sensitive_literal_in_public_spec(tmp_path) -> None:
    runs_root = tmp_path / "runs"
    source = runs_root / "workspace"
    (source / "specs").mkdir(parents=True)
    (source / "feed.jsonl").write_text("", encoding="utf-8")
    (source / "specs" / "finding.spec.ts").write_text('const token = "leaked-value";\n', encoding="utf-8")

    with pytest.raises(ValueError, match="sensitive"):
        run_demo_suite.publish_sweeps(runs_root, tmp_path / "public", ["workspace"])


def test_summary_writer_rejects_sensitive_host_url(tmp_path) -> None:
    with pytest.raises(ValueError, match="sensitive"):
        run_demo_suite.write_summary({}, "https://user:password@demo.example/", tmp_path / "summary.json")


def test_publish_sweeps_keeps_the_previous_generation_when_staging_fails(tmp_path) -> None:
    runs_root = tmp_path / "runs"
    public_root = tmp_path / "console" / "runs"
    old = public_root / "workspace"
    old.mkdir(parents=True)
    (old / "feed.jsonl").write_text("old\n", encoding="utf-8")
    source = runs_root / "workspace"
    source.mkdir(parents=True)
    (source / "feed.jsonl").write_text("", encoding="utf-8")
    (source / "unexpected.txt").write_text("bad", encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected artifact"):
        run_demo_suite.publish_sweeps(runs_root, public_root, ["workspace"])

    assert (old / "feed.jsonl").read_text(encoding="utf-8") == "old\n"


def test_publish_sweeps_leaves_previous_generation_when_atomic_exchange_is_unavailable(tmp_path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    public_root = tmp_path / "console" / "runs"
    old = public_root / "workspace"
    old.mkdir(parents=True)
    (old / "feed.jsonl").write_text("old\n", encoding="utf-8")
    source = runs_root / "workspace"
    source.mkdir(parents=True)
    (source / "feed.jsonl").write_text("", encoding="utf-8")

    monkeypatch.setattr(run_demo_suite, "_rename_exchange", lambda *_: (_ for _ in ()).throw(OSError(errno.ENOSYS, "unsupported")))

    with pytest.raises(RuntimeError, match="atomic exchange"):
        run_demo_suite.publish_sweeps(runs_root, public_root, ["workspace"])

    assert (old / "feed.jsonl").read_text(encoding="utf-8") == "old\n"


@pytest.mark.parametrize("relative", ["feed.jsonl", "specs/finding.spec.ts", "mosaics/frame.jpg"])
def test_publish_sweeps_never_follows_artifact_symlinks(tmp_path, relative) -> None:
    runs_root = tmp_path / "runs"
    source = runs_root / "workspace"
    (source / "specs").mkdir(parents=True)
    (source / "mosaics").mkdir()
    (source / "feed.jsonl").write_text("", encoding="utf-8")
    (source / "specs" / "finding.spec.ts").write_text("// safe\n", encoding="utf-8")
    (source / "mosaics" / "frame.jpg").write_bytes(b"safe")
    target = source / relative
    target.unlink()
    secret = tmp_path / "secret"
    secret.write_text("must not publish", encoding="utf-8")
    target.symlink_to(secret)

    with pytest.raises(ValueError, match="regular file"):
        run_demo_suite.publish_sweeps(runs_root, tmp_path / "public", ["workspace"])

    assert not (tmp_path / "public" / "workspace").exists()


def test_publish_sweeps_rejects_unexpected_types_and_extensions(tmp_path) -> None:
    runs_root = tmp_path / "runs"
    source = runs_root / "workspace"
    (source / "specs").mkdir(parents=True)
    (source / "mosaics").mkdir()
    (source / "feed.jsonl").write_text("", encoding="utf-8")
    (source / "specs" / "cookies.json").write_text("{}", encoding="utf-8")
    os.mkfifo(source / "mosaics" / "unexpected.jpg")

    with pytest.raises(ValueError, match="unexpected artifact"):
        run_demo_suite.publish_sweeps(runs_root, tmp_path / "public", ["workspace"])


def test_storage_state_builder_turns_a_login_cookie_into_playwright_state() -> None:
    class FakeLoginResponse:
        headers = {"Set-Cookie": "session=owner-token; Path=/; HttpOnly; SameSite=Lax"}

    state = run_demo_suite.storage_state_from_login_response(FakeLoginResponse(), "http://127.0.0.1:8099")

    assert state == {
        "cookies": [{
            "name": "session", "value": "owner-token", "domain": "127.0.0.1", "path": "/",
            "httpOnly": True, "secure": False, "sameSite": "Lax",
        }],
        "origins": [],
    }


def test_storage_state_builder_uses_declared_accounts_without_reading_site_source(tmp_path, monkeypatch) -> None:
    requests = []

    class StubSite:
        name = "stub"
        accounts = [Account("reader", "declared@demo", "declared-password")]

    class Response:
        status = 302
        headers = {"Set-Cookie": "session=reader; Path=/; HttpOnly"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Opener:
        def open(self, request):
            requests.append(request)
            return Response()

    monkeypatch.setattr(run_demo_suite, "build_opener", lambda *handlers: Opener())

    states = run_demo_suite.build_storage_states(StubSite(), "http://127.0.0.1:8099", tmp_path)

    assert set(states) == {"reader"}
    assert stat.S_IMODE(states["reader"].stat().st_mode) == 0o600
    assert parse_qs(requests[0].data.decode()) == {
        "email": ["declared@demo"], "username": ["declared@demo"], "password": ["declared-password"],
    }


def test_storage_state_builder_sweeps_sites_without_accounts_anonymously(tmp_path, monkeypatch) -> None:
    class StubSite:
        name = "public"
        accounts: list[Account] = []

    monkeypatch.setattr(run_demo_suite, "build_opener", lambda *handlers: (_ for _ in ()).throw(AssertionError("anonymous sites do not log in")))

    assert run_demo_suite.build_storage_states(StubSite(), "http://127.0.0.1:8099", tmp_path) == {}


def test_storage_state_builder_rejects_a_failed_declared_login_without_partial_states(tmp_path, monkeypatch, capsys) -> None:
    class StubSite:
        name = "stub"
        accounts = [Account("broken", "broken@demo", "wrong"), Account("member", "member@demo", "demo")]

    class Response:
        def __init__(self, cookie: str | None) -> None:
            self.status = 200 if cookie is None else 302
            self.headers = {} if cookie is None else {"Set-Cookie": cookie}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    responses = iter([Response(None), Response("session=member; Path=/; HttpOnly")])

    class Opener:
        def open(self, request):
            return next(responses)

    monkeypatch.setattr(run_demo_suite, "build_opener", lambda *handlers: Opener())

    with pytest.raises(RuntimeError, match="required role login failed"):
        run_demo_suite.build_storage_states(StubSite(), "http://127.0.0.1:8099", tmp_path)

    assert not list(tmp_path.glob("storage-*.json"))
    assert "site stub, role broken, server returned HTTP 200" in capsys.readouterr().err


def test_storage_state_builder_rejects_duplicate_authenticated_identity(tmp_path, monkeypatch) -> None:
    class StubSite:
        name = "stub"
        accounts = [Account("owner", "owner@demo", "demo"), Account("member", "member@demo", "demo")]

    class Response:
        status = 302
        headers = {"Set-Cookie": "session=same-person; Path=/; HttpOnly"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Opener:
        def open(self, request):
            return Response()

    monkeypatch.setattr(run_demo_suite, "build_opener", lambda *handlers: Opener())

    with pytest.raises(ValueError, match="duplicate authenticated identity"):
        run_demo_suite.build_storage_states(StubSite(), "http://127.0.0.1:8099", tmp_path)

    assert not list(tmp_path.glob("storage-*.json"))


def test_storage_state_identity_is_independent_of_cookie_header_order() -> None:
    first = {"cookies": [{"name": "a", "value": "one"}, {"name": "b", "value": "two"}], "origins": []}
    second = {"cookies": list(reversed(first["cookies"])), "origins": []}

    assert run_demo_suite._storage_state_identity(first) == run_demo_suite._storage_state_identity(second)


def test_storage_state_writer_does_not_follow_a_preexisting_symlink(tmp_path, monkeypatch) -> None:
    class StubSite:
        name = "stub"
        accounts = [Account("reader", "declared@demo", "declared-password")]

    class Response:
        status = 302
        headers = {"Set-Cookie": "session=reader; Path=/; HttpOnly"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Opener:
        def open(self, request):
            return Response()

    target = tmp_path / "outside.json"
    target.write_text("unchanged", encoding="utf-8")
    (tmp_path / "storage-reader.json").symlink_to(target)
    monkeypatch.setattr(run_demo_suite, "build_opener", lambda *handlers: Opener())

    with pytest.raises(FileExistsError):
        run_demo_suite.build_storage_states(StubSite(), "http://127.0.0.1:8099", tmp_path)

    assert target.read_text(encoding="utf-8") == "unchanged"


def test_failed_sweep_removes_private_storage_states_outside_the_run_tree(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class StubSite:
        name = "stub"
        accounts = [Account("reader", "declared@demo", "declared-password")]
        relational_scenarios = []

    class Response:
        status = 302
        headers = {"Set-Cookie": "session=reader; Path=/; HttpOnly"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Opener:
        def open(self, request):
            return Response()

    class BrokenConductor:
        def __init__(self, *args, storage_states, **kwargs):
            captured["states"] = storage_states

        async def conduct(self):
            states = captured["states"]
            assert all(path.is_file() for path in states.values())
            raise RuntimeError("sweep failed")

    monkeypatch.setattr(run_demo_suite, "build_opener", lambda *handlers: Opener())
    monkeypatch.setattr(run_demo_suite, "Conductor", BrokenConductor)
    run_dir = tmp_path / "runs" / "stub"

    with pytest.raises(RuntimeError, match="sweep failed"):
        asyncio.run(run_demo_suite._conduct_site(
            StubSite(), "http://127.0.0.1:8099", run_dir, object(), no_vision=True, max_surfaces=1,
        ))

    states = captured["states"]
    assert all(not path.exists() for path in states.values())
    assert all(run_dir not in path.parents for path in states.values())


def test_relational_scenarios_read_a_site_declaration_instead_of_its_name() -> None:
    class StubSite:
        name = "collaboration"
        relational_scenarios = [{
            "surface": "/threads",
            "sender": "owner",
            "receiver": "member",
            "action": {"type": "submit_form", "form": "form.composer", "fills": []},
            "effect": {"type": "visible", "selector": ".message"},
            "deadline_ms": 1000,
        }]

    scenarios = run_demo_suite._relational_scenarios(StubSite(), "http://127.0.0.1:8099")

    assert len(scenarios) == 1
    assert scenarios[0].surface.path == "http://127.0.0.1:8099/collaboration/threads"


def test_publish_carries_forward_a_run_this_sweep_did_not_produce(tmp_path) -> None:
    """Sweeps of real applications are published here too, and are not regenerated.

    Publishing replaces the whole public directory in one exchange. Without the
    carry-forward, running the demo suite with --publish silently deleted every
    hand-run sweep of a real site and dropped it from index.json — evidence a
    reader had been given a link to.
    """
    runs_root = tmp_path / "runs"
    public_root = tmp_path / "console" / "runs"
    fresh = runs_root / "workspace"
    fresh.mkdir(parents=True)
    (fresh / "feed.jsonl").write_text(
        json.dumps({"kind": "finding", "payload": {"id": "f1", "severity": "high", "kind": "escalation"}}) + "\n",
        encoding="utf-8",
    )
    existing = public_root / "arbchat"
    existing.mkdir(parents=True)
    (existing / "feed.jsonl").write_text(
        json.dumps({"kind": "finding", "payload": {"id": "a1", "severity": "low", "kind": "render"}}) + "\n",
        encoding="utf-8",
    )

    index = run_demo_suite.publish_sweeps(runs_root, public_root, ["workspace"])

    assert (public_root / "arbchat" / "feed.jsonl").exists()
    assert set(index) == {"arbchat", "workspace"}
    assert index["arbchat"]["by_kind"] == {"render": 1}


def test_a_carried_run_is_held_to_the_same_rules_as_a_fresh_one(tmp_path) -> None:
    """Being already public is not a reason to skip the checks that made it public."""
    runs_root = tmp_path / "runs"
    public_root = tmp_path / "console" / "runs"
    fresh = runs_root / "workspace"
    fresh.mkdir(parents=True)
    (fresh / "feed.jsonl").write_text("", encoding="utf-8")
    leaky = public_root / "the-internet"
    leaky.mkdir(parents=True)
    (leaky / "feed.jsonl").write_text("", encoding="utf-8")
    (leaky / "storage-owner.json").write_text('{"cookies": []}', encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected artifact"):
        run_demo_suite.publish_sweeps(runs_root, public_root, ["workspace"])
