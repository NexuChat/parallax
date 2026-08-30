from __future__ import annotations

from collections.abc import Sequence

from parallax.differ import compare
from parallax.semantics import (
    CloudTranslation,
    GoogleCloudTransport,
    MAX_SEMANTIC_COMPARISONS_PER_RUN,
    SemanticComparator,
    SemanticPair,
    SemanticPairKind,
    VertexEmbeddings,
)
from parallax.types import (
    BASELINE,
    Axis,
    Context,
    Defect,
    FindingKind,
    Locale,
    Outcome,
    Surface,
    SurfaceKind,
    Testimony as WitnessTestimony,
    Theme,
)


SURFACE = Surface(SurfaceKind.ROUTE, "/settings")


class FakeEmbeddings:
    def __init__(self, vectors: dict[str, list[float]], error: Exception | None = None) -> None:
        self.vectors = vectors
        self.error = error
        self.calls: list[list[str]] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.error is not None:
            raise self.error
        return [self.vectors[text] for text in texts]


class FakeTranslation:
    def __init__(self, translations: dict[tuple[str, str, str], str], error: Exception | None = None) -> None:
        self.translations = translations
        self.error = error
        self.calls: list[tuple[list[str], str, str]] = []

    def translate(self, texts: Sequence[str], *, source: str, target: str) -> list[str]:
        self.calls.append((list(texts), source, target))
        if self.error is not None:
            raise self.error
        return [self.translations[(text, source, target)] for text in texts]


class FakeCredentials:
    valid = True
    token = "adc-token"


def test_vertex_embedding_request_uses_adc_bearer_and_the_verified_route() -> None:
    captured: dict[str, object] = {}

    def post(url: str, headers: dict[str, str], payload: dict[str, object]) -> dict[str, object]:
        captured.update(url=url, headers=headers, payload=payload)
        return {"predictions": [{"embeddings": {"values": [1, 0]}}]}

    transport = GoogleCloudTransport("rasikh-fleet-2026", post=post)
    transport._credentials = FakeCredentials()  # type: ignore[attr-defined]

    assert VertexEmbeddings(transport).embed(["hello"]) == [[1.0, 0.0]]
    assert captured["url"] == (
        "https://us-central1-aiplatform.googleapis.com/v1/projects/rasikh-fleet-2026/"
        "locations/us-central1/publishers/google/models/text-embedding-005:predict"
    )
    assert captured["payload"] == {"instances": [{"content": "hello"}]}
    assert captured["headers"] == {
        "Authorization": "Bearer adc-token",
        "Content-Type": "application/json; charset=utf-8",
        "x-goog-user-project": "rasikh-fleet-2026",
    }


def test_translation_request_batches_strings_and_uses_the_quota_project() -> None:
    captured: dict[str, object] = {}

    def post(url: str, headers: dict[str, str], payload: dict[str, object]) -> dict[str, object]:
        captured.update(url=url, headers=headers, payload=payload)
        return {"data": {"translations": [{"translatedText": "تسجيل الدخول"}]}}

    transport = GoogleCloudTransport("rasikh-fleet-2026", post=post)
    transport._credentials = FakeCredentials()  # type: ignore[attr-defined]

    assert CloudTranslation(transport).translate(["Sign in"], source="en", target="ar") == ["تسجيل الدخول"]
    assert captured["url"] == "https://translation.googleapis.com/language/translate/v2"
    assert captured["payload"] == {
        "q": ["Sign in"], "source": "en", "target": "ar", "format": "text"
    }
    assert captured["headers"] == {
        "Authorization": "Bearer adc-token",
        "Content-Type": "application/json; charset=utf-8",
        "x-goog-user-project": "rasikh-fleet-2026",
    }


def say(context: Context, signature: str, text: str, *, defects: list[Defect] | None = None) -> WitnessTestimony:
    return WitnessTestimony(
        SURFACE,
        context,
        Outcome.REACHED,
        content_signature=signature,
        geometry=[{"selector": "main", "tag": "main", "text": text}],
        defects=defects or [],
    )


def test_semantic_pairs_share_one_batched_embedding_call() -> None:
    embeddings = FakeEmbeddings({
        "Invite teammates": [1.0, 0.0],
        "Add collaborators": [0.99, 0.01],
        "Billing overview": [0.0, 1.0],
        "Delete workspace": [1.0, 0.0],
    })
    models = SemanticComparator(embedding_client=embeddings, translation_client=FakeTranslation({}))

    results = models.evaluate([
        SemanticPair("invite", SemanticPairKind.CONTENT, "Invite teammates", "Add collaborators"),
        SemanticPair("billing", SemanticPairKind.CONTENT, "Billing overview", "Delete workspace"),
    ])

    assert len(embeddings.calls) == 1
    assert results[0].equivalent
    assert not results[1].equivalent
    assert models.embedding_usage.calls_attempted == models.embedding_usage.calls_succeeded == 1


def test_locale_pair_translates_then_reuses_the_embedding_batch() -> None:
    embeddings = FakeEmbeddings({"Sign in": [1.0, 0.0], "تسجيل الدخول": [1.0, 0.0]})
    translation = FakeTranslation({("Sign in", "en", "ar"): "تسجيل الدخول"})
    models = SemanticComparator(embedding_client=embeddings, translation_client=translation)

    result = models.evaluate([
        SemanticPair("locale", SemanticPairKind.LOCALE, "Sign in", "تسجيل الدخول", "en", "ar"),
    ])[0]

    assert result.equivalent
    assert translation.calls == [(["Sign in"], "en", "ar")]
    assert embeddings.calls == [["تسجيل الدخول", "تسجيل الدخول"]]
    assert models.translation_usage.calls_attempted == models.translation_usage.calls_succeeded == 1


def test_embedding_failure_is_visible_to_the_caller() -> None:
    models = SemanticComparator(
        embedding_client=FakeEmbeddings({}, RuntimeError("Vertex unavailable")),
        translation_client=FakeTranslation({}),
    )

    result = models.evaluate([
        SemanticPair("content", SemanticPairKind.CONTENT, "before", "after"),
    ])[0]

    assert result.similarity is None
    assert "Vertex unavailable" in (result.degraded_reason or "")
    assert models.embedding_usage.calls_attempted == 1
    assert models.embedding_usage.calls_succeeded == 0
    assert "Vertex unavailable" in (models.embedding_usage.last_error or "")


def test_translation_failure_keeps_raw_evidence_as_a_visible_fallback() -> None:
    arabic = Context(locale=Locale.AR, varies=Axis.LOCALE)
    models = SemanticComparator(
        embedding_client=FakeEmbeddings({}),
        translation_client=FakeTranslation({}, RuntimeError("translation outage")),
    )
    findings = compare([
        say(BASELINE, "english", "Guide title"),
        say(arabic, "arabic", "guide.title", defects=[Defect.UNTRANSLATED]),
    ], semantics=models)

    report = models.report()

    assert [finding.defect for finding in findings] == [Defect.UNTRANSLATED]
    assert "translation outage" in (findings[0].evidence or "")
    assert report["translation"]["calls_attempted"] == 1
    assert "translation outage" in str(report["translation"].get("last_error"))
    assert report["embeddings"]["calls_attempted"] == 0


def test_reworded_content_replaces_the_hash_finding_with_embedding_equivalence() -> None:
    dark = Context(theme=Theme.DARK, varies=Axis.THEME)
    embeddings = FakeEmbeddings({
        "Invite teammates": [1.0, 0.0],
        "Add collaborators": [0.99, 0.01],
    })
    models = SemanticComparator(embedding_client=embeddings, translation_client=FakeTranslation({}))

    findings = compare([
        say(BASELINE, "fnv-before", "Invite teammates"),
        say(dark, "fnv-after", "Add collaborators"),
    ], semantics=models)

    assert findings == []
    assert embeddings.calls == [["Invite teammates", "Add collaborators"]]


def test_semantic_difference_keeps_divergence_with_similarity_evidence() -> None:
    dark = Context(theme=Theme.DARK, varies=Axis.THEME)
    embeddings = FakeEmbeddings({"Billing overview": [0.0, 1.0], "Delete workspace": [1.0, 0.0]})
    models = SemanticComparator(embedding_client=embeddings, translation_client=FakeTranslation({}))

    findings = compare([
        say(BASELINE, "fnv-before", "Billing overview"),
        say(dark, "fnv-after", "Delete workspace"),
    ], semantics=models)

    assert [finding.kind for finding in findings] == [FindingKind.CONTENT_DIVERGENCE]
    assert findings[0].evidence is not None
    assert "similarity=0.000" in findings[0].evidence


def test_wrong_arabic_translation_is_a_real_untranslated_finding() -> None:
    arabic = Context(locale=Locale.AR, varies=Axis.LOCALE)
    embeddings = FakeEmbeddings({"إدارة الفواتير": [0.0, 1.0], "حذف مساحة العمل": [1.0, 0.0]})
    translation = FakeTranslation({("Manage billing", "en", "ar"): "إدارة الفواتير"})
    models = SemanticComparator(embedding_client=embeddings, translation_client=translation)

    findings = compare([
        say(BASELINE, "english", "Manage billing"),
        say(arabic, "arabic", "حذف مساحة العمل"),
    ], semantics=models)

    assert len(findings) == 1
    assert findings[0].kind is FindingKind.RENDER_DEFECT
    assert findings[0].defect is Defect.UNTRANSLATED
    assert "similarity=0.000" in (findings[0].evidence or "")


def test_embedding_failure_falls_back_to_hash_with_explicit_evidence() -> None:
    dark = Context(theme=Theme.DARK, varies=Axis.THEME)
    models = SemanticComparator(
        embedding_client=FakeEmbeddings({}, RuntimeError("service offline")),
        translation_client=FakeTranslation({}),
    )

    findings = compare([
        say(BASELINE, "fnv-before", "Before"),
        say(dark, "fnv-after", "After"),
    ], semantics=models)

    assert [finding.kind for finding in findings] == [FindingKind.CONTENT_DIVERGENCE]
    assert "degraded" in (findings[0].evidence or "")
    assert "service offline" in (findings[0].evidence or "")


def test_semantic_comparison_cap_returns_visible_degradation() -> None:
    embeddings = FakeEmbeddings({"before": [1.0, 0.0], "after": [0.0, 1.0]})
    models = SemanticComparator(embedding_client=embeddings, translation_client=FakeTranslation({}))
    pairs = [
        SemanticPair(str(index), SemanticPairKind.CONTENT, "before", "after")
        for index in range(MAX_SEMANTIC_COMPARISONS_PER_RUN + 1)
    ]

    results = models.evaluate(pairs)

    assert len(results) == len(pairs)
    assert "cap" in (results[-1].degraded_reason or "")
    assert len(embeddings.calls) == 1
