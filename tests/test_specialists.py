from __future__ import annotations

from datetime import datetime, timedelta, timezone

from parallax.contracts import Moment, MosaicFrame, Specialist, Tile
from parallax.specialists import AccessSpecialist, LayoutI18nSpecialist, RealtimeSpecialist
from parallax.types import (
    BASELINE,
    Axis,
    Context,
    FindingKind,
    Locale,
    Outcome,
    Privilege,
    Severity,
    Surface,
    SurfaceKind,
    Testimony,
)


SURFACE = Surface(SurfaceKind.ROUTE, "/admin")
NOW = datetime(2026, 8, 29, tzinfo=timezone.utc)


def context(*, name: str, axis: Axis = Axis.BASELINE) -> Context:
    if axis is Axis.PRIVILEGE:
        return Context(privilege=Privilege.MEMBER, varies=axis)
    if axis is Axis.LOCALE:
        return Context(locale=Locale.AR, varies=axis)
    return BASELINE


def say(ctx: Context, outcome: Outcome = Outcome.REACHED) -> Testimony:
    return Testimony(surface=SURFACE, context=ctx, outcome=outcome)


def moment(
    *,
    changed: tuple[str, ...],
    action: str = "",
    at: datetime = NOW,
    contexts: tuple[str, ...] = ("owner-en-light-desktop", "owner-ar-light-desktop"),
) -> Moment:
    return Moment(
        mosaic=MosaicFrame(
            jpeg=b"mosaic-jpeg",
            tiles=tuple(Tile(name, index * 10, 0, 10, 10) for index, name in enumerate(contexts)),
            seq=1,
            composed_at=at,
        ),
        changed=changed,
        action=action,
        surface=SURFACE,
    )


class FakeModels:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response: object) -> None:
        self.models = FakeModels(response)


class TextResponse:
    def __init__(self, text: str) -> None:
        self.text = text


def test_every_specialist_satisfies_the_protocol() -> None:
    fake = FakeClient(TextResponse('{"findings": []}'))
    assert isinstance(AccessSpecialist(), Specialist)
    assert isinstance(LayoutI18nSpecialist(client=fake), Specialist)
    assert isinstance(RealtimeSpecialist(), Specialist)


def test_access_delegates_to_differ_and_keeps_only_privilege_findings() -> None:
    member = Context(privilege=Privilege.MEMBER, varies=Axis.PRIVILEGE)
    mobile = Context(viewport=BASELINE.viewport, varies=Axis.VIEWPORT)
    findings = AccessSpecialist().judge(
        [],
        [
            say(BASELINE),
            say(member),
            say(mobile, Outcome.BLOCKED),
        ],
    )
    assert [finding.kind for finding in findings] == [FindingKind.ESCALATION]
    assert all(finding.axis is Axis.PRIVILEGE for finding in findings)


def test_layout_without_a_client_returns_nothing(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert LayoutI18nSpecialist().judge([moment(changed=("owner-en-light-desktop",))], []) == []


def test_layout_sends_the_mosaic_and_parses_a_canned_verdict() -> None:
    arabic = Context(locale=Locale.AR, varies=Axis.LOCALE)
    fake = FakeClient(
        TextResponse(
            '{"findings": [{"context": "owner-ar-light-desktop", '
            '"kind": "render", "summary": "Arabic controls are clipped"}]}'
        )
    )
    specialist = LayoutI18nSpecialist(client=fake)
    findings = specialist.judge(
        [moment(changed=("owner-ar-light-desktop",))],
        [say(BASELINE), say(arabic)],
    )
    assert len(findings) == 1
    assert findings[0].kind is FindingKind.RENDER_DEFECT
    assert findings[0].axis is Axis.LOCALE
    assert "Arabic controls" in findings[0].summary
    call = fake.models.calls[0]
    assert call["model"] == "gemini-3.5-flash"
    prompt, image = call["contents"]
    assert "owner-ar-light-desktop" in prompt
    assert image["inline_data"]["data"] == b"mosaic-jpeg"


def test_layout_malformed_response_is_ignored() -> None:
    fake = FakeClient(TextResponse("not JSON"))
    assert LayoutI18nSpecialist(client=fake).judge([moment(changed=("owner-en-light-desktop",))], []) == []


def test_layout_caps_model_calls_and_skips_unchanged_moments() -> None:
    fake = FakeClient(TextResponse('{"findings": []}'))
    specialist = LayoutI18nSpecialist(client=fake, max_moments=1)
    specialist.judge(
        [
            moment(changed=()),
            moment(changed=("owner-en-light-desktop",)),
            moment(changed=("owner-ar-light-desktop",)),
        ],
        [],
    )
    assert len(fake.models.calls) == 1


def test_realtime_flags_an_action_that_never_reaches_a_witness() -> None:
    actor = "owner-en-light-desktop"
    silent = "owner-ar-light-desktop"
    findings = RealtimeSpecialist(deadline_ms=3_000).judge(
        [moment(changed=(actor,), action="create invoice")],
        [say(BASELINE), say(Context(locale=Locale.AR, varies=Axis.LOCALE))],
    )
    assert len(findings) == 1
    assert findings[0].kind is FindingKind.PROPAGATION_FAILURE
    assert findings[0].axis is Axis.RELATIONAL
    assert findings[0].severity is Severity.HIGH
    assert actor in findings[0].summary and silent in findings[0].summary


def test_realtime_stays_silent_when_the_effect_arrives_before_deadline() -> None:
    actor = "owner-en-light-desktop"
    witness = "owner-ar-light-desktop"
    findings = RealtimeSpecialist(deadline_ms=3_000).judge(
        [
            moment(changed=(actor,), action="create invoice"),
            moment(changed=(witness,), at=NOW + timedelta(milliseconds=2_999)),
        ],
        [],
    )
    assert findings == []
