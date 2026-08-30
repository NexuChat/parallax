"""Geometry-based invariants for locale and theme witnesses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .types import Axis, Context, Defect, Testimony


_TOLERANCE_PX = 3.0
_BOX_KEYS = ("x", "y", "w", "h")


@dataclass(frozen=True)
class MirrorOffender:
    """One named geometry mismatch, ready for an emitter to quote."""

    selector: str
    expected: dict[str, float]
    actual: dict[str, float] | None


_AXIS_DEFECT = {
    Axis.LOCALE: Defect.RTL_NOT_MIRRORED,
    Axis.THEME: Defect.THEME_LAYOUT_SHIFT,
}


def mirror_defects(baseline: Testimony, variant: Testimony) -> list[Defect]:
    """Return the render defect appropriate to the variant's comparison axis."""
    defect = _AXIS_DEFECT.get(variant.context.varies)
    if defect is not None and mirror_report(baseline, variant):
        return [defect]
    return []


def mirror_report(baseline: Testimony, variant: Testimony) -> list[MirrorOffender]:
    """Name geometry mismatches for an RTL or theme variant.

    RTL boxes are compared with the baseline x coordinate reflected about the
    viewport. Theme boxes are compared directly. Missing geometry and witnesses
    that did not reach the surface are deliberately treated as no evidence.
    """
    if not _can_compare(baseline, variant):
        return []

    axis = variant.context.varies
    if axis is Axis.THEME:
        if baseline.layout_signature and variant.layout_signature:
            if baseline.layout_signature == variant.layout_signature:
                return []
        return _box_mismatches(baseline, variant, mirrored=False)

    if axis is Axis.LOCALE:
        return _box_mismatches(baseline, variant, mirrored=True)
    return []


def _can_compare(baseline: Testimony, variant: Testimony) -> bool:
    return (
        baseline.reached
        and variant.reached
        and baseline.surface.id == variant.surface.id
        and bool(baseline.geometry)
        and bool(variant.geometry)
        and variant.context.varies in (Axis.LOCALE, Axis.THEME)
    )


def _box_mismatches(
    baseline: Testimony, variant: Testimony, *, mirrored: bool
) -> list[MirrorOffender]:
    remaining = list(variant.geometry)
    offenders: list[MirrorOffender] = []
    # Across locales only *position* is an invariant: translated text legitimately
    # renders wider, narrower or taller, and flagging that would drown the real
    # signal. Across themes nothing at all may move, so size is compared too.
    compared = ("x", "y") if mirrored else _BOX_KEYS
    for source in baseline.geometry:
        target_index = _matching_index(source, remaining)
        name = _name(source)
        if _box(source) is None:
            continue
        if target_index is None:
            expected = _expected_box(source, baseline.context, mirrored=mirrored, actual=None)
            offenders.append(MirrorOffender(name, expected or {}, None))
            continue

        target = remaining.pop(target_index)
        if mirrored and _text_changed(source, target):
            continue
        actual = _box(target)
        expected = _expected_box(source, baseline.context, mirrored=mirrored, actual=actual)
        if expected is None:
            continue
        if actual is None or not _within_tolerance(expected, actual, compared):
            offenders.append(MirrorOffender(name, expected, actual))
    return offenders


def _text_changed(source: dict[str, Any], target: dict[str, Any]) -> bool:
    baseline_text = source.get("text")
    variant_text = target.get("text")
    return (
        isinstance(baseline_text, str)
        and isinstance(variant_text, str)
        and baseline_text != variant_text
    )


def _matching_index(source: dict[str, Any], candidates: list[dict[str, Any]]) -> int | None:
    selector = source.get("selector")
    if selector:
        for index, candidate in enumerate(candidates):
            if candidate.get("selector") == selector:
                return index

    fallback = _fallback_key(source)
    if fallback is not None:
        for index, candidate in enumerate(candidates):
            if _fallback_key(candidate) == fallback:
                return index
    return None


def _fallback_key(box: dict[str, Any]) -> tuple[str, str] | None:
    tag, text = box.get("tag"), box.get("text")
    if isinstance(tag, str) and isinstance(text, str):
        return tag, text
    return None


def _name(box: dict[str, Any]) -> str:
    selector = box.get("selector")
    if isinstance(selector, str) and selector:
        return selector
    fallback = _fallback_key(box)
    if fallback is not None:
        tag, text = fallback
        return f"{tag}[text={text!r}]"
    return "<unidentified element>"


def _expected_box(
    source: dict[str, Any],
    context: Context,
    *,
    mirrored: bool,
    actual: dict[str, float] | None,
) -> dict[str, float] | None:
    """Where the variant's box belongs if the layout mirrored correctly.

    Mirroring preserves an element's distance from the *opposite* edge: what sat
    `x` from the left in LTR must sit `x` from the right in RTL, so
    `x' = W - x - w`. The width in that equation is the variant's own, because
    the same element translated into Arabic may render wider or narrower — and
    that is a translation, not a mirroring failure.
    """
    box = _box(source)
    if box is None or not mirrored:
        return box
    width = (actual or box)["w"]
    box["x"] = context.viewport.width - box["x"] - width
    return box


def _box(source: dict[str, Any]) -> dict[str, float] | None:
    try:
        values = {key: float(source[key]) for key in _BOX_KEYS}
    except (KeyError, TypeError, ValueError):
        return None
    return values


def _within_tolerance(
    expected: dict[str, float], actual: dict[str, float], keys: tuple[str, ...]
) -> bool:
    return all(abs(expected[key] - actual[key]) <= _TOLERANCE_PX for key in keys)
