"""The deterministic privilege lens."""

from __future__ import annotations

from collections.abc import Sequence

from ..contracts import Moment
from ..differ import compare
from ..types import Axis, Finding, FindingKind, Testimony


class AccessSpecialist:
    """An explicit compatibility lens for consumers that request privilege findings alone."""

    name = "access"

    def judge(
        self, moments: Sequence[Moment], testimonies: Sequence[Testimony]
    ) -> list[Finding]:
        del moments
        return [
            finding
            for finding in compare(testimonies)
            if finding.axis is Axis.PRIVILEGE
            and finding.kind in (FindingKind.ESCALATION, FindingKind.POLICY_INVERSION)
        ]
