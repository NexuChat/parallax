"""Group a noisy finding list into the few causes a reviewer can act on.

A sweep of five applications currently publishes ninety-four findings that are
not defects. That number is honest — it is measured against declared plants and
printed on the front page — but ninety-four lines is not a report anyone reads.
Most of them repeat: the same overflow on the same grid, seen from six witnesses
and re-observed on four routes.

Grouping is judgement about wording, not measurement, so it is the one place a
small language model earns its place here. Gemma reads only the summaries the
deterministic layers already produced and returns a partition of their ids. It
cannot invent a finding, change a severity, or reach a page: anything it returns
that does not name findings from the input is discarded.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass

from .types import Finding


VERTEX_MODEL = "gemma-4-26b-a4b-it-maas"


def _vertex_project() -> str:
    return os.environ.get("GOOGLE_CLOUD_PROJECT", "")


DEFAULT_MODEL = "gemma3:4b"
_PROMPT = (
    "You are grouping automated browser-test findings by shared root cause, so a "
    "reviewer reads a few causes instead of a long list. Group only what the text "
    "shows: findings that describe the same defect on the same component belong "
    "together, and a finding you are unsure about stays in its own group. Do not "
    "invent findings, do not rename them, and use only the ids given.\n"
    "Return strict JSON and nothing else: "
    '{"groups":[{"label":"short cause, at most eight words","ids":[1,2]}]}\n\n'
    "Findings:\n"
)


@dataclass(frozen=True)
class TriageGroup:
    """One cause and the findings a reviewer can settle by fixing it."""

    label: str
    finding_ids: tuple[str, ...]


@dataclass(frozen=True)
class TriageReport:
    """What the grouping pass did, including when it did nothing and why."""

    model: str
    endpoint: str
    attempted: bool
    groups: tuple[TriageGroup, ...] = ()
    error: str | None = None

    @property
    def summary(self) -> str:
        if not self.attempted:
            return (
                "triage disabled: set PARALLAX_GEMMA_URL for an Ollama-compatible "
                "endpoint, or GOOGLE_CLOUD_PROJECT to use Gemma 4 on Vertex"
            )
        if self.error:
            return f"triage unavailable: {self.error}"
        grouped = sum(len(group.finding_ids) for group in self.groups)
        return f"{grouped} findings grouped into {len(self.groups)} causes by {self.model}"


class GemmaTriage:
    """Ask a local Gemma endpoint to partition findings by cause."""

    def __init__(
        self,
        endpoint: str | None = None,
        *,
        model: str | None = None,
        max_findings: int = 120,
        transport: object | None = None,
    ) -> None:
        self._max = max(1, max_findings)
        self._transport = transport
        # An explicit Ollama endpoint wins, because someone who set one meant it.
        # Otherwise Gemma 4 on Vertex, which needs no local model and lets anyone
        # with the project's credentials reproduce the grouping. The MaaS model
        # is served only from the global endpoint; asking us-central1 for it
        # answers "only available via global endpoint" rather than 404.
        self.endpoint = endpoint if endpoint is not None else os.environ.get("PARALLAX_GEMMA_URL", "")
        self.route = "ollama" if self.endpoint else ("vertex" if _vertex_project() else "disabled")
        default = DEFAULT_MODEL if self.route != "vertex" else VERTEX_MODEL
        self.model = model or os.environ.get("PARALLAX_GEMMA_MODEL", default)

    def group(self, findings: Sequence[Finding]) -> TriageReport:
        if self.route == "disabled" or not findings:
            return TriageReport(self.model, self.endpoint, attempted=False)

        numbered = list(enumerate(findings[: self._max], start=1))
        lines = "\n".join(f"{n}: [{f.kind.value}] {f.summary}" for n, f in numbered)
        try:
            raw = self._ask(_PROMPT + lines)
        except Exception as error:
            # Reported rather than swallowed: a reader must be able to tell a run
            # that grouped nothing from a run whose grouper was unreachable.
            return TriageReport(self.model, self.endpoint, attempted=True,
                                error=f"{type(error).__name__}: {str(error)[:160]}")
        return TriageReport(self.model, self.endpoint, attempted=True,
                            groups=tuple(self._parse(raw, dict(numbered))))

    def _ask(self, prompt: str) -> str:
        if self._transport is not None:
            return str(self._transport(prompt))  # type: ignore[operator]
        if self.route == "vertex":
            return self._ask_vertex(prompt)
        body = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        }).encode()
        request = urllib.request.Request(
            self.endpoint.rstrip("/") + "/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode()).get("response", "")

    def _ask_vertex(self, prompt: str) -> str:
        """Gemma 4 through the same project and credentials as everything else."""
        from .semantics import GoogleCloudTransport

        transport = GoogleCloudTransport()
        url = (
            "https://aiplatform.googleapis.com/v1/projects/"
            f"{transport.project}/locations/global/publishers/google/models/{self.model}:generateContent"
        )
        body = transport.post(url, {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0},
        })
        candidates = body.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemma returned no candidates")
        parts = candidates[0].get("content", {}).get("parts") or []
        return "".join(str(part.get("text", "")) for part in parts)

    @staticmethod
    def _parse(raw: str, numbered: dict[int, Finding]) -> list[TriageGroup]:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        try:
            parsed = json.loads(text)
        except Exception:
            return []
        groups: list[TriageGroup] = []
        claimed: set[int] = set()
        for item in parsed.get("groups", []) if isinstance(parsed, dict) else []:
            if not isinstance(item, dict):
                continue
            label = item.get("label")
            ids = item.get("ids")
            if not isinstance(label, str) or not label.strip() or not isinstance(ids, list):
                continue
            # A number the model did not receive, or one it already used, is not a
            # grouping decision — it is noise, and it is dropped rather than
            # letting the model expand its own input.
            chosen = [n for n in ids if isinstance(n, int) and n in numbered and n not in claimed]
            if not chosen:
                continue
            claimed.update(chosen)
            groups.append(TriageGroup(label.strip()[:80], tuple(numbered[n].id for n in chosen)))
        return groups
