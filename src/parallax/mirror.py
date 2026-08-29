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


def mirror_defects(baseline: Testimony, variant: Testimony) -> list[Defect]:
    """Return render defects appropriate to the variant's comparison axis.

    Theme movement is reported by :func:`mirror_report`, but the current defect
    vocabulary only has a name for the RTL invariant.  It must not be used to
    describe a dark-mode layout shift.
    """
    if variant.context.varies is Axis.LOCALE and mirror_report(baseline, variant):
        return [Defect.RTL_NOT_MIRRORED]
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
    for source in baseline.geometry:
        target_index = _matching_index(source, remaining)
        expected = _expected_box(source, baseline.context, mirrored=mirrored)
        name = _name(source)
        if expected is None:
            continue
        if target_index is None:
            offenders.append(MirrorOffender(name, expected, None))
            continue

        actual_source = remaining.pop(target_index)
        actual = _box(actual_source)
        if actual is None or not _within_tolerance(expected, actual):
            offenders.append(MirrorOffender(name, expected, actual))
    return offenders


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
    source: dict[str, Any], context: Context, *, mirrored: bool
) -> dict[str, float] | None:
    result = _box(source)
    if result is not None and mirrored:
        result["x"] = context.viewport.width - result["x"] - result["w"]
    return result


def _box(source: dict[str, Any]) -> dict[str, float] | None:
    try:
        values = {key: float(source[key]) for key in _BOX_KEYS}
    except (KeyError, TypeError, ValueError):
        return None
    return values


def _within_tolerance(expected: dict[str, float], actual: dict[str, float]) -> bool:
    return all(abs(expected[key] - actual[key]) <= _TOLERANCE_PX for key in _BOX_KEYS)
