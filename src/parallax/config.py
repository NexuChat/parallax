"""Project configuration, so a sweep is a command rather than an incantation.

Every option here already exists as a flag, and a research tool can stop there.
A tool someone runs on their own application every week cannot: the same eight
arguments retyped from shell history are a way to get one of them wrong quietly,
and they cannot be reviewed, committed, or explained to a colleague.

So the settings that belong to a project live in `parallax.toml` beside it, and
the flags stay for the things that belong to a single run. A flag always wins
over the file, because the reason to type one is to override what is written
down.

Secrets are the exception and are never written here. The file may say *where*
credentials live; it may not contain them.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


CONFIG_NAME = "parallax.toml"

TEMPLATE = '''\
# Parallax project configuration.
#
# Everything here is optional and every value can be overridden by a flag on the
# command line. Run `parallax sweep` in this directory and it is picked up
# automatically.

[target]
# The application to sweep.
url = "https://app.example.com"

# Where the sweep writes its evidence: the feed, the mosaics, the generated
# specs. One directory per run.
out = "runs/latest"

# How many surfaces to visit before stopping. Discovery is breadth-first, so a
# small number still covers distinct pages rather than one page's controls.
max_surfaces = 12

[auth]
# A JSON file of role -> {identifier, secret}. Parallax finds the sign-in
# surface itself; it does not need to be told where the login page is.
#
# The path is written here. The secrets are not: a credential in a config file
# is a credential in version control.
credentials = ".auth/credentials.json"

[models]
# Vertex AI project for Gemini and the semantic lens. Without it the run says
# the lens is disabled rather than silently skipping it.
google_cloud_project = ""

# Set to false to run entirely on deterministic measurement, with no model call.
vision = true

# Ask Gemini to propose relational and capability tests from what the baseline
# observed. Every proposal is filtered against observed evidence before it runs.
propose_scenarios = false

# An Ollama-compatible endpoint that groups findings by cause. Optional; the run
# reports the grouping as disabled rather than pretending it happened.
gemma_url = ""

[delivery]
# Open a pull request with the generated specs. Needs GITHUB_TOKEN in the
# environment; the base branch is only ever read.
open_pr = ""
base = ""

[scenarios]
# Relational and capability scenarios, in the data-only grammar.
file = ""

[constraints]
# Routes and controls the sweep must never touch. Plain text matches anywhere
# (so "delete" covers every delete button); glob patterns match the whole path.
# An agent pressing things on a live application needs a written "never this".
deny = []
'''


@dataclass
class Settings:
    """Resolved project settings. Every field has a usable default."""

    url: str | None = None
    out: Path | None = None
    max_surfaces: int | None = None
    credentials: Path | None = None
    google_cloud_project: str | None = None
    vision: bool | None = None
    propose_scenarios: bool | None = None
    gemma_url: str | None = None
    open_pr: str | None = None
    pr_base: str | None = None
    scenarios: Path | None = None
    deny: list[str] = field(default_factory=list)
    source: Path | None = field(default=None, compare=False)

    def describe(self) -> str:
        return f"configuration from {self.source}" if self.source else "no configuration file"


def find_config(start: Path | None = None) -> Path | None:
    """Look for the file here, then upward — a sweep is usually run from a subdirectory."""
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def load(path: Path | None = None) -> Settings:
    """Read the file if there is one, and say plainly when there is not."""
    found = path or find_config()
    if found is None:
        return Settings()
    try:
        data = tomllib.loads(found.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise SystemExit(f"{found}: {error}") from error
    return _settings_from(data, found)


def _settings_from(data: dict[str, Any], source: Path) -> Settings:
    target = _table(data, "target")
    auth = _table(data, "auth")
    models = _table(data, "models")
    delivery = _table(data, "delivery")
    scenarios = _table(data, "scenarios")
    constraints = _table(data, "constraints")
    base = source.parent

    def resolved(value: Any) -> Path | None:
        # Relative to the file, not to the shell's working directory, so the
        # same configuration means the same thing from anywhere in the project.
        text = _text(value)
        if not text:
            return None
        path = Path(text)
        return path if path.is_absolute() else (base / path)

    return Settings(
        url=_text(target.get("url")),
        out=resolved(target.get("out")),
        max_surfaces=_int(target.get("max_surfaces")),
        credentials=resolved(auth.get("credentials")),
        google_cloud_project=_text(models.get("google_cloud_project")),
        vision=_bool(models.get("vision")),
        propose_scenarios=_bool(models.get("propose_scenarios")),
        gemma_url=_text(models.get("gemma_url")),
        open_pr=_text(delivery.get("open_pr")),
        pr_base=_text(delivery.get("base")),
        scenarios=resolved(scenarios.get("file")),
        deny=_texts(constraints.get("deny")),
        source=source,
    )


def _table(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    return value if isinstance(value, dict) else {}


def _texts(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None
