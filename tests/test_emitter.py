from __future__ import annotations

import re
from pathlib import Path

from parallax.emitter import emit_all, filename_for, spec_for
from parallax.types import (
    BASELINE,
    MOBILE,
    Axis,
    Context,
    Defect,
    Finding,
    FindingKind,
    Locale,
    Outcome,
    Privilege,
    RevocationLag,
    RevocationPlanes,
    Severity,
    Surface,
    SurfaceKind,
    Testimony,
    Theme,
)


SURFACE = Surface(SurfaceKind.AFFORDANCE, "/admin", "#delete", "Delete")


def make_testimony(
    context: Context, *, defects: list[Defect] | None = None, signature: str | None = None
) -> Testimony:
    return Testimony(
        surface=SURFACE,
        context=context,
        outcome=Outcome.REACHED,
        defects=defects or [],
        content_signature=signature,
    )


def finding(kind: FindingKind, *, axis: Axis = Axis.PRIVILEGE, testimonies: list[Testimony] | None = None) -> Finding:
    return Finding(
        kind=kind,
        severity=Severity.MEDIUM,
        surface=SURFACE,
        axis=axis,
        summary="A generated regression test",
        testimonies=testimonies or [make_testimony(BASELINE)],
    )


def test_specs_encode_context_and_header_evidence() -> None:
    varied = Context(
        privilege=Privilege.MEMBER,
        locale=Locale.AR,
        theme=Theme.DARK,
        viewport=MOBILE,
        varies=Axis.PRIVILEGE,
    )
    generated = spec_for(
        finding(FindingKind.ESCALATION, testimonies=[make_testimony(BASELINE), make_testimony(varied)]),
        {"member": "runs/admin/storage-member.json"},
    )

    assert "Finding: escalation-privilege-" in generated
    assert "Axis: privilege" in generated
    assert "Evidence: owner-en-light-desktop=reached" in generated
    assert "member-ar-dark-mobile=reached" in generated
    assert "viewport: { width: 360, height: 740 }" in generated
    assert 'locale: "ar"' in generated
    assert 'colorScheme: "dark"' in generated
    assert 'storageState: "runs/admin/storage-member.json"' in generated
    assert "the file this run was given" in generated
    assert 'use: { baseURL: "https://your-app.example" }' in generated


def test_specs_use_base_url_relative_routes_and_pipeline_storage_states() -> None:
    anonymous = Context(privilege=Privilege.ANON, varies=Axis.PRIVILEGE)
    member = Context(privilege=Privilege.MEMBER, varies=Axis.PRIVILEGE)
    owner = Context(privilege=Privilege.OWNER, varies=Axis.PRIVILEGE)
    states = {"member": "runs/workspace/storage-member.json", "owner": "runs/workspace/storage-owner.json"}
    absolute_surface = Surface(
        SurfaceKind.ROUTE,
        "https://demo.example/workspace/audit?return=https://elsewhere.example",
    )

    anon_spec = spec_for(
        Finding(FindingKind.ESCALATION, Severity.HIGH, absolute_surface, Axis.PRIVILEGE, "anonymous access", [
            Testimony(absolute_surface, anonymous, Outcome.REACHED),
        ]),
        states,
    )
    member_spec = spec_for(
        Finding(FindingKind.CAPABILITY_DRIFT, Severity.HIGH, absolute_surface, Axis.PRIVILEGE, "member access", [
            Testimony(absolute_surface, member, Outcome.REACHED),
        ]),
        states,
    )
    owner_spec = spec_for(
        Finding(FindingKind.CAPABILITY_DRIFT, Severity.HIGH, absolute_surface, Axis.PRIVILEGE, "owner access", [
            Testimony(absolute_surface, owner, Outcome.REACHED),
        ]),
        states,
    )

    assert "storageState" not in anon_spec
    assert ".auth/" not in anon_spec
    assert 'storageState: "runs/workspace/storage-member.json"' in member_spec
    assert 'storageState: "runs/workspace/storage-owner.json"' in owner_spec
    for generated in (anon_spec, member_spec, owner_spec):
        assert ".auth/" not in generated
        assert not re.search(r"page\.goto\([^)]*://", generated)
        assert 'page.goto("/workspace/audit?return=https%3A%2F%2Felsewhere.example")' in generated


def test_each_finding_kind_emits_the_required_assertion() -> None:
    owner = make_testimony(BASELINE)
    member = make_testimony(Context(privilege=Privilege.MEMBER, varies=Axis.PRIVILEGE))
    mobile = make_testimony(Context(viewport=MOBILE, varies=Axis.VIEWPORT))

    assert "status() === 403" in spec_for(finding(FindingKind.ESCALATION, testimonies=[owner, member]))
    assert "toBeTruthy()" in spec_for(finding(FindingKind.POLICY_INVERSION, testimonies=[owner, member]))
    assert "toBeTruthy()" in spec_for(finding(FindingKind.CAPABILITY_DRIFT, axis=Axis.VIEWPORT, testimonies=[owner, mobile]))
    divergence = spec_for(
        finding(FindingKind.CONTENT_DIVERGENCE, axis=Axis.VIEWPORT, testimonies=[owner, make_testimony(Context(viewport=MOBILE, varies=Axis.VIEWPORT), signature="baseline")])
    )
    # It must recompute the signature the way probe.js did — FNV-1a, not SHA-256 —
    # or the spec fails for a reason unrelated to the finding.
    assert "Math.imul(h, 16777619)" in divergence
    assert 'expect(contentSignature).toBe("baseline")' in divergence
    dead = spec_for(finding(FindingKind.DEAD_SURFACE))
    assert "test.skip(" in dead
    assert "No assertion is emitted" in dead


def test_revocation_lag_spec_polls_an_open_session_under_the_recorded_threshold() -> None:
    item = finding(FindingKind.REVOCATION_LAG)
    item.revocation = RevocationLag(
        lag_ms=20,
        deadline_ms=30,
        probes=("effects",),
        planes=RevocationPlanes(decision=True, distribution=True, enforcement=True, effects=False),
    )

    generated = spec_for(item)

    assert "expect.poll" in generated
    assert "toBeLessThan(30)" in generated
    assert "revocationLagMs" in generated


def test_render_defects_have_specific_invariants() -> None:
    expected = {
        Defect.HORIZONTAL_OVERFLOW: "scrollWidth <= document.documentElement.clientWidth",
        Defect.OFFSCREEN_CONTROL: "box.x + box.width <= window.innerWidth",
        Defect.SMALL_TAP_TARGET: "Math.min(box!.width, box!.height)).toBeGreaterThanOrEqual(44)",
        Defect.LOW_CONTRAST: "contrastRatio",
        Defect.UNTRANSLATED: "rawI18nKey",
        Defect.RTL_NOT_MIRRORED: "toBe(\"rtl\")",
        Defect.THEME_LAYOUT_SHIFT: 'emulateMedia({ colorScheme: "dark" })',
        Defect.CLIPPED: "box.x + box.width <= window.innerWidth",
    }
    for defect, assertion in expected.items():
        generated = spec_for(
            finding(
                FindingKind.RENDER_DEFECT,
                axis=Axis.VIEWPORT,
                testimonies=[make_testimony(Context(viewport=MOBILE, varies=Axis.VIEWPORT), defects=[defect])],
            )
        )
        assert assertion in generated


def test_hostile_text_is_escaped_and_generated_typescript_is_balanced() -> None:
    hostile = Surface(
        SurfaceKind.AFFORDANCE,
        '/danger"\n${injected}`',
        None,
        'Delete */ ${code}\n`',
    )
    item = Finding(
        FindingKind.DEAD_SURFACE,
        Severity.HIGH,
        hostile,
        Axis.BASELINE,
        '"`\n${summary}',
        [make_testimony(BASELINE), make_testimony(Context(privilege=Privilege.ANON, varies=Axis.PRIVILEGE))],
    )
    generated = spec_for(item)

    assert "${injected}" not in generated
    assert "${summary}" not in generated
    assert "*/ ${code}" not in generated
    assert generated.count("{") == generated.count("}")
    assert "import { test, expect } from \"@playwright/test\";" in generated


def test_filenames_are_stable_safe_and_distinct_by_axis() -> None:
    viewport = finding(FindingKind.CAPABILITY_DRIFT, axis=Axis.VIEWPORT)
    theme = finding(FindingKind.CAPABILITY_DRIFT, axis=Axis.THEME)

    assert filename_for(viewport) == filename_for(viewport)
    assert filename_for(viewport) != filename_for(theme)
    assert filename_for(viewport).endswith(".spec.ts")
    assert "/" not in filename_for(viewport)


def test_emit_all_writes_exactly_the_expected_files(tmp_path: Path) -> None:
    findings = [
        finding(FindingKind.ESCALATION),
        finding(FindingKind.CAPABILITY_DRIFT, axis=Axis.VIEWPORT),
    ]

    written = emit_all(findings, tmp_path)

    assert written == [tmp_path / filename_for(item) for item in findings]
    assert {path.name for path in tmp_path.iterdir()} == {filename_for(item) for item in findings}
    assert all(path.read_text(encoding="utf-8") == spec_for(item) for path, item in zip(written, findings))


def test_a_run_without_credentials_emits_a_spec_that_can_open() -> None:
    """The guessed path made every credential-free spec fail on ENOENT first."""
    surface = Surface(SurfaceKind.ROUTE, "https://example.com/")
    owner = Context(privilege=Privilege.OWNER, varies=Axis.VIEWPORT)

    generated = spec_for(
        Finding(FindingKind.RENDER_DEFECT, Severity.MEDIUM, surface, Axis.VIEWPORT, "tap target too small", [
            Testimony(surface, owner, Outcome.PARTIAL),
        ]),
        storage_states=None,
    )

    assert "storageState" not in generated
    assert "runs/site/" not in generated
