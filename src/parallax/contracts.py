"""The seams between stages.

Witnesses produce frames and testimonies. The compositor turns seven frame
streams into one mosaic and decides which instants deserve a model call. The
specialists judge those instants. The console renders them. Each of those is
built and tested on its own, so the shapes they hand each other live here
instead of inside whichever stage happened to define them first.

Nothing here does work. If a type in this file grows a method that computes
something, it belongs in the stage that owns the computation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from .types import Finding, Surface, Testimony


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Witness → compositor
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Frame:
    """One screencast frame from one witness.

    Bytes stay bytes until the mosaic: encoding once, at capture, and decoding
    once, at composition, is the whole reason a live wall of seven sessions is
    affordable at all.
    """

    context_name: str
    jpeg: bytes
    seq: int
    captured_at: datetime = field(default_factory=_now)


# --------------------------------------------------------------------------
# Compositor → specialists and console
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Tile:
    """Where one witness sits in the mosaic, so a finding can point at a pixel."""

    context_name: str
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class MosaicFrame:
    """Every witness in one image.

    The point is not compression. It is that a comparison across contexts
    becomes a glance instead of a join: six tiles that agree and one that does
    not is a shape the eye — and the model — resolves immediately.
    """

    jpeg: bytes
    tiles: tuple[Tile, ...]
    seq: int
    composed_at: datetime = field(default_factory=_now)

    def tile(self, context_name: str) -> Tile | None:
        return next((t for t in self.tiles if t.context_name == context_name), None)


@dataclass(frozen=True)
class Moment:
    """A mosaic worth looking at: something moved, and then it stopped moving.

    Motion is not evidence — a half-painted frame is noise. The instant a tile
    changes and then settles is the only one a specialist should pay for.
    """

    mosaic: MosaicFrame
    changed: tuple[str, ...]        # context names whose tile moved
    action: str                     # what the run was doing when it moved
    surface: Surface | None = None  # the surface under test, when one is
    settled_ms: int = 0             # how long the tiles held still


# --------------------------------------------------------------------------
# Specialists
# --------------------------------------------------------------------------

@runtime_checkable
class Specialist(Protocol):
    """One lens over the shared stream.

    Specialists never drive a browser and never talk to each other. They read
    the same moments and testimonies every other specialist reads and return
    findings in their own domain — which is what makes adding a seventh lens
    cost a replay instead of another seven browser sessions.
    """

    name: str

    def judge(
        self,
        moments: Sequence[Moment],
        testimonies: Sequence[Testimony],
    ) -> list[Finding]: ...


# --------------------------------------------------------------------------
# → console
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class FeedEvent:
    """One line on the wire to the console. JSON, never bytes."""

    kind: str            # "mosaic" | "finding" | "status"
    payload: dict[str, Any]
    at: datetime = field(default_factory=_now)

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "at": self.at.isoformat(), "payload": self.payload}


def finding_payload(finding: Finding) -> dict[str, Any]:
    """A finding, flattened for transport, evidence included.

    The evidence line travels with the finding on purpose: a claim the console
    shows without the testimonies behind it is a claim nobody can check.
    """

    return {
        "id": finding.id,
        "kind": finding.kind.value,
        "severity": finding.severity.value,
        "axis": finding.axis.value,
        "surface": finding.surface.describe(),
        "surface_id": finding.surface.id,
        "summary": finding.summary,
        "evidence": finding.evidence_line(),
        "witnesses": [t.context.name for t in finding.testimonies],
    }


def mosaic_payload(mosaic: MosaicFrame, image_url: str) -> dict[str, Any]:
    """A mosaic, referenced rather than inlined — the console fetches the image."""

    return {
        "seq": mosaic.seq,
        "image": image_url,
        "tiles": [
            {"context": t.context_name, "x": t.x, "y": t.y, "w": t.w, "h": t.h}
            for t in mosaic.tiles
        ],
    }
