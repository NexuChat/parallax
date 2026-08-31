"""Compose witness screenshots and surface only settled visual changes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from io import BytesIO

from PIL import Image, ImageDraw

from .contracts import Frame, Moment, MosaicFrame, Tile
from .types import derive_witnesses


_COLUMNS = 4
_ROWS = 2
_THUMBNAIL_SIZE = (32, 32)
_PLACEHOLDER = (36, 36, 36)
_NO_SIGNAL = (172, 172, 172)


class Compositor:
    """Maintain a fixed witness wall and emit its settled visual changes.

    ``contexts`` fixes the layout for the life of a compositor.  A frame's
    sequence number is compared only with frames from the same context, so a
    late CDP delivery cannot overwrite a newer image.
    """

    def __init__(
        self,
        contexts: Sequence[str] | None = None,
        *,
        settle_ms: int = 500,
        clock: Callable[[], int] | None = None,
        motion_threshold: float = 5.0,
        tile_size: tuple[int, int] | None = None,
    ) -> None:
        names = tuple(contexts) if contexts is not None else tuple(
            context.name for context in derive_witnesses()
        )
        if not names or len(names) > _COLUMNS * _ROWS:
            raise ValueError("contexts must contain between 1 and 7 names")
        if len(set(names)) != len(names):
            raise ValueError("context names must be unique")
        if settle_ms < 0:
            raise ValueError("settle_ms must not be negative")

        self._contexts = names
        self._settle_ms = settle_ms
        self._clock = clock or _wall_clock_ms
        self._motion_threshold = motion_threshold
        self._latest: dict[str, tuple[int, Image.Image]] = {}
        self._thumbnails: dict[str, Image.Image] = {}
        self._changed_at: dict[str, int] = {}
        # Left unset, the first frame to arrive decides the tile shape for
        # everyone — which is a race when the witnesses have different
        # viewports. Callers running the real seven should pass one.
        self._tile_size: tuple[int, int] | None = tile_size
        self._current_mosaic: MosaicFrame | None = None
        self._dirty = False
        self._action = ""

    @property
    def current_mosaic(self) -> MosaicFrame | None:
        """The latest wall, including labelled no-signal tiles for unseen contexts."""
        if self._tile_size is not None and (self._dirty or self._current_mosaic is None):
            self._current_mosaic = self._compose()
            self._dirty = False
        return self._current_mosaic

    def set_action(self, action: str) -> None:
        # The conductor calls this once per surface. Frames are observations of
        # that surface, so an old frame must never satisfy this surface's
        # paintedness gate for a witness that is now silent.
        self._latest.clear()
        self._thumbnails.clear()
        self._changed_at.clear()
        self._current_mosaic = None
        self._dirty = False
        self._action = action

    def submit(self, frame: Frame) -> None:
        """Accept one frame, ignoring stale deliveries from a known context."""
        if frame.context_name not in self._contexts:
            raise ValueError(f"unknown context: {frame.context_name}")
        previous = self._latest.get(frame.context_name)
        if previous is not None and frame.seq <= previous[0]:
            return

        image = _decode(frame.jpeg)
        if self._tile_size is None:
            self._tile_size = image.size
        image = _fit_to_width(image, self._tile_size)
        thumbnail = image.convert("L").resize(_THUMBNAIL_SIZE, Image.Resampling.BILINEAR)

        old_thumbnail = self._thumbnails.get(frame.context_name)
        if old_thumbnail is not None and _has_motion(
            old_thumbnail, thumbnail, self._motion_threshold
        ):
            self._changed_at[frame.context_name] = self._clock()

        self._latest[frame.context_name] = (frame.seq, image)
        self._thumbnails[frame.context_name] = thumbnail
        # Deliberately NOT composed here. Seven witnesses streaming at CDP rates
        # would otherwise re-encode the entire wall once per frame — measured at
        # a quarter-second of blocked event loop per submit — and starve the very
        # sessions being watched. The wall is only built when someone looks.
        self._dirty = True

    def tick(self, now_ms: int) -> Moment | None:
        """Return one moment once changed tiles have been quiet long enough."""
        settled = tuple(
            name
            for name in self._contexts
            if name in self._changed_at and now_ms - self._changed_at[name] >= self._settle_ms
        )
        # Hold, rather than drop, an early change: a late first screencast frame
        # is normal and its eventual wall is useful, whereas a partial wall would
        # make an absent witness look like a visual regression to specialists.
        if not settled or not self._all_contexts_painted:
            return None
        mosaic = self.current_mosaic
        if mosaic is None:
            return None

        settled_ms = min(now_ms - self._changed_at[name] for name in settled)
        for name in settled:
            del self._changed_at[name]
        return Moment(
            mosaic=mosaic,
            changed=settled,
            action=self._action,
            settled_ms=settled_ms,
        )

    @property
    def _all_contexts_painted(self) -> bool:
        return all(name in self._latest for name in self._contexts)

    def _compose(self) -> MosaicFrame:
        assert self._tile_size is not None
        width, height = self._tile_size
        wall = Image.new("RGB", (_COLUMNS * width, _ROWS * height), _PLACEHOLDER)
        tiles: list[Tile] = []
        for index, name in enumerate(self._contexts):
            x, y = (index % _COLUMNS) * width, (index // _COLUMNS) * height
            image = self._latest.get(name)
            if image is not None:
                wall.paste(image[1], (x, y))
            else:
                _draw_no_signal(wall, x, y, width, height)
            tiles.append(Tile(context_name=name, x=x, y=y, w=width, h=height))

        encoded = BytesIO()
        # The wall is looked at, not measured: q100 would multiply the cost of
        # every moment sent to a model for detail no one can see at tile scale.
        wall.save(encoded, format="JPEG", quality=85)
        return MosaicFrame(
            jpeg=encoded.getvalue(),
            tiles=tuple(tiles),
            seq=max((sequence for sequence, _ in self._latest.values()), default=0),
        )


def _decode(jpeg: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(jpeg)) as decoded:
            if decoded.format != "JPEG":
                raise ValueError("frame is not a JPEG")
            return decoded.convert("RGB").copy()
    except OSError as error:
        raise ValueError("frame is not a valid JPEG") from error


def _fit_to_width(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Fill the tile width without distortion, retaining the frame's top edge.

    Letterboxing made the portrait witnesses ineffective: on the published
    mosaic, owner-en-light-mobile (480x300) was 69% padding and
    owner-en-light-tablet was 53%, while every desktop witness was 1%. Scale to
    width and crop vertically from the top instead, because the page top is the
    shared comparison anchor and viewport differences emerge below it.

    Keep the conductor's existing landscape tile aspect for this wall: it keeps
    the fixed 4x2 grid compact and now contains image pixels rather than bars.
    A future conductor-level experiment could choose taller tiles, but must not
    alter the compositor's stable Tile boxes as part of this fitting change.
    """
    scale = size[0] / image.width
    scaled = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGB", size, _PLACEHOLDER)
    if scaled.height <= size[1]:
        canvas.paste(scaled, (0, (size[1] - scaled.height) // 2))
    else:
        canvas.paste(scaled.crop((0, 0, size[0], size[1])), (0, 0))
    return canvas


def _draw_no_signal(wall: Image.Image, x: int, y: int, width: int, height: int) -> None:
    """Make an unpainted slot explicit when a caller intentionally inspects it."""
    # Draw into a separate tile so the label can never overpaint its neighbour
    # on a small test or caller-supplied tile size.
    tile = Image.new("RGB", (width, height), _PLACEHOLDER)
    draw = ImageDraw.Draw(tile)
    inset = max(1, min(width, height) // 16)
    draw.rectangle((inset, inset, width - inset - 1, height - inset - 1), outline=_NO_SIGNAL)
    draw.text((width // 2, height // 2), "NO SIGNAL", fill=_NO_SIGNAL, anchor="mm")
    wall.paste(tile, (x, y))


def _has_motion(before: Image.Image, after: Image.Image, threshold: float) -> bool:
    difference = sum(abs(left - right) for left, right in zip(before.tobytes(), after.tobytes()))
    return difference / (before.width * before.height) >= threshold


def _wall_clock_ms() -> int:
    return int(datetime.now().timestamp() * 1000)
