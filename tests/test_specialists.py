from __future__ import annotations

from datetime import datetime, timedelta, timezone

from parallax.contracts import Moment, MosaicFrame, Specialist, Tile
from parallax.__main__ import _specialists
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
    Testimony as WitnessTestimony,
)


SURFACE = Surface(SurfaceKind.ROUTE, "/admin")
NOW = datetime(2026, 8, 29, tzinfo=timezone.utc)


def context(*, name: str, axis: Axis = Axis.BASELINE) -> Context:
    if axis is Axis.PRIVILEGE:
        return Context(privilege=Privilege.MEMBER, varies=axis)
    if axis is Axis.LOCALE:
        return Context(locale=Locale.AR, varies=axis)
    return BASELINE


def say(ctx: Context, outcome: Outcome = Outcome.REACHED) -> WitnessTestimony:
    return WitnessTestimony(surface=SURFACE, context=ctx, outcome=outcome)


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
    anonymous = Context(privilege=Privilege.ANON, varies=Axis.PRIVILEGE)
    findings = AccessSpecialist().judge(
        [],
        [
            say(BASELINE),
            say(member, Outcome.BLOCKED),
            say(anonymous),
        ],
    )
    assert [finding.kind for finding in findings] == [FindingKind.ESCALATION]
    assert all(finding.axis is Axis.PRIVILEGE for finding in findings)


def test_access_is_explicitly_opt_in_not_a_default_cli_lens() -> None:
    assert not any(isinstance(specialist, AccessSpecialist) for specialist in _specialists(no_vision=True))


def test_layout_without_a_client_returns_nothing(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    specialist = LayoutI18nSpecialist()
    assert specialist.route == "disabled"
    assert specialist.judge([moment(changed=("owner-en-light-desktop",))], []) == []


def test_layout_injected_client_wins_over_every_environment_route(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "configured-project")
    monkeypatch.setenv("GEMINI_API_KEY", "studio-key")
    fake = FakeClient(TextResponse('{"findings": []}'))
    specialist = LayoutI18nSpecialist(
        client=fake,
        token_fetcher=lambda: (_ for _ in ()).throw(AssertionError("should not fetch a token")),
        client_factory=lambda **_: (_ for _ in ()).throw(AssertionError("should not build a client")),
    )
    specialist.judge([moment(changed=("owner-en-light-desktop",))], [])
    assert specialist.route == "injected"
    assert len(fake.models.calls) == 1


def test_layout_selects_vertex_with_configured_project_and_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "configured-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")
    monkeypatch.setenv("GEMINI_API_KEY", "studio-key")
    captured: dict[str, object] = {}
    fake = FakeClient(TextResponse('{"findings": []}'))

    def factory(**kwargs: object) -> FakeClient:
        captured.update(kwargs)
        return fake

    specialist = LayoutI18nSpecialist(
        token_fetcher=lambda: "test-bearer-token", client_factory=factory
    )
    specialist.judge([moment(changed=("owner-en-light-desktop",))], [])
    assert specialist.route == "vertex"
    assert captured["vertexai"] is True
    assert captured["project"] == "configured-project"
    assert captured["location"] == "global"
    assert captured["http_options"] == {"api_version": "v1"}
    assert captured["credentials"].token == "test-bearer-token"
    assert fake.models.calls[0]["model"] == "gemini-3.6-flash"


def test_layout_selects_ai_studio_when_vertex_is_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "studio-key")
    captured: dict[str, object] = {}
    fake = FakeClient(TextResponse('{"findings": []}'))

    def factory(**kwargs: object) -> FakeClient:
        captured.update(kwargs)
        return fake

    specialist = LayoutI18nSpecialist(client_factory=factory)
    specialist.judge([moment(changed=("owner-en-light-desktop",))], [])
    assert specialist.route == "ai_studio"
    assert captured == {"api_key": "studio-key"}
    assert len(fake.models.calls) == 1


def test_layout_refreshes_vertex_token_once_after_an_auth_failure(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "configured-project")
    tokens = iter(["first-token", "second-token"])
    fetches: list[str] = []
    first = FakeClient(TextResponse('{"findings": []}'))
    second = FakeClient(TextResponse('{"findings": []}'))

    def unauthorized(**_: object) -> object:
        raise RuntimeError("401 UNAUTHENTICATED")

    first.models.generate_content = unauthorized  # type: ignore[method-assign]
    clients = iter([first, second])
    specialist = LayoutI18nSpecialist(
        token_fetcher=lambda: fetches.append("fetch") or next(tokens),
        client_factory=lambda **_: next(clients),
    )
    assert specialist.judge([moment(changed=("owner-en-light-desktop",))], []) == []
    assert fetches == ["fetch", "fetch"]
    assert len(second.models.calls) == 1


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
    assert call["model"] == "gemini-3.6-flash"
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
        [
            say(Context(varies=Axis.RELATIONAL)),
            say(Context(locale=Locale.AR, varies=Axis.RELATIONAL)),
        ],
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
        [
            say(Context(varies=Axis.RELATIONAL)),
            say(Context(locale=Locale.AR, varies=Axis.RELATIONAL)),
        ],
    )
    assert findings == []


def test_realtime_says_nothing_about_an_ordinary_sweep() -> None:
    """Every tile repaints as its page loads. That is not a failed propagation.

    Without this guard a three-surface run produced sixty-nine HIGH findings,
    one for every witness that did not happen to repaint after another did.
    """
    findings = RealtimeSpecialist(deadline_ms=3_000).judge(
        [moment(changed=("owner-en-light-desktop",), action="/settings")],
        [say(BASELINE), say(Context(locale=Locale.AR, varies=Axis.LOCALE))],
    )
    assert findings == []
