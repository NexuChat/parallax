"""Bounded Google semantic comparisons for hash-mismatched witness text."""

from __future__ import annotations

import json
import os
import subprocess
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from math import sqrt
from typing import Any, Protocol
from urllib.request import Request, urlopen


EMBEDDING_MODEL = "text-embedding-005"
SEMANTIC_EQUIVALENCE_THRESHOLD = 0.82
"""0.82 rejects topical overlap while retaining ordinary paraphrases and translations."""

# A sweep batches at most twelve changed regions into one Translation request and
# one Vertex request: two paid model calls per run, regardless of surface count.
MAX_SEMANTIC_COMPARISONS_PER_RUN = 12
MAX_SEMANTIC_MODEL_CALLS_PER_RUN = 2


class SemanticPairKind(str, Enum):
    CONTENT = "content"
    LOCALE = "locale"


@dataclass(frozen=True)
class SemanticPair:
    """Two bounded visible-text regions that require a semantic judgement."""

    key: str
    kind: SemanticPairKind
    baseline_text: str
    variant_text: str
    source_locale: str = "en"
    target_locale: str = "en"


@dataclass(frozen=True)
class SemanticResult:
    """The result for one requested comparison, including any degradation."""

    key: str
    similarity: float | None
    equivalent: bool | None
    degraded_reason: str | None = None


@dataclass
class ModelUsage:
    """The model-call accounting that makes degraded runs auditable."""

    name: str
    route: str
    calls_attempted: int = 0
    calls_succeeded: int = 0
    last_error: str | None = None

    def report(self) -> dict[str, object]:
        result: dict[str, object] = {
            "name": self.name,
            "route": self.route,
            "calls_attempted": self.calls_attempted,
            "calls_succeeded": self.calls_succeeded,
        }
        if self.last_error:
            result["last_error"] = self.last_error
        return result


class EmbeddingClient(Protocol):
    """The narrow, injectable Vertex embedding seam."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class TranslationClient(Protocol):
    """The narrow, injectable Cloud Translation seam."""

    def translate(self, texts: Sequence[str], *, source: str, target: str) -> list[str]: ...


class GoogleCloudTransport:
    """ADC-authenticated JSON transport shared by the two Google APIs."""

    def __init__(
        self,
        project: str | None = None,
        *,
        post: Callable[[str, dict[str, str], dict[str, object]], dict[str, object]] | None = None,
    ) -> None:
        self.project = project or os.environ.get("GOOGLE_CLOUD_PROJECT", "rasikh-fleet-2026")
        self._post = post or self._urlopen_post
        self._credentials: Any | None = None

    def post(self, url: str, payload: dict[str, object]) -> dict[str, object]:
        return self._post(url, self._headers(), payload)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token()}",
            "Content-Type": "application/json; charset=utf-8",
            "x-goog-user-project": self.project,
        }

    def _token(self) -> str:
        """Prefer application-default credentials, then a gcloud user token.

        Cloud Run supplies ADC from the metadata server, so the first branch is
        the production path. A developer who has authenticated with `gcloud`
        but never run `gcloud auth application-default login` has no ADC, which
        used to disable the semantic lens with a credentials error while the
        vision lens on the same machine worked; both now accept the same two
        routes.
        """
        credentials = self._credentials
        if credentials is None:
            try:
                import google.auth

                credentials, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
            except Exception:
                return self._gcloud_token()
            self._credentials = credentials
        if not credentials.valid or not credentials.token:
            from google.auth.transport.requests import Request as GoogleRequest

            credentials.refresh(GoogleRequest())
        return str(credentials.token)

    @staticmethod
    def _gcloud_token() -> str:
        completed = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        return completed.stdout.strip()

    @staticmethod
    def _urlopen_post(
        url: str, headers: dict[str, str], payload: dict[str, object]
    ) -> dict[str, object]:
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=15) as response:  # noqa: S310 - endpoints are constants below
            body = json.loads(response.read().decode("utf-8"))
        if not isinstance(body, dict):
            raise RuntimeError("Google API returned a non-object JSON response")
        return body


class VertexEmbeddings:
    """Call Vertex text-embedding-005 with all comparison regions in one batch."""

    route = "vertex"

    def __init__(self, transport: GoogleCloudTransport) -> None:
        self._transport = transport

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        payload = {"instances": [{"content": text} for text in texts]}
        url = (
            "https://us-central1-aiplatform.googleapis.com/v1/projects/"
            f"{self._transport.project}/locations/us-central1/publishers/google/models/"
            f"{EMBEDDING_MODEL}:predict"
        )
        body = self._transport.post(url, payload)
        predictions = body.get("predictions")
        if not isinstance(predictions, list) or len(predictions) != len(texts):
            raise RuntimeError("Vertex returned a different number of embeddings")
        vectors: list[list[float]] = []
        for prediction in predictions:
            embedding = prediction.get("embeddings") if isinstance(prediction, dict) else None
            values = embedding.get("values") if isinstance(embedding, dict) else None
            if not isinstance(values, list) or not all(isinstance(value, (int, float)) for value in values):
                raise RuntimeError("Vertex returned an invalid embedding vector")
            vectors.append([float(value) for value in values])
        return vectors


class CloudTranslation:
    """Call Cloud Translation v2 with one batch per locale direction."""

    route = "cloud-translation"

    def __init__(self, transport: GoogleCloudTransport) -> None:
        self._transport = transport

    def translate(self, texts: Sequence[str], *, source: str, target: str) -> list[str]:
        body = self._transport.post(
            "https://translation.googleapis.com/language/translate/v2",
            {"q": list(texts), "source": source, "target": target, "format": "text"},
        )
        data = body.get("data")
        translations = data.get("translations") if isinstance(data, dict) else None
        if not isinstance(translations, list) or len(translations) != len(texts):
            raise RuntimeError("Cloud Translation returned a different number of strings")
        values = [item.get("translatedText") if isinstance(item, dict) else None for item in translations]
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise RuntimeError("Cloud Translation returned an empty translation")
        return [str(value) for value in values]


class SemanticComparator:
    """Translate locale regions and compare all requested regions by cosine similarity."""

    def __init__(
        self,
        embedding_client: EmbeddingClient | None = None,
        translation_client: TranslationClient | None = None,
        *,
        project: str | None = None,
    ) -> None:
        transport = GoogleCloudTransport(project)
        self._embedding_client = embedding_client or VertexEmbeddings(transport)
        self._translation_client = translation_client or CloudTranslation(transport)
        self.embedding_usage = ModelUsage(
            EMBEDDING_MODEL,
            getattr(self._embedding_client, "route", "injected"),
        )
        self.translation_usage = ModelUsage(
            "cloud-translation-v2",
            getattr(self._translation_client, "route", "injected"),
        )

    def report(self) -> dict[str, dict[str, object]]:
        """Return independent call counts for both load-bearing models."""
        return {
            "embeddings": self.embedding_usage.report(),
            "translation": self.translation_usage.report(),
        }

    def evaluate(self, pairs: Sequence[SemanticPair]) -> list[SemanticResult]:
        """Batch a run's bounded regions, retaining a result for every requested pair."""
        limited = list(pairs[:MAX_SEMANTIC_COMPARISONS_PER_RUN])
        results: dict[str, SemanticResult] = {
            pair.key: SemanticResult(
                pair.key, None, None,
                f"semantic comparison cap of {MAX_SEMANTIC_COMPARISONS_PER_RUN} regions reached",
            )
            for pair in pairs[MAX_SEMANTIC_COMPARISONS_PER_RUN:]
        }
        pending: list[tuple[SemanticPair, str, str]] = []
        locale_groups: dict[tuple[str, str], list[SemanticPair]] = defaultdict(list)
        for pair in limited:
            if pair.kind is SemanticPairKind.CONTENT:
                pending.append((pair, pair.baseline_text, pair.variant_text))
            else:
                locale_groups[(pair.source_locale, pair.target_locale)].append(pair)

        for group_number, ((source, target), group) in enumerate(locale_groups.items()):
            if group_number >= MAX_SEMANTIC_MODEL_CALLS_PER_RUN - 1:
                for pair in group:
                    results[pair.key] = SemanticResult(
                        pair.key, None, None,
                        f"semantic model call ceiling of {MAX_SEMANTIC_MODEL_CALLS_PER_RUN} reached",
                    )
                continue
            translated = self._translate([pair.baseline_text for pair in group], source, target)
            if translated is None:
                reason = self.translation_usage.last_error or "Cloud Translation was unavailable"
                for pair in group:
                    results[pair.key] = SemanticResult(pair.key, None, None, f"translation degraded: {reason}")
                continue
            pending.extend((pair, translated[index], pair.variant_text) for index, pair in enumerate(group))

        if pending:
            vectors = self._embed([text for _, left, right in pending for text in (left, right)])
            if vectors is None:
                reason = self.embedding_usage.last_error or "Vertex embeddings were unavailable"
                for pair, _, _ in pending:
                    results[pair.key] = SemanticResult(pair.key, None, None, f"embedding degraded: {reason}")
            else:
                for index, (pair, _, _) in enumerate(pending):
                    try:
                        similarity = _cosine(vectors[index * 2], vectors[index * 2 + 1])
                    except ValueError as error:
                        results[pair.key] = SemanticResult(pair.key, None, None, f"embedding degraded: {error}")
                        continue
                    results[pair.key] = SemanticResult(
                        pair.key, similarity, similarity >= SEMANTIC_EQUIVALENCE_THRESHOLD
                    )
        return [
            results.get(pair.key, SemanticResult(pair.key, None, None, "comparison was not evaluated"))
            for pair in pairs
        ]

    def _embed(self, texts: Sequence[str]) -> list[list[float]] | None:
        self.embedding_usage.calls_attempted += 1
        try:
            vectors = self._embedding_client.embed(texts)
            if len(vectors) != len(texts):
                raise RuntimeError("embedding client returned a different number of vectors")
        except Exception as error:
            self.embedding_usage.last_error = _error(error)
            return None
        self.embedding_usage.calls_succeeded += 1
        return vectors

    def _translate(self, texts: Sequence[str], source: str, target: str) -> list[str] | None:
        self.translation_usage.calls_attempted += 1
        try:
            values = self._translation_client.translate(texts, source=source, target=target)
            if len(values) != len(texts):
                raise RuntimeError("translation client returned a different number of strings")
        except Exception as error:
            self.translation_usage.last_error = _error(error)
            return None
        self.translation_usage.calls_succeeded += 1
        return values


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("embedding vectors have incompatible dimensions")
    magnitude_left = sqrt(sum(value * value for value in left))
    magnitude_right = sqrt(sum(value * value for value in right))
    if not magnitude_left or not magnitude_right:
        raise ValueError("embedding vector has zero magnitude")
    return sum(a * b for a, b in zip(left, right)) / (magnitude_left * magnitude_right)


def _error(error: Exception) -> str:
    return f"{type(error).__name__}: {str(error)[:200]}"
