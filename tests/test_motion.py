"""The movement between the moments, retained instead of thrown away.

Every witness records a CDP screencast; until now the compositor used it only
to decide when a frame had settled and discarded it. The motion clip is that
same footage composed once per surface into an animated WebP — the stills stay
the judged evidence, the clip is the passage of time between them.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from parallax.compositor import Compositor
from parallax.conductor import Conductor, _clean_managed_mosaics, _MANAGED_MOSAIC
from parallax.contracts import Frame
from parallax.types import Surface, SurfaceKind


CONTEXTS = ("left", "right")


def jpeg(color: tuple[int, int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (40, 20), color).save(buffer, format="JPEG")
    return buffer.getvalue()


def compositor(clock: list[int]) -> Compositor:
    return Compositor(CONTEXTS, settle_ms=0, clock=lambda: clock[0], tile_size=(40, 20))


def feed(comp: Compositor, name: str, color: tuple[int, int, int], seq: int) -> None:
    comp.submit(Frame(context_name=name, jpeg=jpeg(color), seq=seq))


def test_a_moving_surface_yields_an_animated_clip() -> None:
    clock = [0]
    comp = compositor(clock)
    for step, color in enumerate([(250, 250, 250), (10, 10, 10), (250, 20, 20), (20, 250, 20)]):
        clock[0] = step * 200
        feed(comp, "left", color, step + 1)
        feed(comp, "right", color, step + 1)

    clip = comp.motion_clip()

    assert clip is not None
    data, frames, duration_ms = clip
    with Image.open(BytesIO(data)) as animation:
        assert animation.format == "WEBP"
        assert getattr(animation, "n_frames", 1) >= 3
        # The clip is the same wall geometry as the stills — the fixed 4x2
        # grid — so the console's tile overlay applies to it unchanged.
        assert animation.size == (4 * 40, 2 * 20)
    assert frames >= 3
    assert duration_ms > 0


def test_a_static_surface_ships_no_film_of_itself_standing_still() -> None:
    clock = [0]
    comp = compositor(clock)
    for step in range(4):
        clock[0] = step * 200
        feed(comp, "left", (128, 128, 128), step + 1)
        feed(comp, "right", (128, 128, 128), step + 1)

    assert comp.motion_clip() is None


def test_the_next_surface_does_not_inherit_this_ones_movement() -> None:
    clock = [0]
    comp = compositor(clock)
    for step, color in enumerate([(250, 250, 250), (10, 10, 10), (250, 20, 20)]):
        clock[0] = step * 200
        feed(comp, "left", color, step + 1)
        feed(comp, "right", color, step + 1)
    comp.set_action("the next surface")

    assert comp.motion_clip() is None


def test_the_writer_publishes_the_clip_and_the_feed_names_it(tmp_path: Path) -> None:
    conductor = Conductor("https://app.example/", tmp_path, browser=None)
    feed_path = tmp_path / "feed.jsonl"
    feed_path.write_text("", encoding="utf-8")
    surface = Surface(SurfaceKind.ROUTE, "https://app.example/threads")

    conductor._write_motion(feed_path, surface, (b"RIFFwebp-bytes", 5, 1200))

    clip_path = tmp_path / "mosaics" / f"{surface.id}-motion.webp"
    assert clip_path.read_bytes() == b"RIFFwebp-bytes"
    [line] = [json.loads(row) for row in feed_path.read_text().splitlines() if row.strip()]
    assert line["kind"] == "motion"
    assert line["payload"] == {
        "surface_id": surface.id,
        "image": f"mosaics/{surface.id}-motion.webp",
        "frames": 5,
        "duration_ms": 1200,
    }
    # A rerun must replace it, exactly like the stills it sits beside.
    assert _MANAGED_MOSAIC.fullmatch(clip_path.name)


def test_no_clip_writes_nothing(tmp_path: Path) -> None:
    conductor = Conductor("https://app.example/", tmp_path, browser=None)
    feed_path = tmp_path / "feed.jsonl"
    feed_path.write_text("", encoding="utf-8")

    conductor._write_motion(feed_path, Surface(SurfaceKind.ROUTE, "https://app.example/"), None)

    assert feed_path.read_text() == ""
    assert not (tmp_path / "mosaics").exists()


def test_reruns_clean_stale_motion_clips(tmp_path: Path) -> None:
    mosaics = tmp_path / "mosaics"
    mosaics.mkdir()
    stale = mosaics / f"{'a' * 16}-motion.webp"
    stale.write_bytes(b"old")
    keep = mosaics / "hand-made.webp"
    keep.write_bytes(b"not ours")

    _clean_managed_mosaics(tmp_path)

    assert not stale.exists()
    assert keep.exists()


def test_the_clip_never_opens_before_the_last_witness_has_painted() -> None:
    """A late joiner must not appear as a NO SIGNAL box in the film's start."""
    clock = [0]
    comp = compositor(clock)
    # left paints and moves early; right delivers its first frame late
    for step, color in enumerate([(250, 250, 250), (10, 10, 10), (250, 20, 20)]):
        clock[0] = step * 200
        feed(comp, "left", color, step + 1)
    clock[0] = 500
    feed(comp, "right", (250, 250, 250), 1)
    clock[0] = 700
    feed(comp, "left", (20, 250, 20), 4)
    feed(comp, "right", (10, 10, 10), 2)
    clock[0] = 900
    feed(comp, "left", (250, 250, 10), 5)
    feed(comp, "right", (250, 20, 250), 3)

    clip = comp.motion_clip()

    assert clip is not None
    data, _, _ = clip
    from parallax.compositor import _PLACEHOLDER
    with Image.open(BytesIO(data)) as animation:
        animation.seek(0)
        frame = animation.convert("RGB")
        # centre of the second tile (right context) in the fixed 4x2 grid
        assert frame.getpixel((60, 10)) != _PLACEHOLDER


def test_a_witness_that_never_painted_means_no_clip_at_all() -> None:
    clock = [0]
    comp = compositor(clock)
    for step, color in enumerate([(250, 250, 250), (10, 10, 10), (250, 20, 20)]):
        clock[0] = step * 200
        feed(comp, "left", color, step + 1)

    assert comp.motion_clip() is None
