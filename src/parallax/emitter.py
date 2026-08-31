"""Emit deterministic Playwright regression specs from Parallax findings."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from pathlib import Path
from urllib.parse import quote, urlsplit

from .types import (
    Axis,
    Context,
    Defect,
    DefectObservation,
    EffectExpectation,
    Finding,
    FindingKind,
    Privilege,
    RelationalReplay,
    SurfaceKind,
    Testimony,
)
from .witness import contextual_url


def _ts(value: str) -> str:
    """Return a TypeScript string literal without interpolation hazards."""
    return json.dumps(value, ensure_ascii=True).replace("${", r"\u0024{")


def _comment(value: str) -> str:
    """Keep untrusted evidence inside a one-line comment safely."""
    return value.replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n").replace("*/", "*\\/")


def _base_url_path(value: str) -> str:
    """Return a route suitable for Playwright's configured baseURL."""
    parts = urlsplit(value)
    path = parts.path or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    query = quote(parts.query, safe="!$&'()*+,;=@%")
    return f"{path}?{query}" if query else path


def _witness_path(finding: Finding, testimony: Testimony) -> str:
    return _base_url_path(contextual_url(finding.surface.path, testimony.context))


def _storage_state_path(privilege: str, storage_states: Mapping[str, str] | None) -> str | None:
    """Return the state file the run actually used for this role, or none.

    Guessing a path from the finding's URL produced specs that could not run: a
    root-level route yielded the literal "runs/site/storage-owner.json", and a
    sweep given no credentials still claimed one. A spec that cannot open its
    storage state fails on ENOENT before reaching a single assertion, which turns
    the one deliverable that is supposed to prove the finding into noise. A
    supplied state enables an environment-only reference; its path is never
    embedded, and anonymous witnesses carry none.
    """
    if privilege == "anon" or not storage_states:
        return None
    path = storage_states.get(privilege)
    return str(path) if path else None


def _storage_state_expression(context: Context, path: str | None) -> str | None:
    if path is None:
        return None
    variable = f"PARALLAX_{context.privilege.value.upper()}_STORAGE_STATE"
    return f'''(() => {{
    const storageState = process.env.{variable};
    if (!storageState) throw new Error({_ts(f"Parallax generated spec requires {variable}")});
    return storageState;
  }})()'''


def _context_for(finding: Finding) -> Testimony:
    """Choose the witness that must reproduce the regression, deterministically."""
    if finding.kind is FindingKind.ESCALATION:
        candidates = [t for t in finding.testimonies if t.context.privilege.value != "owner"]
    elif finding.kind is FindingKind.POLICY_INVERSION:
        candidates = [t for t in finding.testimonies if t.context.privilege.value == "owner"]
    elif finding.axis is Axis.BASELINE:
        candidates = list(finding.testimonies)
    else:
        candidates = [t for t in finding.testimonies if t.context.varies is finding.axis]
    return sorted(candidates or finding.testimonies, key=lambda t: t.context.name)[0]


def _target(finding: Finding, selector: str | None = None) -> str:
    if selector:
        return f"page.locator({_ts(selector)})"
    if finding.surface.kind is SurfaceKind.ROUTE:
        return 'page.locator("body")'
    if finding.surface.selector:
        return f"page.locator({_ts(finding.surface.selector)})"
    if finding.surface.label:
        return f"page.getByText({_ts(finding.surface.label)}, {{ exact: true }})"
    return 'page.locator("[data-parallax-surface]")'


def _reachability_assertion(finding: Finding, *, must_reach: bool) -> str:
    target = _target(finding)
    affordance = finding.surface.kind is SurfaceKind.AFFORDANCE
    if must_reach:
        control = f"await {target}.isVisible()" if affordance else "(response?.status() ?? 500) < 400"
        return f'''  const reached = !isLoginPage && {control};
  expect(reached).toBeTruthy();'''
    absent = f"!(await {target}.isVisible().catch(() => false))" if affordance else "false"
    return f'''  const blocked = isLoginPage || response?.status() === 403 || {absent};
  expect(blocked).toBeTruthy();'''


def _render_observation(finding: Finding, witness: Testimony) -> tuple[Defect | None, DefectObservation | None]:
    defect = finding.defect
    if defect is None:
        defects = sorted(
            {item for testimony in finding.testimonies for item in testimony.defects},
            key=lambda item: item.value,
        )
        defect = defects[0] if defects else None
    observation = next((item for item in witness.observations if item.defect is defect), None)
    return defect, observation


def _render_skip(defect: Defect, reason: str) -> str:
    return f'''  test.skip({_ts(f"Parallax cannot assert {defect.value}: {reason}")});
  // The rendered test has no honest assertion for this observation.'''


def _detail_number(observation: DefectObservation, key: str) -> float | None:
    try:
        value = json.loads(observation.detail).get(key)
    except (AttributeError, TypeError, ValueError):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _render_assertion(finding: Finding) -> str:
    witness = _context_for(finding)
    defect, observation = _render_observation(finding, witness)
    if defect is None:
        # Unreachable through emit_all, which declines to write a spec for a
        # finding it cannot express. Kept as a loud failure rather than a quiet
        # pass in case a caller reaches spec_for directly.
        return "  throw new Error(\"Parallax render finding did not include a known defect\");"
    if observation is None or not observation.selector:
        return _render_skip(defect, "the probe recorded no element selector.")
    if defect is Defect.HORIZONTAL_OVERFLOW:
        return "  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();"
    target = _target(finding, observation.selector)
    if defect is Defect.OFFSCREEN_CONTROL:
        return f'''  const withinViewport = await {target}.evaluate((element) => {{
    const box = element.getBoundingClientRect();
    return box.left >= 0 && box.right <= window.innerWidth;
  }});
  expect(withinViewport).toBeTruthy();'''
    if defect is Defect.SMALL_TAP_TARGET:
        return f'''  const box = await {target}.boundingBox();
  expect(box).not.toBeNull();
  expect(Math.min(box!.width, box!.height)).toBeGreaterThanOrEqual(44);'''
    if defect is Defect.CLIPPED:
        return f"  expect(await {target}.evaluate((element) => element.scrollWidth <= element.clientWidth && element.scrollHeight <= element.clientHeight)).toBeTruthy();"
    if defect is Defect.LOW_CONTRAST:
        threshold = _detail_number(observation, "required")
        if threshold is None:
            return _render_skip(defect, "the probe recorded no contrast threshold.")
        return f'''  const contrastRatio = await {target}.evaluate((element) => {{
    const parseColor = (value: string) => {{
      const match = value.match(/rgba?\\(([^)]+)\\)/);
      if (!match) return null;
      const channels = match[1].split(",").map(Number);
      if (channels.length === 4 && channels[3] === 0) return null;
      return channels.slice(0, 3);
    }};
    const luminance = (color: number[]) => color.map(channel => {{ const s = channel / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; }}).reduce((total, channel, index) => total + channel * [0.2126, 0.7152, 0.0722][index], 0);
    const backdrop = () => {{
      let background: Element | null = element;
      while (background && background !== document.documentElement) {{
        const color = parseColor(getComputedStyle(background).backgroundColor);
        if (color) return color;
        background = background.parentElement;
      }}
      return [255, 255, 255];
    }};
    const foreground = parseColor(getComputedStyle(element).color);
    if (!foreground) throw new Error("Parallax could not parse the recorded element color");
    const a = luminance(foreground); const b = luminance(backdrop());
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  }});
  expect(contrastRatio).toBeGreaterThanOrEqual({threshold});'''
    if defect is Defect.UNTRANSLATED:
        return f'''  const rawI18nKey = await {target}.evaluate((element) => {{
    const text = (element.textContent ?? "").trim();
    const rawKey = /(⟦[^⟧]+⟧)|(\\{{\\{{[^}}]+\\}}\\}})|(^[a-z][a-z0-9]*(\\.[a-z0-9_]+){{2,}}$)/i.test(text);
    const latin = text.match(/\\b[A-Za-z]{{3,}}\\b/g) ?? [];
    return rawKey || (document.documentElement.lang.toLowerCase().startsWith("ar") && latin.length >= 2 && !/[@/\\\\_]|\\d{{3,}}/.test(text));
  }});
  expect(rawI18nKey).toBeFalsy();'''
    if defect is Defect.THEME_LAYOUT_SHIFT:
        return _render_skip(defect, "the probe has no replayable cross-theme geometry assertion.")
    if defect is Defect.RTL_NOT_MIRRORED:
        return _render_skip(defect, "the probe has no replayable cross-locale geometry assertion.")
    return "  throw new Error(\"Parallax render finding did not include a known defect\");"


def _content_assertion(finding: Finding) -> str:
    baseline = next((t for t in finding.testimonies if t.context.varies is Axis.BASELINE), None)
    expected = baseline.content_signature if baseline else None
    if not expected:
        expected = next((t.content_signature for t in finding.testimonies if t.content_signature), "")
    # The recorded signature came from probe.js, which hashes with FNV-1a over the
    # page's normalised innerText. Any other hash — SHA-256 included — would make
    # this spec fail for a reason that has nothing to do with the finding.
    return f'''  const contentSignature = await page.evaluate(() => {{
    const root = document.querySelector("main") ?? document.body;
    const text = (root.innerText || "").replace(/\\s+/g, " ").trim();
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) {{ h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); }}
    return (h >>> 0).toString(16);
  }});
  expect(contentSignature).toBe({_ts(expected)});'''


def _relational_context(finding: Finding, privilege: Privilege) -> Context:
    return next(
        (testimony.context for testimony in finding.testimonies if testimony.context.privilege is privilege),
        Context(privilege=privilege, varies=Axis.RELATIONAL),
    )


def _context_literal(context: Context, storage_state: str | None) -> str:
    storage_expression = _storage_state_expression(context, storage_state)
    storage_line = f"\n    storageState: {storage_expression}," if storage_expression else ""
    return f'''{{
    baseURL,
    viewport: {{ width: {context.viewport.width}, height: {context.viewport.height} }},
    locale: {_ts(context.locale.value)},
    colorScheme: {_ts(context.theme.value)},{storage_line}
  }}'''


def _effect_expression(page: str, effect: EffectExpectation) -> str | None:
    if effect.kind == "visible" and effect.selector:
        return f'await {page}.locator({_ts(effect.selector)}).isVisible().catch(() => false)'
    if effect.kind == "json_contains" and all((effect.url, effect.items, effect.field, effect.equals)):
        expectation = (
            f'{{ url: {_ts(effect.url or "")}, items: {_ts(effect.items or "")}, '
            f'field: {_ts(effect.field or "")}, equals: {_ts(effect.equals or "")} }}'
        )
        return f'''await {page}.evaluate(async (expectation) => {{
      const response = await fetch(new URL(expectation.url, location.href));
      if (!response.ok) return false;
      const payload = await response.json();
      return Array.isArray(payload[expectation.items]) && payload[expectation.items]
        .some((item) => item && item[expectation.field] === expectation.equals);
    }}, {expectation})'''
    return None


def _action_lines(page: str, replay: RelationalReplay) -> str:
    lines = [f"  await {page}.locator({_ts(selector)}).check();" for selector in replay.action.checks]
    lines.extend(
        f"  await {page}.locator({_ts(selector)}).fill({_ts(value)});"
        for selector, value in replay.action.fills
    )
    lines.append(
        f"  await {page}.locator({_ts(replay.action.form)}).evaluate((form: HTMLFormElement) => form.requestSubmit());"
    )
    return "\n".join(lines)


def _relational_spec(
    finding: Finding,
    storage_states: Mapping[str, str] | None,
) -> str:
    title = _ts(f"Parallax: {finding.id}")
    replay = finding.replay
    reason: str | None = None
    effect: str | None = None
    if replay is None:
        reason = "no replayable relational declaration was retained with this finding"
    else:
        effect = _effect_expression("receiverPage", replay.effect)
        if effect is None:
            reason = "the receiver effect is outside the replayable scenario vocabulary"
    sender_state = _storage_state_path(replay.sender.value, storage_states) if replay else None
    receiver_state = _storage_state_path(replay.receiver.value, storage_states) if replay else None
    if replay and replay.sender is not Privilege.ANON and sender_state is None:
        reason = f"no storage state was supplied for the {replay.sender.value} sender"
    if replay and replay.receiver is not Privilege.ANON and receiver_state is None:
        reason = f"no storage state was supplied for the {replay.receiver.value} receiver"
    if finding.kind is FindingKind.REVOCATION_LAG and replay and replay.max_lag_ms is None:
        reason = "the revocation declaration did not retain an acceptable lag threshold"
    header = f'''/*
 * Parallax generated relational regression spec
 * Finding: {_comment(finding.id)}
 * Axis: {_comment(finding.axis.value)}
 * Evidence: {_comment(finding.evidence_line())}
 * In playwright.config.ts: use: {{ baseURL: "https://your-app.example" }}
 */
import {{ test, expect }} from "@playwright/test";
'''
    if reason or replay is None or effect is None:
        return f'''{header}
test({title}, async () => {{
  test.skip({_ts(f"Parallax cannot replay this relation: {reason}")});
}});
'''
    sender = _relational_context(finding, replay.sender)
    receiver = _relational_context(finding, replay.receiver)
    action = _action_lines("senderPage", replay)
    if finding.kind is FindingKind.PROPAGATION_FAILURE:
        assertion = f'''{action}
  await expect.poll(async () => {effect}, {{ timeout: {replay.deadline_ms} }}).toBeTruthy();'''
    else:
        assertion = f'''  expect({effect}).toBeTruthy();
{action}
  const revocationCompletedAt = performance.now();
  await expect.poll(async () => {effect}, {{ timeout: {replay.deadline_ms} }}).toBeFalsy();
  const revocationLagMs = performance.now() - revocationCompletedAt;
  expect(revocationLagMs).toBeLessThanOrEqual({replay.max_lag_ms});'''
    return f'''{header}
test({title}, async ({{ browser }}) => {{
  const baseURL = test.info().project.use.baseURL;
  if (typeof baseURL !== "string") throw new Error("Parallax relational specs require use.baseURL in playwright.config.ts");
  const senderContext = await browser.newContext({_context_literal(sender, sender_state)});
  const receiverContext = await browser.newContext({_context_literal(receiver, receiver_state)});
  try {{
    const senderPage = await senderContext.newPage();
    const receiverPage = await receiverContext.newPage();
    await Promise.all([senderPage.goto({_ts(_base_url_path(finding.surface.path))}), receiverPage.goto({_ts(_base_url_path(finding.surface.path))})]);
{assertion}
  }} finally {{
    await Promise.all([senderContext.close(), receiverContext.close()]);
  }}
}});
'''


def _mirror_spec(
    finding: Finding, storage_states: Mapping[str, str] | None,
) -> str | None:
    defect = (
        Defect.RTL_NOT_MIRRORED if finding.axis is Axis.LOCALE
        else Defect.THEME_LAYOUT_SHIFT if finding.axis is Axis.THEME
        else None
    )
    if defect is None:
        return None
    baseline = next((item for item in finding.testimonies if item.context.varies is Axis.BASELINE), None)
    variant = next((item for item in finding.testimonies if defect in item.defects), None)
    observation = next(
        (item for item in variant.observations if item.defect is defect and item.selector),
        None,
    ) if variant else None
    if baseline is None or variant is None or observation is None or observation.selector is None:
        return None
    baseline_state = _storage_state_path(baseline.context.privilege.value, storage_states)
    variant_state = _storage_state_path(variant.context.privilege.value, storage_states)
    selector = _ts(observation.selector)
    if defect is Defect.RTL_NOT_MIRRORED:
        assertion = '''  const variantViewportWidth = await variantPage.evaluate(() => window.innerWidth);
  const expectedVariantX = variantViewportWidth - baselineBox!.x - variantBox!.width;
  expect(Math.abs(variantBox!.x - expectedVariantX)).toBeLessThanOrEqual(3);
  expect(Math.abs(variantBox!.y - baselineBox!.y)).toBeLessThanOrEqual(3);'''
    else:
        assertion = '''  expect(Math.abs(variantBox!.x - baselineBox!.x)).toBeLessThanOrEqual(3);
  expect(Math.abs(variantBox!.y - baselineBox!.y)).toBeLessThanOrEqual(3);
  expect(Math.abs(variantBox!.width - baselineBox!.width)).toBeLessThanOrEqual(3);
  expect(Math.abs(variantBox!.height - baselineBox!.height)).toBeLessThanOrEqual(3);'''
    return f'''/*
 * Parallax generated cross-context geometry regression spec
 * Finding: {_comment(finding.id)}
 * Axis: {_comment(finding.axis.value)}
 * Evidence: {_comment(finding.evidence_line())}
 * In playwright.config.ts: use: {{ baseURL: "https://your-app.example" }}
 */
import {{ test, expect }} from "@playwright/test";

test({_ts(f"Parallax: {finding.id}")}, async ({{ browser }}) => {{
  const baseURL = test.info().project.use.baseURL;
  if (typeof baseURL !== "string") throw new Error("Parallax geometry specs require use.baseURL in playwright.config.ts");
  const baselineContext = await browser.newContext({_context_literal(baseline.context, baseline_state)});
  const variantContext = await browser.newContext({_context_literal(variant.context, variant_state)});
  try {{
    const baselinePage = await baselineContext.newPage();
    const variantPage = await variantContext.newPage();
    await Promise.all([baselinePage.goto({_ts(_witness_path(finding, baseline))}), variantPage.goto({_ts(_witness_path(finding, variant))})]);
    const [baselineBox, variantBox] = await Promise.all([
      baselinePage.locator({selector}).boundingBox(),
      variantPage.locator({selector}).boundingBox(),
    ]);
    expect(baselineBox).not.toBeNull();
    expect(variantBox).not.toBeNull();
{assertion}
  }} finally {{
    await Promise.all([baselineContext.close(), variantContext.close()]);
  }}
}});
'''


def spec_for(finding: Finding, storage_states: Mapping[str, str] | None = None) -> str:
    """Render one self-contained, failing-until-fixed Playwright TypeScript spec."""
    if finding.kind in (FindingKind.PROPAGATION_FAILURE, FindingKind.REVOCATION_LAG):
        return _relational_spec(finding, storage_states)
    if finding.kind is FindingKind.RENDER_DEFECT:
        mirror = _mirror_spec(finding, storage_states)
        if mirror is not None:
            return mirror
    witness = _context_for(finding)
    context = witness.context
    path = _ts(_witness_path(finding, witness))
    title = _ts(f"Parallax: {finding.id}")
    storage_state = _storage_state_path(context.privilege.value, storage_states)
    storage_variable = (
        f"PARALLAX_{context.privilege.value.upper()}_STORAGE_STATE"
        if storage_state
        else None
    )
    storage_line = f"\n  storageState: process.env.{storage_variable}," if storage_variable else ""
    storage_note = (
        " * Set PARALLAX_<ROLE>_STORAGE_STATE to the role state file before running this spec."
        if storage_state
        else " * This run had no credentials for that role, so the spec opens the page anonymously."
    )
    setup = f'''test.use({{
  viewport: {{ width: {context.viewport.width}, height: {context.viewport.height} }},
  locale: {_ts(context.locale.value)},
  colorScheme: {_ts(context.theme.value)},{storage_line}
}});'''
    storage_guard = (
        f'''  if (!process.env.{storage_variable}) throw new Error({_ts(f"Parallax generated spec requires {storage_variable}")});
'''
        if storage_variable
        else ""
    )
    prelude = f'''{storage_guard}  const response = await page.goto({path});
  const isLoginPage = /\\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);'''
    if finding.kind is FindingKind.ESCALATION:
        assertion = _reachability_assertion(finding, must_reach=False)
    elif finding.kind in (FindingKind.POLICY_INVERSION, FindingKind.CAPABILITY_DRIFT):
        assertion = _reachability_assertion(finding, must_reach=True)
    elif finding.kind is FindingKind.RENDER_DEFECT:
        assertion = _render_assertion(finding)
    elif finding.kind is FindingKind.CONTENT_DIVERGENCE:
        assertion = _content_assertion(finding)
    elif finding.kind is FindingKind.DEAD_SURFACE:
        assertion = _reachability_assertion(finding, must_reach=True)
    else:
        prelude = ""
        assertion = f'''  test.skip({_ts(finding.summary)});
  // No assertion is emitted: this surface was unreachable for every witness.'''
    return f'''/*
 * Parallax generated regression spec
 * Finding: {_comment(finding.id)}
 * Axis: {_comment(finding.axis.value)}
 * Evidence: {_comment(finding.evidence_line())}
 * In playwright.config.ts: use: {{ baseURL: "https://your-app.example" }}
{storage_note}
 */
import {{ test, expect }} from "@playwright/test";

{setup}

test({title}, async ({{ page }}) => {{
{prelude}
{assertion}
}});
'''


def filename_for(finding: Finding) -> str:
    """Return a stable filesystem-safe name, unique to the finding identity."""
    identity = "|".join((
        finding.kind.value,
        finding.axis.value,
        finding.surface.kind.value,
        finding.surface.path,
        finding.surface.selector or "",
        finding.defect.value if finding.defect is not None else "",
    ))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"parallax-{finding.kind.value}-{finding.axis.value}-{digest}.spec.ts"


def is_expressible(finding: Finding) -> bool:
    """Whether this finding can become a check of the application, not of itself.

    A render finding from the vision lens has no measured defect behind it —
    the model said one tile disagreed with its peers, which is a judgement and
    not a geometry the emitter can assert. The honest answer is no spec.

    Emitting one anyway produced a file that threw unconditionally, so it failed
    against a fixed application exactly as loudly as against a broken one. That
    is worse than silence: the project's claim is that a finding becomes a test,
    and a test that cannot pass is not a test of anything.
    """
    return not (finding.kind is FindingKind.RENDER_DEFECT and finding.defect is None)


def emit_all(
    findings: Iterable[Finding], out_dir: Path, storage_states: Mapping[str, str] | None = None
) -> list[Path]:
    """Replace the generated spec set and return paths in input order."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for finding in findings:
        if not is_expressible(finding):
            continue
        path = out_dir / filename_for(finding)
        path.write_text(spec_for(finding, storage_states), encoding="utf-8")
        written.append(path)
    expected = set(written)
    for path in out_dir.glob("parallax-*.spec.ts"):
        if path not in expected and (path.is_file() or path.is_symlink()):
            path.unlink()
    return written
