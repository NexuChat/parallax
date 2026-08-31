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
_MOTION_HISTORY = 24
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
        if not names:
            raise ValueError("contexts must contain at least one name")
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
        # Raw screencast bytes, kept so the wall's movement can be replayed —
        # not decoded here, because 24 decoded walls of memory per witness is a
        # cost nobody pays until a clip is actually asked for.
        self._history: dict[str, list[tuple[int, bytes]]] = {}
        self._saw_motion = False

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
        self._history.clear()
        self._saw_motion = False
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
            self._saw_motion = True
        history = self._history.setdefault(frame.context_name, [])
        history.append((self._clock(), frame.jpeg))
        del history[:-_MOTION_HISTORY]

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

    def motion_clip(self, max_steps: int = 14) -> tuple[bytes, int, int] | None:
        """The wall's movement over this surface, as one animated WebP.

        The settled stills are the evidence; this is the passage of time between
        them — the screencast every witness already records and, until now,
        threw away once the settle gate had used it. Composed once, at the end
        of the surface, from the same raw frames: no re-encode of anything
        published, and inter-frame compression keeps it lighter than any
        sequence of JPEGs could be.

        Returns (webp bytes, steps, duration ms), or None when nothing moved —
        a static page must not ship a film of itself standing still.
        """
        if not self._saw_motion or self._tile_size is None or not self._history:
            return None
        if set(self._history) != set(self._contexts):
            # A context that never delivered a frame would be a NO SIGNAL tile
            # in every animation frame — the harness's placeholder shipped as
            # if it were the application's behaviour.
            return None
        stamps = sorted({ts for frames in self._history.values() for ts, _ in frames})
        # The film starts when the LAST witness has painted, not when the first
        # one did. Anything earlier bakes NO SIGNAL boxes and half-loaded white
        # pages into the clip's opening frames, and the console then loops that
        # broken-looking second forever in place of the settled still.
        painted_at = max(frames[0][0] for frames in self._history.values())
        stamps = [ts for ts in stamps if ts >= painted_at]
        if len(stamps) < 2 or stamps[-1] - stamps[0] < 120:
            return None
        first, last = stamps[0], stamps[-1]
        steps = min(max_steps, len(stamps))
        times = [first + (last - first) * index // (steps - 1) for index in range(steps)]

        decoded: dict[int, Image.Image] = {}

        def tile_at(name: str, when: int) -> Image.Image | None:
            newest = None
            for ts, jpeg in self._history.get(name, ()):
                if ts <= when:
                    newest = jpeg
                else:
                    break
            if newest is None:
                return None
            key = id(newest)
            if key not in decoded:
                decoded[key] = _fit_to_width(_decode(newest), self._tile_size)
            return decoded[key]

        walls: list[Image.Image] = []
        previous_thumb: Image.Image | None = None
        for when in times:
            wall = self._paint_wall({name: tile_at(name, when) for name in self._contexts})
            thumb = wall.convert("L").resize(_THUMBNAIL_SIZE, Image.Resampling.BILINEAR)
            # Consecutive identical walls carry no motion and only add weight.
            if previous_thumb is not None and not _has_motion(previous_thumb, thumb, 0.6):
                continue
            walls.append(wall)
            previous_thumb = thumb
        if len(walls) < 3:
            return None

        duration = max(80, min(400, (last - first) // len(walls)))
        encoded = BytesIO()
        walls[0].save(
            encoded, format="WEBP", save_all=True, append_images=walls[1:],
            duration=duration, loop=0, quality=80, method=3,
        )
        return encoded.getvalue(), len(walls), duration * len(walls)

    @property
    def _all_contexts_painted(self) -> bool:
        return all(name in self._latest for name in self._contexts)

    def _paint_wall(self, images: dict[str, Image.Image | None]) -> Image.Image:
        assert self._tile_size is not None
        width, height = self._tile_size
        # The wall grows rows to fit however many witnesses were declared; the
        # default seven still compose to the same 4x2 sheet they always did.
        rows = max(_ROWS, -(-len(self._contexts) // _COLUMNS))
        wall = Image.new("RGB", (_COLUMNS * width, rows * height), _PLACEHOLDER)
        for index, name in enumerate(self._contexts):
            x, y = (index % _COLUMNS) * width, (index // _COLUMNS) * height
            image = images.get(name)
            if image is not None:
                wall.paste(image, (x, y))
            else:
                _draw_no_signal(wall, x, y, width, height)
        return wall

    def _compose(self) -> MosaicFrame:
        assert self._tile_size is not None
        width, height = self._tile_size
        wall = self._paint_wall({
            name: (entry[1] if entry is not None else None)
            for name, entry in ((name, self._latest.get(name)) for name in self._contexts)
        })
        tiles = [
            Tile(context_name=name,
                 x=(index % _COLUMNS) * width, y=(index // _COLUMNS) * height,
                 w=width, h=height)
            for index, name in enumerate(self._contexts)
        ]

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
