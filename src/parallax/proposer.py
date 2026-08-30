"""Constrain Gemini relational scenario proposals to baseline evidence."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit


@dataclass(frozen=True)
class ObservedAffordance:
    """One selector the baseline rendered on a discovered route."""

    route: str
    selector: str
    label: str
    kind: str


@dataclass(frozen=True)
class BaselineObservation:
    """The evidence Gemini may use to suggest a relational check."""

    start_url: str
    routes: tuple[str, ...]
    affordances: tuple[ObservedAffordance, ...]
    endpoints: tuple[str, ...]
    roles: tuple[str, ...]
    text: str = ""


@dataclass(frozen=True)
class ProposalCandidate:
    """One model proposal that passed the observed-reference guard."""

    index: int
    data: object


@dataclass(frozen=True)
class ProposalRejection:
    """Why one model proposal could not reach validation."""

    index: int
    reason: str


@dataclass(frozen=True)
class ProposalBatch:
    """Raw model proposals after the observed-reference guard."""

    proposed: int
    candidates: tuple[ProposalCandidate, ...]
    rejections: tuple[ProposalRejection, ...]
    note: str | None = None


@dataclass(frozen=True)
class ProposalReport:
    """The proposal result recorded by a completed conductor run."""

    enabled: bool
    proposed: int
    validated: int
    rejections: tuple[ProposalRejection, ...] = ()
    calls_attempted: int = 0
    calls_succeeded: int = 0
    route: str = "disabled"
    last_error: str | None = None
    note: str | None = None

    @classmethod
    def disabled(cls) -> "ProposalReport":
        return cls(False, 0, 0, note="scenario proposal disabled")


class ScenarioProposer:
    """Ask Gemini for constrained relational scenarios, never executable instructions."""

    model = "gemini-3.5-flash"

    def __init__(
        self,
        client: Any | None = None,
        *,
        max_scenarios: int = 3,
        token_fetcher: Callable[[], str] | None = None,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._client = client
        self._max_scenarios = max(1, max_scenarios)
        self._token_fetcher = token_fetcher
        self._client_factory = client_factory or self._google_client
        self._project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        self._location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
        self.route = self._select_route()
        self.calls_attempted = 0
        self.calls_succeeded = 0
        self.last_error: str | None = None

    def propose(self, observation: BaselineObservation) -> ProposalBatch:
        """Return only candidates whose references came from the baseline."""
        client = self._client or self._environment_client()
        if client is None:
            self.calls_attempted += 1
            self.last_error = self.last_error or "no client: credentials for the selected route were rejected"
            return ProposalBatch(0, (), (), self.last_error)

        self.calls_attempted += 1
        try:
            response = self._generate(client, observation)
        except Exception as error:
            self.last_error = f"{type(error).__name__}: {str(error)[:200]}"
            return ProposalBatch(0, (), (), self.last_error)
        self.calls_succeeded += 1

        scenarios = self._parse_response(response)
        if scenarios is None:
            self.last_error = "Gemini did not return a JSON scenarios list"
            return ProposalBatch(0, (), (), self.last_error)

        candidates: list[ProposalCandidate] = []
        rejections: list[ProposalRejection] = []
        for index, scenario in enumerate(scenarios, start=1):
            if index > self._max_scenarios:
                rejections.append(ProposalRejection(index, f"proposal limit is {self._max_scenarios}"))
                continue
            if reason := self._invented_reference(scenario, observation):
                rejections.append(ProposalRejection(index, reason))
                continue
            candidates.append(ProposalCandidate(index, scenario))
        note = "Gemini proposed no scenarios" if not scenarios else None
        return ProposalBatch(len(scenarios), tuple(candidates), tuple(rejections), note)

    def _select_route(self) -> str:
        if self._client is not None:
            return "injected"
        return "vertex" if self._project else "disabled"

    def _environment_client(self) -> Any | None:
        if self.route == "vertex":
            try:
                self._client = self._vertex_client()
            except Exception:
                return None
        return self._client

    def _vertex_client(self, *, force_token: bool = False) -> Any:
        return self._client_factory(
            vertexai=True,
            project=self._project,
            location=self._location,
            credentials=self._vertex_credentials(force_token=force_token),
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
            ["gcloud", "auth", "print-access-token"], check=True, capture_output=True, text=True
        ).stdout.strip()

    @staticmethod
    def _google_client(**kwargs: Any) -> Any:
        from google import genai

        return genai.Client(**kwargs)

    def _generate(self, client: Any, observation: BaselineObservation) -> Any:
        kwargs = {"model": self.model, "contents": self._prompt(observation)}
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

    def _prompt(self, observation: BaselineObservation) -> str:
        evidence = {
            "routes": observation.routes,
            "affordances": [
                {"route": item.route, "selector": item.selector, "label": item.label, "kind": item.kind}
                for item in observation.affordances
            ],
            "endpoints": observation.endpoints,
            "roles": observation.roles,
            "visible_text": observation.text,
        }
        return (
            "You plan up to three relational browser tests. Return strict JSON only, with this exact envelope: "
            '{"scenarios":[{"type":"propagation|revocation","surface":"observed route","sender":"observed role",'
            '"receiver":"observed role","action":{"type":"submit_form","form":"observed form selector",'
            '"checks":["observed selector"],"fills":[{"selector":"observed selector","value":"text"}]},'
            '"effect":{"type":"visible|json_contains",...},"deadline_ms":positive_integer,"max_lag_ms":non_negative_integer}]}. '
            "For json_contains use an observed endpoint URL. A revocation requires max_lag_ms below deadline_ms. "
            "Use only the supplied routes, roles, and selectors; never return JavaScript, markdown, explanations, or extra keys. "
            "Prefer an owner action that removes or revokes a member when the evidence supports it. "
            f"Baseline evidence:\n{json.dumps(evidence, ensure_ascii=False, separators=(',', ':'))}"
        )

    @staticmethod
    def _parse_response(response: Any) -> list[object] | None:
        try:
            text = response if isinstance(response, str) else response.text
            if not isinstance(text, str):
                return None
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else ""
                if text.endswith("```"):
                    text = text[:-3]
            parsed = json.loads(text)
            scenarios = parsed.get("scenarios") if isinstance(parsed, Mapping) else None
            return scenarios if isinstance(scenarios, list) else None
        except Exception:
            return None

    def _invented_reference(self, scenario: object, observation: BaselineObservation) -> str | None:
        if not isinstance(scenario, Mapping):
            return None
        if reason := _grammar_rejection(scenario):
            return reason
        surface = scenario.get("surface")
        if isinstance(surface, str):
            route = _resolve(surface, observation.start_url)
            if route not in observation.routes:
                return f"surface {surface!r} was not observed"
        else:
            route = None
        for field in ("sender", "receiver"):
            if isinstance(value := scenario.get(field), str) and value not in observation.roles:
                return f"{field} role {value!r} was not supplied to the run"
        if scenario.get("sender") == scenario.get("receiver") and isinstance(scenario.get("sender"), str):
            return "sender and receiver must be distinct observed roles"
        if route is None:
            return None
        forms = {item.selector for item in observation.affordances if item.route == route and item.kind == "form"}
        selectors = {item.selector for item in observation.affordances if item.route == route}
        if isinstance(action := scenario.get("action"), Mapping):
            if isinstance(form := action.get("form"), str) and form not in forms:
                return f"action.form selector {form!r} was not observed"
            for selector in action.get("checks", []) if isinstance(action.get("checks"), list) else []:
                if isinstance(selector, str) and selector not in selectors:
                    return f"action.checks selector {selector!r} was not observed"
            for fill in action.get("fills", []) if isinstance(action.get("fills"), list) else []:
                if isinstance(fill, Mapping) and isinstance(selector := fill.get("selector"), str) and selector not in selectors:
                    return f"action.fills selector {selector!r} was not observed"
        for field in ("effect", "distribution", "enforcement"):
            if reason := self._effect_reference(scenario.get(field), field, route, selectors, observation.endpoints):
                return reason
        return None

    @staticmethod
    def _effect_reference(
        effect: object, field: str, route: str, selectors: set[str], endpoints: tuple[str, ...]
    ) -> str | None:
        if not isinstance(effect, Mapping):
            return None
        if effect.get("type") == "visible" and isinstance(selector := effect.get("selector"), str) and selector not in selectors:
            return f"{field}.selector {selector!r} was not observed"
        if effect.get("type") == "json_contains" and isinstance(url := effect.get("url"), str):
            known = {_endpoint_path(item) for item in endpoints}
            if _endpoint_path(urljoin(route, url)) not in known:
                return f"{field}.url {url!r} was not observed"
        return None


def _resolve(value: str, start_url: str) -> str:
    """Resolve a model surface exactly as the existing scenario validator does."""
    parts = urlsplit(urljoin(start_url, value))
    return urlunsplit(parts._replace(fragment=""))


def _endpoint_path(value: str) -> str:
    """Compare endpoints by origin and path while allowing observed query keys."""
    parts = urlsplit(value)
    return urlunsplit(parts._replace(query="", fragment=""))


def _grammar_rejection(scenario: Mapping[str, object]) -> str | None:
    """Reject model-only fields the data validator has no reason to execute."""
    if unexpected := set(scenario) - {
        "type", "surface", "sender", "receiver", "action", "effect", "deadline_ms", "max_lag_ms", "distribution", "enforcement",
    }:
        return f"{sorted(unexpected)[0]} is outside the relational scenario grammar"
    if isinstance(action := scenario.get("action"), Mapping):
        if unexpected := set(action) - {"type", "form", "checks", "fills"}:
            return f"action.{sorted(unexpected)[0]} is outside the relational scenario grammar"
        if isinstance(fills := action.get("fills"), list):
            for fill in fills:
                if isinstance(fill, Mapping) and (unexpected := set(fill) - {"selector", "value"}):
                    return f"action.fills.{sorted(unexpected)[0]} is outside the relational scenario grammar"
    for field in ("effect", "distribution", "enforcement"):
        if isinstance(effect := scenario.get(field), Mapping):
            allowed = {"type", "selector"} if effect.get("type") == "visible" else {
                "type", "url", "items", "field", "equals",
            }
            if unexpected := set(effect) - allowed:
                return f"{field}.{sorted(unexpected)[0]} is outside the relational scenario grammar"
    return None
