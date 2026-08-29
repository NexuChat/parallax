from __future__ import annotations

import json

from parallax.contracts import FeedEvent


def test_older_finding_payload_without_mosaic_reference_still_has_the_required_shape() -> None:
    """The optional evidence-frame field does not invalidate an older feed line."""
    older_payload = {
        "id": "render-baseline-abc",
        "kind": "render",
        "severity": "low",
        "axis": "baseline",
        "surface": "/shop?category=paper",
        "surface_id": "abc",
        "summary": "heading clips",
        "evidence": "owner-en-light-desktop=partial",
        "witnesses": ["owner-en-light-desktop"],
    }

    event = json.loads(json.dumps(FeedEvent("finding", older_payload).to_json()))

    assert event["payload"] == older_payload
    assert "mosaic" not in event["payload"]
