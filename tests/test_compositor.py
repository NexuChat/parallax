from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from parallax.compositor import Compositor
from parallax.contracts import Frame


CONTEXTS = tuple(f"witness-{index}" for index in range(7))


def jpeg(color: tuple[int, int, int], size: tuple[int, int] = (12, 8)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG", quality=100, subsampling=0)
    return buffer.getvalue()


def pixel(mosaic: bytes, x: int, y: int) -> tuple[int, int, int]:
    with Image.open(BytesIO(mosaic)) as image:
        return image.convert("RGB").getpixel((x, y))


def is_color(actual: tuple[int, int, int], expected: tuple[int, int, int]) -> bool:
    """The wall is saved lossily on purpose; assert the colour, not the bytes."""
    return all(abs(left - right) <= 10 for left, right in zip(actual, expected))


def test_seven_frames_compose_into_a_stable_four_by_two_grid() -> None:
    compositor = Compositor(CONTEXTS)
    colors = [(index * 30, 20, 40) for index in range(7)]

    for index, color in enumerate(colors):
        compositor.submit(Frame(CONTEXTS[index], jpeg(color), seq=index))

    mosaic = compositor.current_mosaic
    assert mosaic is not None
    assert [(tile.context_name, tile.x, tile.y, tile.w, tile.h) for tile in mosaic.tiles] == [
        (name, (index % 4) * 12, (index // 4) * 8, 12, 8)
        for index, name in enumerate(CONTEXTS)
    ]
    with Image.open(BytesIO(mosaic.jpeg)) as image:
        assert image.size == (48, 16)
    for index, color in enumerate(colors):
        x = (index % 4) * 12 + 6
        y = (index // 4) * 8 + 4
        assert is_color(pixel(mosaic.jpeg, x, y), color)


def test_later_frame_replaces_the_contexts_earlier_frame_and_stale_delivery_is_ignored() -> None:
    compositor = Compositor(CONTEXTS)
    compositor.submit(Frame(CONTEXTS[0], jpeg((240, 0, 0)), seq=1))
    compositor.submit(Frame(CONTEXTS[0], jpeg((0, 0, 240)), seq=2))
    compositor.submit(Frame(CONTEXTS[0], jpeg((0, 240, 0)), seq=1))

    mosaic = compositor.current_mosaic
    assert mosaic is not None
    assert is_color(pixel(mosaic.jpeg, 6, 4), (0, 0, 240))


def test_a_narrow_viewport_is_letterboxed_rather_than_stretched() -> None:
    """The mobile witness is 360 wide next to a 1440 desktop. It must not distort."""
    compositor = Compositor(CONTEXTS, tile_size=(40, 20))
    compositor.submit(Frame(CONTEXTS[0], jpeg((240, 0, 0), size=(10, 20)), seq=1))

    mosaic = compositor.current_mosaic
    assert mosaic is not None
    assert is_color(pixel(mosaic.jpeg, 20, 10), (240, 0, 0))   # the frame, centred
    assert is_color(pixel(mosaic.jpeg, 2, 10), (36, 36, 36))   # padding, not stretched pixels


def test_unchanged_tile_emits_no_moment() -> None:
    now = 0
    compositor = Compositor(CONTEXTS, clock=lambda: now)
    frame = jpeg((20, 30, 40))
    compositor.submit(Frame(CONTEXTS[0], frame, seq=1))
    now = 10
    compositor.submit(Frame(CONTEXTS[0], frame, seq=2))

    assert compositor.tick(1_000) is None


def test_changed_tile_emits_one_moment_after_settling() -> None:
    now = 0
    compositor = Compositor(CONTEXTS, clock=lambda: now, settle_ms=500)
    compositor.set_action("open billing")
    compositor.submit(Frame(CONTEXTS[0], jpeg((10, 10, 10)), seq=1))
    now = 1
    compositor.submit(Frame(CONTEXTS[0], jpeg((220, 220, 220)), seq=2))

    assert compositor.tick(500) is None
    moment = compositor.tick(501)
    assert moment is not None
    assert moment.changed == (CONTEXTS[0],)
    assert moment.action == "open billing"
    assert moment.settled_ms == 500
    assert compositor.tick(1_000) is None


def test_still_changing_inside_the_settle_window_emits_nothing_yet() -> None:
    now = 0
    compositor = Compositor(CONTEXTS, clock=lambda: now, settle_ms=500)
    compositor.submit(Frame(CONTEXTS[0], jpeg((10, 10, 10)), seq=1))
    now = 1
    compositor.submit(Frame(CONTEXTS[0], jpeg((120, 120, 120)), seq=2))
    now = 400
    compositor.submit(Frame(CONTEXTS[0], jpeg((230, 230, 230)), seq=3))

    assert compositor.tick(800) is None
    moment = compositor.tick(900)
    assert moment is not None
    assert moment.changed == (CONTEXTS[0],)
    assert moment.settled_ms == 500


def test_unknown_context_is_rejected_without_changing_the_grid() -> None:
    compositor = Compositor(CONTEXTS)

    with pytest.raises(ValueError, match="unknown context"):
        compositor.submit(Frame("intruder", jpeg((1, 2, 3)), seq=1))
