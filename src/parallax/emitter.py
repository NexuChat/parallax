"""Emit deterministic Playwright regression specs from Parallax findings."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from urllib.parse import quote, urlsplit

from .types import Axis, Defect, Finding, FindingKind, SurfaceKind, Testimony


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


def _storage_state_path(privilege: str, storage_states: Mapping[str, str] | None) -> str | None:
    """Return the state file the run actually used for this role, or none.

    Guessing a path from the finding's URL produced specs that could not run: a
    root-level route yielded the literal "runs/site/storage-owner.json", and a
    sweep given no credentials still claimed one. A spec that cannot open its
    storage state fails on ENOENT before reaching a single assertion, which turns
    the one deliverable that is supposed to prove the finding into noise. Only a
    path the operator supplied is written, and anonymous witnesses carry none.
    """
    if privilege == "anon" or not storage_states:
        return None
    path = storage_states.get(privilege)
    return str(path) if path else None


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


def _target(finding: Finding) -> str:
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


def _render_assertion(finding: Finding) -> str:
    defects = sorted(
        {defect for testimony in finding.testimonies for defect in testimony.defects}, key=lambda defect: defect.value
    )
    defect = defects[0] if defects else None
    target = _target(finding)
    if defect is Defect.HORIZONTAL_OVERFLOW:
        return "  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBeTruthy();"
    if defect in (Defect.OFFSCREEN_CONTROL, Defect.CLIPPED):
        return f'''  const box = await {target}.boundingBox();
  expect(box).not.toBeNull();
  expect(await {target}.evaluate((_, box) => box.x >= 0 && box.y >= 0 && box.x + box.width <= window.innerWidth && box.y + box.height <= window.innerHeight, box!)).toBeTruthy();'''
    if defect is Defect.SMALL_TAP_TARGET:
        return f'''  const box = await {target}.boundingBox();
  expect(box).not.toBeNull();
  expect(Math.min(box!.width, box!.height)).toBeGreaterThanOrEqual(44);'''
    if defect is Defect.LOW_CONTRAST:
        return f'''  const contrastRatio = await {target}.evaluate((element) => {{
    const rgb = (value: string) => value.match(/\\d+(?:\\.\\d+)?/g)?.slice(0, 3).map(Number) ?? [0, 0, 0];
    const luminance = (color: number[]) => color.map(channel => {{ const s = channel / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; }}).reduce((total, channel, index) => total + channel * [0.2126, 0.7152, 0.0722][index], 0);
    const style = getComputedStyle(element); const a = luminance(rgb(style.color)); const b = luminance(rgb(style.backgroundColor));
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  }});
  expect(contrastRatio).toBeGreaterThanOrEqual(4.5);'''
    if defect is Defect.UNTRANSLATED:
        return '''  const rawI18nKey = await page.locator("body").evaluate((element) => /\\b[a-z][\\w-]*(?:\\.[a-z][\\w-]*)+\\b/i.test(element.textContent ?? ""));
  expect(rawI18nKey).toBeFalsy();'''
    if defect is Defect.THEME_LAYOUT_SHIFT:
        # Dark mode is allowed to recolour and nothing else, so the check is the
        # same page measured twice: only the colour scheme may differ.
        return '''  const fingerprint = () => page.evaluate(() => Array.from(
    document.querySelectorAll("header, nav, main, footer, aside, section, button, a[href], h1, h2, [role]")
  ).map((element) => {
    const rect = element.getBoundingClientRect();
    return element.tagName + ":" + Math.round(rect.x) + "," + Math.round(rect.y) + "," + Math.round(rect.width) + "," + Math.round(rect.height);
  }).join("|"));
  await page.emulateMedia({ colorScheme: "light" });
  const lightLayout = await fingerprint();
  await page.emulateMedia({ colorScheme: "dark" });
  expect(await fingerprint()).toBe(lightLayout);'''
    if defect is Defect.RTL_NOT_MIRRORED:
        return f'''  expect(await page.locator("html").getAttribute("dir")).toBe("rtl");
  expect(await {target}.evaluate((element) => getComputedStyle(element).direction)).toBe("rtl");'''
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
    const text = (document.body.innerText || "").replace(/\\s+/g, " ").trim();
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) {{ h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); }}
    return (h >>> 0).toString(16);
  }});
  expect(contentSignature).toBe({_ts(expected)});'''


def _revocation_assertion(finding: Finding) -> str:
    measurement = finding.revocation
    assert measurement is not None
    target = (
        f"page.locator({_ts(measurement.effect_selector)})"
        if measurement.effect_selector else _target(finding)
    )
    return f'''  const revocationCompletedAt = performance.now();
  await expect.poll(async () => await {target}.isVisible().catch(() => false), {{ timeout: {measurement.deadline_ms} }}).toBeFalsy();
  const revocationLagMs = performance.now() - revocationCompletedAt;
  expect(revocationLagMs).toBeLessThan({measurement.deadline_ms});'''


def spec_for(finding: Finding, storage_states: Mapping[str, str] | None = None) -> str:
    """Render one self-contained, failing-until-fixed Playwright TypeScript spec."""
    witness = _context_for(finding)
    context = witness.context
    path = _ts(_base_url_path(finding.surface.path))
    title = _ts(f"Parallax: {finding.id}")
    storage_state = _storage_state_path(context.privilege.value, storage_states)
    storage_line = f"\n  storageState: {_ts(storage_state)}," if storage_state else ""
    storage_note = (
        " * The storage state below is the file this run was given for that role."
        if storage_state
        else " * This run had no credentials for that role, so the spec opens the page anonymously."
    )
    setup = f'''test.use({{
  viewport: {{ width: {context.viewport.width}, height: {context.viewport.height} }},
  locale: {_ts(context.locale.value)},
  colorScheme: {_ts(context.theme.value)},{storage_line}
}});'''
    prelude = f'''  const response = await page.goto({path});
  const isLoginPage = /\\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);'''
    if finding.kind is FindingKind.ESCALATION:
        assertion = _reachability_assertion(finding, must_reach=False)
    elif finding.kind in (FindingKind.POLICY_INVERSION, FindingKind.CAPABILITY_DRIFT):
        assertion = _reachability_assertion(finding, must_reach=True)
    elif finding.kind is FindingKind.RENDER_DEFECT:
        assertion = _render_assertion(finding)
    elif finding.kind is FindingKind.CONTENT_DIVERGENCE:
        assertion = _content_assertion(finding)
    elif finding.kind is FindingKind.REVOCATION_LAG and finding.revocation is not None:
        assertion = _revocation_assertion(finding)
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
    identity = "|".join((finding.kind.value, finding.axis.value, finding.surface.kind.value, finding.surface.path, finding.surface.selector or ""))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"parallax-{finding.kind.value}-{finding.axis.value}-{digest}.spec.ts"


def emit_all(
    findings: Iterable[Finding], out_dir: Path, storage_states: Mapping[str, str] | None = None
) -> list[Path]:
    """Write one spec per finding and return paths in input order."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for finding in findings:
        path = out_dir / filename_for(finding)
        path.write_text(spec_for(finding, storage_states), encoding="utf-8")
        written.append(path)
    return written
