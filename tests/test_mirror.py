from __future__ import annotations

from parallax.mirror import mirror_defects, mirror_report
from parallax.types import (
    BASELINE,
    Axis,
    Context,
    Defect,
    Locale,
    Outcome,
    Surface,
    SurfaceKind,
    Testimony,
    Theme,
)


SURFACE = Surface(SurfaceKind.ROUTE, "/settings")
WIDTH = BASELINE.viewport.width


def box(selector: str, x: float, y: float, w: float, h: float, *, text: str = "") -> dict[str, object]:
    return {"selector": selector, "tag": "nav" if "nav" in selector else "main", "x": x, "y": y,
            "w": w, "h": h, "text": text}


def say(context: Context, geometry: list[dict[str, object]], **kwargs: object) -> Testimony:
    return Testimony(surface=SURFACE, context=context, outcome=Outcome.REACHED, geometry=geometry, **kwargs)


def test_correctly_mirrored_rtl_layout_has_no_defect() -> None:
    baseline = say(BASELINE, [box("#nav", 20, 10, 200, 40), box("main", 300, 80, 600, 500)])
    arabic = say(
        Context(locale=Locale.AR, varies=Axis.LOCALE),
        [box("#arabic-nav", WIDTH - 20 - 200, 10, 200, 40), box("main", WIDTH - 300 - 600, 80, 600, 500)],
    )

    assert mirror_defects(baseline, arabic) == []
    assert mirror_report(baseline, arabic) == []


def test_unmirrored_nav_is_a_single_named_rtl_offender() -> None:
    baseline = say(BASELINE, [box("#nav", 20, 10, 200, 40), box("main", 300, 80, 600, 500)])
    arabic = say(
        Context(locale=Locale.AR, varies=Axis.LOCALE),
        [box("#nav", 20, 10, 200, 40), box("main", WIDTH - 300 - 600, 80, 600, 500)],
    )

    report = mirror_report(baseline, arabic)

    assert mirror_defects(baseline, arabic) == [Defect.RTL_NOT_MIRRORED]
    assert len(report) == 1
    assert report[0].selector == "#nav"
    assert report[0].expected["x"] == WIDTH - 20 - 200
    assert report[0].actual["x"] == 20


def test_dark_mode_shift_is_reported_when_signature_differs() -> None:
    baseline = say(BASELINE, [box("#nav", 20, 10, 200, 40)], layout_signature="light")
    dark = say(
        Context(theme=Theme.DARK, varies=Axis.THEME),
        [box("#nav", 26, 10, 200, 40)],
        layout_signature="dark",
    )

    report = mirror_report(baseline, dark)

    assert mirror_defects(baseline, dark) == [Defect.THEME_LAYOUT_SHIFT]
    assert len(report) == 1
    assert report[0].selector == "#nav"
    assert report[0].expected["x"] == 20
    assert report[0].actual["x"] == 26


def test_translated_text_may_change_width_without_being_a_mirroring_failure() -> None:
    """Arabic renders the same label at a different width. Only position mirrors."""
    baseline = say(BASELINE, [box("#nav", 20, 10, 200, 40)])
    arabic = say(
        Context(locale=Locale.AR, varies=Axis.LOCALE),
        # Correctly mirrored — its right edge sits 20px from the right — but 60px wider.
        [box("#nav", WIDTH - 20 - 260, 10, 260, 44)],
    )

    assert mirror_report(baseline, arabic) == []
    assert mirror_defects(baseline, arabic) == []


def test_one_pixel_rounding_difference_is_within_tolerance() -> None:
    baseline = say(BASELINE, [box("#nav", 20, 10, 200, 40)])
    arabic = say(
        Context(locale=Locale.AR, varies=Axis.LOCALE),
        [box("#nav", WIDTH - 20 - 200 + 1, 10, 200, 40)],
    )

    assert mirror_report(baseline, arabic) == []
    assert mirror_defects(baseline, arabic) == []


def test_missing_geometry_is_not_evidence_of_a_defect() -> None:
    baseline = say(BASELINE, [])
    arabic = say(Context(locale=Locale.AR, varies=Axis.LOCALE), [box("#nav", 20, 10, 200, 40)])

    assert mirror_report(baseline, arabic) == []
    assert mirror_defects(baseline, arabic) == []
