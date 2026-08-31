from __future__ import annotations

from dataclasses import replace

import re
from pathlib import Path

from parallax.emitter import emit_all, filename_for, spec_for
from parallax.types import (
    BASELINE,
    MOBILE,
    Axis,
    Context,
    Defect,
    DefectObservation,
    EffectExpectation,
    Finding,
    FindingKind,
    FormAction,
    Locale,
    Outcome,
    Privilege,
    RevocationLag,
    RevocationPlanes,
    RelationalReplay,
    Severity,
    Surface,
    SurfaceKind,
    Testimony as WitnessTestimony,
    Theme,
)


SURFACE = Surface(SurfaceKind.AFFORDANCE, "/admin", "#delete", "Delete")


def make_testimony(
    context: Context,
    *,
    defects: list[Defect] | None = None,
    observations: list[DefectObservation] | None = None,
    signature: str | None = None,
) -> WitnessTestimony:
    return WitnessTestimony(
        surface=SURFACE,
        context=context,
        outcome=Outcome.REACHED,
        defects=defects or [],
        observations=observations or [],
        content_signature=signature,
    )


def finding(kind: FindingKind, *, axis: Axis = Axis.PRIVILEGE, testimonies: list[WitnessTestimony] | None = None) -> Finding:
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
    assert "storageState: process.env.PARALLAX_MEMBER_STORAGE_STATE" in generated
    assert "process.env.PARALLAX_MEMBER_STORAGE_STATE" in generated
    assert "requires PARALLAX_MEMBER_STORAGE_STATE" in generated
    assert "runs/admin/storage-member.json" not in generated
    assert 'use: { baseURL: "https://your-app.example" }' in generated


def test_missing_storage_state_is_checked_inside_the_test_so_list_still_works() -> None:
    member = Context(privilege=Privilege.MEMBER, varies=Axis.PRIVILEGE)
    generated = spec_for(
        finding(FindingKind.CAPABILITY_DRIFT, testimonies=[make_testimony(member)]),
        {"member": "/private/storage-member.json"},
    )

    assert "storageState: process.env.PARALLAX_MEMBER_STORAGE_STATE" in generated
    assert generated.index('test("Parallax:') < generated.index(
        'throw new Error("Parallax generated spec requires PARALLAX_MEMBER_STORAGE_STATE")'
    )


def test_specs_use_base_url_relative_routes_and_pipeline_storage_states() -> None:
    anonymous = Context(privilege=Privilege.ANON, varies=Axis.PRIVILEGE)
    member = Context(privilege=Privilege.MEMBER, varies=Axis.PRIVILEGE)
    owner = Context(privilege=Privilege.OWNER, varies=Axis.PRIVILEGE)
    states = {
        "member": "/tmp/parallax-demo.internal/storage-member.json",
        "owner": "/tmp/parallax-demo.internal/storage-owner.json",
    }
    absolute_surface = Surface(
        SurfaceKind.ROUTE,
        "https://demo.example/workspace/audit?return=https://elsewhere.example",
    )

    anon_spec = spec_for(
        Finding(FindingKind.ESCALATION, Severity.HIGH, absolute_surface, Axis.PRIVILEGE, "anonymous access", [
            WitnessTestimony(absolute_surface, anonymous, Outcome.REACHED),
        ]),
        states,
    )
    member_spec = spec_for(
        Finding(FindingKind.CAPABILITY_DRIFT, Severity.HIGH, absolute_surface, Axis.PRIVILEGE, "member access", [
            WitnessTestimony(absolute_surface, member, Outcome.REACHED),
        ]),
        states,
    )
    owner_spec = spec_for(
        Finding(FindingKind.CAPABILITY_DRIFT, Severity.HIGH, absolute_surface, Axis.PRIVILEGE, "owner access", [
            WitnessTestimony(absolute_surface, owner, Outcome.REACHED),
        ]),
        states,
    )

    assert "storageState" not in anon_spec
    assert ".auth/" not in anon_spec
    assert "process.env.PARALLAX_MEMBER_STORAGE_STATE" in member_spec
    assert "requires PARALLAX_MEMBER_STORAGE_STATE" in member_spec
    assert "process.env.PARALLAX_OWNER_STORAGE_STATE" in owner_spec
    assert "requires PARALLAX_OWNER_STORAGE_STATE" in owner_spec
    for generated in (anon_spec, member_spec, owner_spec):
        assert ".auth/" not in generated
        assert "runs/workspace/storage-" not in generated
        assert "parallax-demo.internal" not in generated
        assert "demo.example" not in generated
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
    assert 'document.querySelector("main") ?? document.body' in divergence
    assert 'expect(contentSignature).toBe("baseline")' in divergence
    dead = spec_for(finding(FindingKind.DEAD_SURFACE))
    assert "test.skip(" not in dead
    assert "expect(reached).toBeTruthy()" in dead


def test_revocation_lag_spec_polls_an_open_session_under_the_recorded_threshold() -> None:
    item = finding(FindingKind.REVOCATION_LAG)
    item.revocation = RevocationLag(
        lag_ms=20,
        deadline_ms=30,
        probes=("effects",),
        planes=RevocationPlanes(decision=True, distribution=True, enforcement=True, effects=False),
        max_lag_ms=10,
    )
    item.replay = RelationalReplay(
        sender=Privilege.OWNER,
        receiver=Privilege.MEMBER,
        action=FormAction("form.remove-member", (), (("#member", "ada"),)),
        effect=EffectExpectation("visible", selector=".workspace-data"),
        deadline_ms=30,
        max_lag_ms=10,
    )

    generated = spec_for(item, {
        "owner": "runs/workspace/storage-owner.json",
        "member": "runs/workspace/storage-member.json",
    })

    assert "browser.newContext" in generated
    assert "process.env.PARALLAX_OWNER_STORAGE_STATE" in generated
    assert "requires PARALLAX_OWNER_STORAGE_STATE" in generated
    assert "process.env.PARALLAX_MEMBER_STORAGE_STATE" in generated
    assert "requires PARALLAX_MEMBER_STORAGE_STATE" in generated
    assert "runs/workspace/storage-" not in generated
    assert 'senderPage.locator("#member").fill("ada")' in generated
    assert 'senderPage.locator("form.remove-member")' in generated
    assert "expect.poll" in generated
    assert "toBeLessThanOrEqual(10)" in generated
    assert "revocationLagMs" in generated
    assert 'receiverPage.locator(".workspace-data")' in generated
    assert "toBeFalsy()" in generated


def test_propagation_spec_replays_the_declared_action_and_json_effect() -> None:
    sender = make_testimony(Context(privilege=Privilege.OWNER, varies=Axis.RELATIONAL))
    receiver = make_testimony(Context(privilege=Privilege.MEMBER, varies=Axis.RELATIONAL))
    item = finding(FindingKind.PROPAGATION_FAILURE, axis=Axis.RELATIONAL, testimonies=[sender, receiver])
    item.replay = RelationalReplay(
        sender=Privilege.OWNER,
        receiver=Privilege.MEMBER,
        action=FormAction(
            "form.composer",
            ("input[value='quiet']",),
            (("#message", "Ship it"),),
        ),
        effect=EffectExpectation(
            "json_contains",
            url="api/messages?since=0",
            items="messages",
            field="text",
            equals="Ship it",
        ),
        deadline_ms=3000,
    )

    generated = spec_for(item, {
        "owner": "runs/workspace/storage-owner.json",
        "member": "runs/workspace/storage-member.json",
    })

    assert "browser.newContext" in generated
    assert 'senderPage.locator("input[value=\'quiet\']").check()' in generated
    assert 'senderPage.locator("#message").fill("Ship it")' in generated
    assert "form.requestSubmit()" in generated
    assert 'url: "api/messages?since=0"' in generated
    assert "expect.poll" in generated
    assert "toBeTruthy()" in generated
    assert "test.skip" not in generated


def test_relational_finding_without_a_replay_declaration_is_explicitly_skipped() -> None:
    generated = spec_for(finding(FindingKind.PROPAGATION_FAILURE, axis=Axis.RELATIONAL))

    assert "test.skip" in generated
    assert "no replayable relational declaration" in generated
    assert "expect.poll" not in generated


def test_render_defects_have_specific_invariants() -> None:
    expected = {
        Defect.HORIZONTAL_OVERFLOW: "document.documentElement.scrollWidth <= window.innerWidth + 1",
        Defect.OFFSCREEN_CONTROL: "box.right <= window.innerWidth",
        Defect.SMALL_TAP_TARGET: "Math.min(box!.width, box!.height)).toBeGreaterThanOrEqual(44)",
        Defect.LOW_CONTRAST: "contrastRatio",
        Defect.UNTRANSLATED: "rawI18nKey",
        Defect.CLIPPED: "element.scrollHeight <= element.clientHeight",
    }
    for defect, assertion in expected.items():
        generated = spec_for(
            finding(
                FindingKind.RENDER_DEFECT,
                axis=Axis.VIEWPORT,
                testimonies=[make_testimony(
                    Context(viewport=MOBILE, varies=Axis.VIEWPORT),
                    defects=[defect],
                    observations=[DefectObservation(
                        defect,
                        "main > a:nth-of-type(1)",
                        '{"required": 4.5}' if defect is Defect.LOW_CONTRAST else "measured",
                    )],
                )],
            )
        )
        assert assertion in generated


def test_render_spec_uses_the_explicit_finding_defect_when_testimony_has_several() -> None:
    surface = Surface(SurfaceKind.ROUTE, "https://example.com/cart")
    testimony = WitnessTestimony(
        surface=surface,
        context=Context(viewport=MOBILE, varies=Axis.VIEWPORT),
        outcome=Outcome.PARTIAL,
        defects=[Defect.HORIZONTAL_OVERFLOW, Defect.SMALL_TAP_TARGET],
        observations=[
            DefectObservation(Defect.HORIZONTAL_OVERFLOW, "table.cart", "overflow"),
            DefectObservation(Defect.SMALL_TAP_TARGET, "button.decrease", "24px"),
        ],
    )
    item = Finding(
        FindingKind.RENDER_DEFECT,
        Severity.MEDIUM,
        surface,
        Axis.VIEWPORT,
        "small target",
        [testimony],
        defect=Defect.SMALL_TAP_TARGET,
    )

    generated = spec_for(item)

    assert 'page.locator("button.decrease").boundingBox()' in generated
    assert 'page.locator("table.cart")' not in generated


def test_offscreen_spec_measures_the_viewport_inside_the_page() -> None:
    defect = Defect.OFFSCREEN_CONTROL
    generated = spec_for(finding(
        FindingKind.RENDER_DEFECT,
        axis=Axis.VIEWPORT,
        testimonies=[make_testimony(
            Context(viewport=MOBILE, varies=Axis.VIEWPORT),
            defects=[defect],
            observations=[DefectObservation(defect, ".checkout-action-row .button", "measured")],
        )],
    ))

    assert 'page.locator(".checkout-action-row .button").evaluate((element) => {' in generated
    assert "const box = element.getBoundingClientRect()" in generated
    assert "box!.x + box!.width <= window.innerWidth" not in generated


def test_probe_source_measures_offscreen_controls_against_the_viewport() -> None:
    source = (Path(__file__).parents[1] / "src/parallax/probe.js").read_text(encoding="utf-8")
    offscreen = source.split("// --------------------------------------------------- 2. offscreen controls", 1)[1].split(
        "// ------------------------------------------------------------- 3. clipping", 1
    )[0]

    assert "r.right > view.width" in offscreen
    assert "document.documentElement.scrollWidth" not in offscreen
    assert "scrollableAncestor(el)" in offscreen


def test_probe_source_detects_vertical_hidden_clipping() -> None:
    source = (Path(__file__).parents[1] / "src/parallax/probe.js").read_text(encoding="utf-8")
    clipping = source.split("// ------------------------------------------------------------- 3. clipping", 1)[1].split(
        "// ------------------------------------------------------------- 4. contrast", 1
    )[0]

    assert "el.scrollHeight > el.clientHeight" in clipping
    assert "s.overflowY" in clipping


def test_render_spec_uses_the_probe_selector_for_its_defect() -> None:
    surface = Surface(SurfaceKind.ROUTE, "https://example.com/")
    testimony = WitnessTestimony(
        surface=surface,
        context=Context(viewport=MOBILE, varies=Axis.VIEWPORT),
        outcome=Outcome.PARTIAL,
        defects=[Defect.SMALL_TAP_TARGET],
        observations=[DefectObservation(
            Defect.SMALL_TAP_TARGET,
            "body > div:nth-of-type(1) > a:nth-of-type(1)",
            "width 31px, height 18px",
        )],
    )

    generated = spec_for(Finding(
        FindingKind.RENDER_DEFECT,
        Severity.MEDIUM,
        surface,
        Axis.VIEWPORT,
        "a tap target is smaller than the 44px minimum",
        [testimony],
    ))

    assert 'page.locator("body > div:nth-of-type(1) > a:nth-of-type(1)")' in generated
    assert 'page.locator("body")' not in generated
    assert "Math.min(box!.width, box!.height)).toBeGreaterThanOrEqual(44)" in generated


def test_selectorless_render_evidence_is_explicitly_skipped() -> None:
    surface = Surface(SurfaceKind.ROUTE, "https://example.com/")
    testimony = WitnessTestimony(
        surface=surface,
        context=Context(viewport=MOBILE, varies=Axis.VIEWPORT),
        outcome=Outcome.PARTIAL,
        defects=[Defect.SMALL_TAP_TARGET],
    )

    generated = spec_for(Finding(
        FindingKind.RENDER_DEFECT,
        Severity.MEDIUM,
        surface,
        Axis.VIEWPORT,
        "a tap target is smaller than the 44px minimum",
        [testimony],
    ))

    assert 'test.skip("Parallax cannot assert small_tap_target: the probe recorded no element selector.")' in generated
    assert "boundingBox" not in generated
    assert 'page.locator("body")' not in generated


def test_mirror_finding_replays_baseline_and_rtl_geometry_in_two_contexts() -> None:
    baseline = make_testimony(BASELINE)
    rtl = make_testimony(
        Context(locale=Locale.AR, varies=Axis.LOCALE),
        defects=[Defect.RTL_NOT_MIRRORED],
        observations=[DefectObservation(
            Defect.RTL_NOT_MIRRORED,
            "#nav",
            '{"expected":{"x":1220,"y":10,"w":200,"h":40},"actual":{"x":20,"y":10,"w":200,"h":40}}',
        )],
    )
    generated = spec_for(
        finding(FindingKind.RENDER_DEFECT, axis=Axis.LOCALE, testimonies=[baseline, rtl]),
        {"owner": "runs/site/storage-owner.json"},
    )

    assert generated.count("browser.newContext") == 2
    assert 'baselinePage.locator("#nav").boundingBox()' in generated
    assert 'variantPage.locator("#nav").boundingBox()' in generated
    assert "variantViewportWidth - baselineBox!.x - variantBox!.width" in generated
    assert "toBeLessThanOrEqual(3)" in generated
    assert "test.skip" not in generated


def test_locale_specs_replay_the_contextual_query_that_produced_the_finding() -> None:
    surface = Surface(
        SurfaceKind.ROUTE,
        "https://demo.example/admin/exports?lang=en&theme=light&return=%2Fadmin",
    )
    baseline = WitnessTestimony(surface, BASELINE, Outcome.REACHED)
    arabic = WitnessTestimony(
        surface,
        Context(locale=Locale.AR, varies=Axis.LOCALE),
        Outcome.PARTIAL,
        defects=[Defect.UNTRANSLATED],
        observations=[DefectObservation(Defect.UNTRANSLATED, "main")],
    )
    generated = spec_for(Finding(
        FindingKind.RENDER_DEFECT,
        Severity.MEDIUM,
        surface,
        Axis.LOCALE,
        "Arabic rendering is untranslated",
        [baseline, arabic],
        defect=Defect.UNTRANSLATED,
    ))

    assert 'page.goto("/admin/exports?lang=ar&theme=light&return=%2Fadmin")' in generated
    assert 'page.goto("/admin/exports?lang=en&theme=light&return=%2Fadmin")' not in generated


def test_geometry_specs_replay_baseline_and_contextual_variant_queries() -> None:
    surface = Surface(
        SurfaceKind.ROUTE,
        "https://demo.example/admin?lang=en&theme=light",
    )
    baseline = WitnessTestimony(surface, BASELINE, Outcome.REACHED)
    dark = WitnessTestimony(
        surface,
        Context(theme=Theme.DARK, varies=Axis.THEME),
        Outcome.PARTIAL,
        defects=[Defect.THEME_LAYOUT_SHIFT],
        observations=[DefectObservation(Defect.THEME_LAYOUT_SHIFT, "main")],
    )
    generated = spec_for(Finding(
        FindingKind.RENDER_DEFECT,
        Severity.MEDIUM,
        surface,
        Axis.THEME,
        "Dark mode moves the layout",
        [baseline, dark],
        defect=Defect.THEME_LAYOUT_SHIFT,
    ))

    assert 'baselinePage.goto("/admin?lang=en&theme=light")' in generated
    assert 'variantPage.goto("/admin?lang=en&theme=dark")' in generated


def test_theme_geometry_spec_compares_position_and_size() -> None:
    baseline = make_testimony(BASELINE)
    dark = make_testimony(
        Context(theme=Theme.DARK, varies=Axis.THEME),
        defects=[Defect.THEME_LAYOUT_SHIFT],
        observations=[DefectObservation(Defect.THEME_LAYOUT_SHIFT, "main", "measured")],
    )

    generated = spec_for(finding(
        FindingKind.RENDER_DEFECT,
        axis=Axis.THEME,
        testimonies=[baseline, dark],
    ))

    assert "variantBox!.x - baselineBox!.x" in generated
    assert "variantBox!.width - baselineBox!.width" in generated
    assert "variantBox!.height - baselineBox!.height" in generated
    assert "test.skip" not in generated


def test_contrast_spec_uses_the_probe_threshold() -> None:
    testimony = make_testimony(
        Context(viewport=MOBILE, varies=Axis.VIEWPORT),
        defects=[Defect.LOW_CONTRAST],
        observations=[DefectObservation(
            Defect.LOW_CONTRAST,
            "main > p:nth-of-type(1)",
            '{"required": 3.0}',
        )],
    )

    generated = spec_for(finding(
        FindingKind.RENDER_DEFECT,
        axis=Axis.VIEWPORT,
        testimonies=[testimony],
    ))

    assert "expect(contrastRatio).toBeGreaterThanOrEqual(3.0)" in generated
    assert "while (background && background !== document.documentElement)" in generated
    assert "background = background.parentElement" in generated
    assert "return [255, 255, 255]" in generated


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


def test_render_filenames_are_distinct_by_defect_on_the_same_surface() -> None:
    overflow = finding(FindingKind.RENDER_DEFECT, axis=Axis.VIEWPORT)
    overflow.defect = Defect.HORIZONTAL_OVERFLOW
    small_target = finding(FindingKind.RENDER_DEFECT, axis=Axis.VIEWPORT)
    small_target.defect = Defect.SMALL_TAP_TARGET

    assert filename_for(overflow) != filename_for(small_target)


def test_emit_all_writes_exactly_the_expected_files(tmp_path: Path) -> None:
    findings = [
        finding(FindingKind.ESCALATION),
        finding(FindingKind.CAPABILITY_DRIFT, axis=Axis.VIEWPORT),
    ]

    written = emit_all(findings, tmp_path)

    assert written == [tmp_path / filename_for(item) for item in findings]
    assert {path.name for path in tmp_path.iterdir()} == {filename_for(item) for item in findings}
    assert all(path.read_text(encoding="utf-8") == spec_for(item) for path, item in zip(written, findings))


def test_emit_all_replaces_the_previous_generation_without_deleting_unmanaged_files(tmp_path: Path) -> None:
    retained = finding(FindingKind.ESCALATION)
    obsolete = finding(FindingKind.CAPABILITY_DRIFT, axis=Axis.VIEWPORT)
    emit_all([retained, obsolete], tmp_path)
    unmanaged = tmp_path / "handwritten.spec.ts"
    unmanaged.write_text("// maintained by the operator\n", encoding="utf-8")

    written = emit_all([retained], tmp_path)

    assert written == [tmp_path / filename_for(retained)]
    assert not (tmp_path / filename_for(obsolete)).exists()
    assert unmanaged.read_text(encoding="utf-8") == "// maintained by the operator\n"


def test_a_run_without_credentials_emits_a_spec_that_can_open() -> None:
    """The guessed path made every credential-free spec fail on ENOENT first."""
    surface = Surface(SurfaceKind.ROUTE, "https://example.com/")
    owner = Context(privilege=Privilege.OWNER, varies=Axis.VIEWPORT)

    generated = spec_for(
        Finding(FindingKind.RENDER_DEFECT, Severity.MEDIUM, surface, Axis.VIEWPORT, "tap target too small", [
            WitnessTestimony(surface, owner, Outcome.PARTIAL),
        ]),
        storage_states=None,
    )

    assert "storageState" not in generated
    assert "runs/site/" not in generated


def test_a_model_only_render_finding_produces_no_spec(tmp_path) -> None:
    """The vision lens reports a judgement, not a geometry the emitter can assert.

    Writing a spec anyway produced a file that threw unconditionally, so it
    failed against a healthy application exactly as loudly as against a broken
    one. The project's claim is that a finding becomes a test; a test that
    cannot pass is not a test of the application.
    """
    from parallax.emitter import emit_all, is_expressible

    measured = replace(
        finding(FindingKind.RENDER_DEFECT, axis=Axis.VIEWPORT), defect=Defect.HORIZONTAL_OVERFLOW
    )
    judged = replace(finding(FindingKind.RENDER_DEFECT, axis=Axis.VIEWPORT), defect=None)

    assert is_expressible(measured) is True
    assert is_expressible(judged) is False

    written = emit_all([measured, judged], tmp_path)

    assert len(written) == 1
    for path in written:
        assert "did not include a known defect" not in path.read_text(encoding="utf-8")


def test_every_emitted_spec_asserts_something_about_the_page(tmp_path) -> None:
    from parallax.emitter import emit_all

    base = finding(FindingKind.RENDER_DEFECT, axis=Axis.VIEWPORT)
    written = emit_all(
        [replace(base, defect=d) for d in (
            Defect.HORIZONTAL_OVERFLOW, Defect.LOW_CONTRAST, Defect.SMALL_TAP_TARGET,
        )],
        tmp_path,
    )

    assert written
    for path in written:
        body = path.read_text(encoding="utf-8")
        assert "expect" in body, path.name
        assert "throw new Error(\"Parallax render finding" not in body, path.name
