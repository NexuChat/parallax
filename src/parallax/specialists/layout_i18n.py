"""Model-assisted visual comparison of a settled witness mosaic."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from typing import Any, Callable

from ..contracts import Moment
from ..types import Axis, Finding, FindingKind, Severity, Surface, Testimony


class LayoutI18nSpecialist:
    """Ask Gemini to spot visual outliers that geometry cannot describe."""

    name = "layout_i18n"

    model = "gemini-3.5-flash"

    def __init__(
        self,
        client: Any | None = None,
        *,
        max_moments: int = 5,
        token_fetcher: Callable[[], str] | None = None,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._client = client
        self._max_moments = max(0, max_moments)
        self._token_fetcher = token_fetcher
        self._client_factory = client_factory or self._google_client
        self._project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        self._location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
        self.route = self._select_route()

    def judge(
        self, moments: Sequence[Moment], testimonies: Sequence[Testimony]
    ) -> list[Finding]:
        client = self._client or self._environment_client()
        if client is None:
            return []

        findings: list[Finding] = []
        sent = 0
        for moment in moments:
            if not moment.changed or sent >= self._max_moments:
                continue
            sent += 1
            try:
                response = self._generate(client, moment)
                verdict = self._parse_response(response)
            except Exception:
                continue
            findings.extend(self._findings_from_verdict(verdict, moment, testimonies))
        return findings

    def _select_route(self) -> str:
        if self._client is not None:
            return "injected"
        if self._project:
            return "vertex"
        if os.environ.get("GEMINI_API_KEY"):
            return "ai_studio"
        return "disabled"

    def _environment_client(self) -> Any | None:
        if self.route == "vertex":
            try:
                self._client = self._vertex_client()
            except Exception:
                return None
        elif self.route == "ai_studio":
            try:
                self._client = self._client_factory(api_key=os.environ["GEMINI_API_KEY"])
            except Exception:
                return None
        return self._client

    def _vertex_client(self, *, force_token: bool = False) -> Any:
        credentials = self._vertex_credentials(force_token=force_token)
        return self._client_factory(
            vertexai=True,
            project=self._project,
            location=self._location,
            credentials=credentials,
            http_options={"api_version": "v1"},
        )

    def _vertex_credentials(self, *, force_token: bool) -> Any:
        if not force_token and self._token_fetcher is None:
            try:
                import google.auth

                credentials, _ = google.auth.default()
                return credentials
            except Exception:
                pass
        from google.oauth2.credentials import Credentials

        token = (self._token_fetcher or self._gcloud_token)()
        if not token:
            raise RuntimeError("gcloud returned an empty access token")
        return Credentials(token=token)

    @staticmethod
    def _gcloud_token() -> str:
        return subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    @staticmethod
    def _google_client(**kwargs: Any) -> Any:
        from google import genai

        return genai.Client(**kwargs)

    def _generate(self, client: Any, moment: Moment) -> Any:
        kwargs = {
            "model": self.model,
            "contents": [self._prompt(moment), self._image_part(moment)],
        }
        try:
            return client.models.generate_content(**kwargs)
        except Exception as error:
            if self.route != "vertex" or not self._is_auth_failure(error):
                raise
            self._client = self._vertex_client(force_token=True)
            return self._client.models.generate_content(**kwargs)

    @staticmethod
    def _is_auth_failure(error: Exception) -> bool:
        status = getattr(error, "status_code", None) or getattr(error, "code", None)
        if status in {401, 403}:
            return True
        message = str(error).upper()
        return "UNAUTHENTICATED" in message or "401" in message

    @staticmethod
    def _image_part(moment: Moment) -> dict[str, dict[str, bytes | str]]:
        return {"inline_data": {"mime_type": "image/jpeg", "data": moment.mosaic.jpeg}}

    @staticmethod
    def _prompt(moment: Moment) -> str:
        tiles = "\n".join(
            f"- {tile.context_name}: x={tile.x}, y={tile.y}, w={tile.w}, h={tile.h}"
            for tile in moment.mosaic.tiles
        )
        return (
            "You are reviewing one composed browser screenshot. Each rectangle below is "
            "a different witness context in the same application. Compare them as a set. "
            "Report only visible mixed-language text, missed untranslated text, broken RTL, "
            "or a tile visibly inconsistent with its peers. Return strict JSON only: "
            '{"findings":[{"context":"exact tile context",'
            '"kind":"render|divergence","summary":"short visible evidence"}]}. '
            "Do not infer access policy or invent contexts.\nTiles:\n"
            f"{tiles}"
        )

    @staticmethod
    def _parse_response(response: Any) -> list[Mapping[str, Any]]:
        try:
            text = response if isinstance(response, str) else response.text
            if not isinstance(text, str):
                return []
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else ""
                if text.endswith("```"):
                    text = text[:-3]
            parsed = json.loads(text)
            items = parsed.get("findings", []) if isinstance(parsed, Mapping) else parsed
            return [item for item in items if isinstance(item, Mapping)] if isinstance(items, list) else []
        except Exception:
            return []

    @staticmethod
    def _findings_from_verdict(
        verdict: Sequence[Mapping[str, Any]], moment: Moment, testimonies: Sequence[Testimony]
    ) -> list[Finding]:
        tile_names = {tile.context_name for tile in moment.mosaic.tiles}
        by_context = {testimony.context.name: testimony for testimony in testimonies}
        surface: Surface | None = moment.surface or next(
            (testimony.surface for testimony in testimonies), None
        )
        if surface is None:
            return []

        findings: list[Finding] = []
        for item in verdict:
            context_name, kind, summary = item.get("context"), item.get("kind"), item.get("summary")
            if (
                not isinstance(context_name, str)
                or context_name not in tile_names
                or not isinstance(kind, str)
                or not isinstance(summary, str)
                or not summary.strip()
            ):
                continue
            testimony = by_context.get(context_name)
            axis = testimony.context.varies if testimony is not None else _axis(item.get("axis"))
            if axis is None:
                continue
            finding_kind = _kind(kind)
            if finding_kind is None:
                continue
            findings.append(
                Finding(
                    kind=finding_kind,
                    severity=Severity.MEDIUM,
                    surface=surface,
                    axis=axis,
                    summary=summary.strip(),
                    testimonies=[testimony] if testimony is not None else [],
                )
            )
        return findings


def _kind(value: str) -> FindingKind | None:
    return {
        "render": FindingKind.RENDER_DEFECT,
        "render_defect": FindingKind.RENDER_DEFECT,
        "divergence": FindingKind.CONTENT_DIVERGENCE,
        "content_divergence": FindingKind.CONTENT_DIVERGENCE,
    }.get(value.lower())


def _axis(value: Any) -> Axis | None:
    try:
        return Axis(value)
    except (TypeError, ValueError):
        return None
