from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from parallax.compositor import Compositor
from parallax.contracts import Frame


CONTEXTS = tuple(f"witness-{index}" for index in range(7))


def jpeg(color: tuple[int, int, int], size: tuple[int, int] = (12, 8)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG", quality=100, subsampling=0)
    return buffer.getvalue()


def split_jpeg(
    top: tuple[int, int, int], bottom: tuple[int, int, int], size: tuple[int, int]
) -> bytes:
    """Make a frame whose top and bottom remain distinguishable after JPEG encoding."""
    image = Image.new("RGB", size, top)
    ImageDraw.Draw(image).rectangle((0, size[1] // 2, size[0], size[1]), fill=bottom)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=100, subsampling=0)
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
    for name in CONTEXTS[1:]:
        compositor.submit(Frame(name, jpeg((0, 0, 240)), seq=1))
    compositor.submit(Frame(CONTEXTS[0], jpeg((240, 0, 0)), seq=1))
    compositor.submit(Frame(CONTEXTS[0], jpeg((0, 0, 240)), seq=2))
    compositor.submit(Frame(CONTEXTS[0], jpeg((0, 240, 0)), seq=1))

    mosaic = compositor.current_mosaic
    assert mosaic is not None
    assert is_color(pixel(mosaic.jpeg, 6, 4), (0, 0, 240))


def test_submitting_frames_does_not_rebuild_the_wall_every_time(monkeypatch) -> None:
    """Seven witnesses streaming at CDP rates must not re-encode the wall per frame."""
    composed = 0
    original = Compositor._compose

    def counting(self):
        nonlocal composed
        composed += 1
        return original(self)

    monkeypatch.setattr(Compositor, "_compose", counting)
    compositor = Compositor(CONTEXTS)
    for index in range(20):
        compositor.submit(Frame(CONTEXTS[index % 7], jpeg((index * 10, 20, 40)), seq=index))

    assert composed == 0            # nothing built while frames were only arriving
    assert compositor.current_mosaic is not None
    assert composed == 1            # built once, when someone finally looked
    assert compositor.current_mosaic is not None
    assert composed == 1            # and cached until the next frame


def test_a_portrait_viewport_fills_the_tile_width_without_background_columns() -> None:
    """Portrait witnesses use every horizontal pixel of their comparison tile."""
    compositor = Compositor(CONTEXTS, tile_size=(40, 20))
    compositor.submit(Frame(CONTEXTS[0], jpeg((240, 0, 0), size=(10, 20)), seq=1))

    mosaic = compositor.current_mosaic
    assert mosaic is not None
    assert all(not is_color(pixel(mosaic.jpeg, x, 10), (36, 36, 36)) for x in range(40))
    assert is_color(pixel(mosaic.jpeg, 0, 10), (240, 0, 0))
    assert is_color(pixel(mosaic.jpeg, 20, 10), (240, 0, 0))
    assert is_color(pixel(mosaic.jpeg, 38, 10), (240, 0, 0))


def test_fit_to_width_crops_a_portrait_frame_from_its_top() -> None:
    compositor = Compositor(CONTEXTS, tile_size=(40, 20))
    compositor.submit(
        Frame(
            CONTEXTS[0],
            split_jpeg((240, 0, 0), (0, 0, 240), size=(10, 30)),
            seq=1,
        )
    )

    mosaic = compositor.current_mosaic
    assert mosaic is not None
    assert is_color(pixel(mosaic.jpeg, 20, 2), (240, 0, 0))
    assert is_color(pixel(mosaic.jpeg, 20, 18), (240, 0, 0))


def test_a_landscape_frame_is_scaled_to_width_and_cropped_from_the_top() -> None:
    compositor = Compositor(CONTEXTS, tile_size=(40, 20))
    compositor.submit(
        Frame(
            CONTEXTS[0],
            split_jpeg((240, 0, 0), (0, 240, 0), size=(60, 40)),
            seq=1,
        )
    )

    mosaic = compositor.current_mosaic
    assert mosaic is not None
    assert is_color(pixel(mosaic.jpeg, 0, 2), (240, 0, 0))
    assert is_color(pixel(mosaic.jpeg, 38, 18), (0, 240, 0))


def test_a_wide_short_frame_is_centred_on_the_tile_background() -> None:
    compositor = Compositor(CONTEXTS, tile_size=(40, 20))
    compositor.submit(Frame(CONTEXTS[0], jpeg((240, 0, 0), size=(100, 20)), seq=1))

    mosaic = compositor.current_mosaic
    assert mosaic is not None
    assert is_color(pixel(mosaic.jpeg, 20, 2), (36, 36, 36))
    assert is_color(pixel(mosaic.jpeg, 20, 10), (240, 0, 0))
    assert is_color(pixel(mosaic.jpeg, 20, 18), (36, 36, 36))


def test_fit_to_width_does_not_change_reported_tile_boxes() -> None:
    compositor = Compositor(("portrait", "landscape"), tile_size=(40, 20))
    compositor.submit(Frame("portrait", jpeg((240, 0, 0), size=(10, 30)), seq=1))
    compositor.submit(Frame("landscape", jpeg((0, 240, 0), size=(60, 40)), seq=1))

    mosaic = compositor.current_mosaic
    assert mosaic is not None
    assert [(tile.context_name, tile.x, tile.y, tile.w, tile.h) for tile in mosaic.tiles] == [
        ("portrait", 0, 0, 40, 20),
        ("landscape", 40, 0, 40, 20),
    ]


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
    for name in CONTEXTS[1:]:
        compositor.submit(Frame(name, jpeg((20, 20, 20)), seq=1))
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


def test_changed_tile_waits_for_every_context_to_paint_before_emitting() -> None:
    now = 0
    contexts = ("left", "right")
    compositor = Compositor(contexts, clock=lambda: now, settle_ms=500)
    compositor.submit(Frame("left", jpeg((10, 10, 10)), seq=1))
    now = 1
    compositor.submit(Frame("left", jpeg((220, 220, 220)), seq=2))

    assert compositor.tick(501) is None

    compositor.submit(Frame("right", jpeg((30, 30, 30)), seq=1))
    moment = compositor.tick(501)
    assert moment is not None
    assert moment.changed == ("left",)


def test_undecodable_later_frame_keeps_the_contexts_last_good_image() -> None:
    compositor = Compositor(CONTEXTS)
    for name in CONTEXTS[1:]:
        compositor.submit(Frame(name, jpeg((0, 0, 240)), seq=1))
    compositor.submit(Frame(CONTEXTS[0], jpeg((0, 0, 240)), seq=1))

    with pytest.raises(ValueError, match="valid JPEG"):
        compositor.submit(Frame(CONTEXTS[0], b"not a jpeg", seq=2))

    mosaic = compositor.current_mosaic
    assert mosaic is not None
    assert is_color(pixel(mosaic.jpeg, 6, 4), (0, 0, 240))


def test_only_never_painted_contexts_use_a_labelled_no_signal_tile() -> None:
    compositor = Compositor(("painted", "never"), tile_size=(120, 80))
    compositor.submit(Frame("painted", jpeg((0, 0, 240), size=(120, 80)), seq=1))

    mosaic = compositor.current_mosaic
    assert mosaic is not None
    assert is_color(pixel(mosaic.jpeg, 60, 40), (0, 0, 240))
    with Image.open(BytesIO(mosaic.jpeg)) as image:
        label_area = image.convert("RGB").crop((140, 20, 220, 60))
    assert any(not is_color(color, (36, 36, 36)) for color in label_area.get_flattened_data())


def test_still_changing_inside_the_settle_window_emits_nothing_yet() -> None:
    now = 0
    compositor = Compositor(CONTEXTS, clock=lambda: now, settle_ms=500)
    for name in CONTEXTS[1:]:
        compositor.submit(Frame(name, jpeg((20, 20, 20)), seq=1))
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
