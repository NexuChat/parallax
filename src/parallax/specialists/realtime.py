"""The deterministic relational propagation lens."""

from __future__ import annotations

from collections.abc import Sequence

from ..contracts import Moment
from ..types import Axis, Finding, FindingKind, Severity, Surface, Testimony


class RealtimeSpecialist:
    """Report witnesses that do not reflect an action before its deadline."""

    name = "realtime"

    def __init__(self, *, deadline_ms: int = 3_000) -> None:
        self._deadline_ms = max(0, deadline_ms)

    def judge(
        self, moments: Sequence[Moment], testimonies: Sequence[Testimony]
    ) -> list[Finding]:
        # Propagation is a claim about a DECLARED sender/receiver pair, and about
        # nothing else. On an ordinary sweep every tile repaints as its page
        # loads; reading that as "six witnesses failed to mirror an action"
        # turned three real surfaces into sixty-nine false alarms before this
        # guard existed. Witnesses only carry Axis.RELATIONAL when something
        # deliberately paired them.
        by_context = {
            testimony.context.name: testimony
            for testimony in testimonies
            if testimony.context.varies is Axis.RELATIONAL
        }
        if len(by_context) < 2:
            return []
        ordered = sorted(moments, key=lambda moment: moment.mosaic.composed_at)
        findings: list[Finding] = []
        for index, event in enumerate(ordered):
            if not event.action or not event.changed:
                continue
            witnesses = {tile.context_name for tile in event.mosaic.tiles} & set(by_context)
            deadline = event.mosaic.composed_at.timestamp() * 1000 + self._deadline_ms
            surface: Surface | None = event.surface or next(
                (testimony.surface for testimony in testimonies), None
            )
            if surface is None:
                continue
            later = ordered[index + 1 :]
            for actor in event.changed:
                if actor not in by_context:
                    continue
                for witness in sorted(witnesses - {actor}):
                    propagated = any(
                        witness in candidate.changed
                        and candidate.mosaic.composed_at.timestamp() * 1000 <= deadline
                        for candidate in later
                    )
                    if propagated:
                        continue
                    evidence = [
                        testimony
                        for name in (actor, witness)
                        if (testimony := by_context.get(name)) is not None
                    ]
                    findings.append(
                        Finding(
                            kind=FindingKind.PROPAGATION_FAILURE,
                            severity=Severity.HIGH,
                            surface=surface,
                            axis=Axis.RELATIONAL,
                            summary=(
                                f"{actor} performed {event.action!r}, but {witness} did not "
                                f"show the effect within {self._deadline_ms}ms"
                            ),
                            testimonies=evidence,
                        )
                    )
        return findings
