"""Run and grade Parallax against every available demo site."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from collections.abc import Iterable
import ctypes
import errno
from http.cookies import SimpleCookie
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo"
if str(DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(DEMO_DIR))

from parallax.conductor import Conductor, RelationalScenario  # noqa: E402
from parallax.__main__ import audiences_from_data, choreographies_from_data, relational_scenarios_from_data  # noqa: E402
from parallax.audience import AudienceScenario  # noqa: E402
from parallax.choreography import Choreography  # noqa: E402
from parallax.media import MEDIA_BROWSER_ARGS  # noqa: E402
from parallax.emitter import spec_for  # noqa: E402
from parallax.specialists import AccessSpecialist, LayoutI18nSpecialist, RealtimeSpecialist  # noqa: E402
from parallax.types import Axis, BASELINE, Context, Finding, FindingKind, Outcome, Privilege, Severity, Surface, SurfaceKind, Testimony  # noqa: E402
from serve import discover_sites  # noqa: E402
from sites.base import Planted, Site  # noqa: E402


@dataclass
class Grade:
    found: list[Planted]
    missed: list[Planted]
    false_positives: list[Finding]


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _route_matches(planted_route: str, finding_route: str, site_name: str | None) -> bool:
    expected = _path(planted_route)
    actual = _path(finding_route)
    if site_name and actual == f"/{site_name}":
        actual = "/"
    elif site_name and actual.startswith(f"/{site_name}/"):
        actual = actual[len(site_name) + 1 :]
    expected_parts = expected.split("/")
    actual_parts = actual.split("/")
    if len(expected_parts) != len(actual_parts):
        return False
    return all(
        bool(actual_part) if re.fullmatch(r"<[^/<>]+>", expected_part) else expected_part == actual_part
        for expected_part, actual_part in zip(expected_parts, actual_parts)
    )


def _path(value: str) -> str:
    path = urlsplit(value).path or "/"
    return path if path.startswith("/") else f"/{path}"


def _finding_defects(finding: Finding) -> set[str]:
    defects = {_value(finding.kind)}
    if finding.defect is not None:
        defects.add(_value(finding.defect))
    else:
        for testimony in finding.testimonies:
            defects.update(_value(defect) for defect in getattr(testimony, "defects", []))
    return defects


def _matches(plant: Planted, finding: Finding, site_name: str | None) -> bool:
    if getattr(plant, "evidence", "") and plant.evidence not in f"{finding.summary} {finding.evidence or ''}":
        # The right kind of finding on the right route is not necessarily the
        # finding the plant describes. A fixture that breaks earlier, for its
        # own reasons, produced exactly that shape and was counted as found.
        return False
    return (
        plant.defect in _finding_defects(finding)
        and plant.axis == _value(finding.axis)
        and _route_matches(plant.route, finding.surface.path, site_name)
    )


def grade_findings(findings: list[Finding], planted: list[Planted], site_name: str | None = None) -> Grade:
    unmatched = list(findings)
    found: list[Planted] = []
    missed: list[Planted] = []
    for plant in planted:
        matches = [item for item in unmatched if _matches(plant, item, site_name)]
        if not matches:
            missed.append(plant)
        else:
            found.append(plant)
            matched_ids = {id(item) for item in matches}
            unmatched = [item for item in unmatched if id(item) not in matched_ids]
    return Grade(found, missed, unmatched)


def exit_code(grades: dict[str, Grade]) -> int:
    return int(any(grade.missed or grade.false_positives for grade in grades.values()))


def summary_payload(grades: dict[str, Grade], host: str, generated_at: str | None = None) -> dict[str, object]:
    """Make the public, machine-readable account of one graded demo run."""
    sites: dict[str, dict[str, object]] = {}
    totals = {"planted": 0, "found": 0, "missed": 0, "false_positives": 0}
    for name, grade in grades.items():
        plants = [
            {"name": plant.note, "defect": plant.defect, "axis": plant.axis, "route": plant.route, "verdict": verdict}
            for verdict, group in (("found", grade.found), ("missed", grade.missed))
            for plant in group
        ]
        site = {
            "planted": len(plants), "found": len(grade.found), "missed": len(grade.missed),
            "false_positives": len(grade.false_positives), "plants": plants,
        }
        sites[name] = site
        for key in totals:
            totals[key] += int(site[key])
    payload = {
        "host": host.rstrip("/"),
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "sites": sites,
        "totals": totals,
    }
    _assert_public_value(payload)
    return payload


def write_summary(grades: dict[str, Grade], host: str, path: Path, *, generated_at: str | None = None) -> None:
    """Publish the completed demo grade where the public page can fetch it."""
    path.write_text(json.dumps(summary_payload(grades, host, generated_at), indent=2) + "\n", encoding="utf-8")


def generated_example_spec() -> str:
    """Generate the public output example from the same Finding model as a run."""
    surface = Surface(SurfaceKind.ROUTE, "https://demo.mlki.app/workspace/audit")
    anon = BASELINE.__class__(privilege=Privilege.ANON, varies=Axis.PRIVILEGE)
    finding = Finding(
        FindingKind.ESCALATION, Severity.HIGH, surface, Axis.PRIVILEGE,
        "Anonymous access to the workspace audit route.",
        [Testimony(surface, BASELINE, Outcome.REACHED), Testimony(surface, anon, Outcome.REACHED)],
    )
    return spec_for(finding)


def write_generated_example(path: Path) -> None:
    generated = generated_example_spec()
    _assert_public_spec(generated)
    path.write_text(generated, encoding="utf-8")


_RUN_MANIFEST = {"feed.jsonl", "mosaics", "specs"}
_ARTIFACT_SUFFIXES = {"mosaics": (".jpg", ".jpeg", ".png", ".webp"), "specs": (".spec.ts",)}
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_AT_FDCWD = -100
_RENAME_EXCHANGE = 0x2
_SENSITIVE_FIELDS = frozenset({
    "access_token", "apikey", "api_key", "authorization", "client_secret", "cookie",
    "password", "refresh_token", "secret", "session", "token",
})
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|authorization|cookie|session|token)"
    r"\s*[:=]\s*(?!process\.env\b|undefined\b|null\b|false\b)[\"']?[A-Za-z0-9_./+=-]{6,}",
)
_PRIVATE_SPEC_PATH = re.compile(r"(?i)(?:^|[\"'\s])(?:\.auth/|runs/[^\"'\s]+/storage-|/tmp/[^\"'\s]*storage-)")


def _assert_public_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("sensitive credentials are not allowed in public URLs")
    for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower().replace("-", "_") in _SENSITIVE_FIELDS:
            raise ValueError("sensitive credentials are not allowed in public URLs")


def _assert_public_value(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in _SENSITIVE_FIELDS:
                raise ValueError(f"sensitive field is not allowed in public artifact: {key}")
            _assert_public_value(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _assert_public_value(child)
    elif isinstance(value, str):
        if "://" in value:
            _assert_public_url(value)
        if _SENSITIVE_ASSIGNMENT.search(value) or re.search(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{6,}", value):
            raise ValueError("sensitive value is not allowed in public artifact")


def _assert_public_feed(text: str) -> None:
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"public feed line {number} is not valid JSON") from error
        _assert_public_value(event)


def _assert_public_spec(text: str) -> None:
    if _PRIVATE_SPEC_PATH.search(text):
        raise ValueError("private storage path is not allowed in public spec")
    _assert_public_value(text)


def _rename_exchange(left: Path, right: Path) -> None:
    """Atomically exchange two sibling directories without an ENOENT interval."""
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError as error:
        raise OSError(errno.ENOSYS, "renameat2 is unavailable") from error
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(_AT_FDCWD, os.fsencode(left), _AT_FDCWD, os.fsencode(right), _RENAME_EXCHANGE) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(left), str(right))


def _replace_directory_atomically(stage: Path, target: Path) -> None:
    """Commit a fully staged directory, never deleting an existing generation first."""
    try:
        target_mode = target.lstat().st_mode
    except FileNotFoundError:
        stage.replace(target)
        return
    if not stat.S_ISDIR(target_mode):
        raise ValueError(f"publish target must be a real directory: {target}")
    try:
        _rename_exchange(stage, target)
    except OSError as error:
        raise RuntimeError("atomic exchange is unavailable; previous public generation was retained") from error
    # `stage` now names the old, no-longer-public generation. Cleanup failure must
    # not invalidate the successfully committed replacement.
    shutil.rmtree(stage, ignore_errors=True)


def _open_directory(path: Path) -> int:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW)
    except OSError as error:
        raise ValueError(f"artifact path must be a real directory: {path}") from error
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ValueError(f"artifact path must be a real directory: {path}")
    return descriptor


def _copy_regular_file(source_dir: int, name: str, target: Path) -> None:
    try:
        source = os.open(name, os.O_RDONLY | _NOFOLLOW, dir_fd=source_dir)
    except OSError as error:
        raise ValueError(f"artifact must be a regular file: {name}") from error
    try:
        if not stat.S_ISREG(os.fstat(source).st_mode):
            raise ValueError(f"artifact must be a regular file: {name}")
        target_descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o644)
        with os.fdopen(source, "rb") as source_file, os.fdopen(target_descriptor, "wb") as target_file:
            source = -1
            shutil.copyfileobj(source_file, target_file)
    finally:
        if source >= 0:
            os.close(source)


def _read_regular_text(path: Path) -> str:
    directory = _open_directory(path.parent)
    try:
        try:
            source = os.open(path.name, os.O_RDONLY | _NOFOLLOW, dir_fd=directory)
        except OSError as error:
            raise ValueError(f"artifact must be a regular file: {path.name}") from error
        try:
            if not stat.S_ISREG(os.fstat(source).st_mode):
                raise ValueError(f"artifact must be a regular file: {path.name}")
            with os.fdopen(source, "r", encoding="utf-8") as input_file:
                source = -1
                return input_file.read()
        finally:
            if source >= 0:
                os.close(source)
    finally:
        os.close(directory)


def _copy_artifact_directory(source_root: int, name: str, target: Path) -> None:
    try:
        source = os.open(name, os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW, dir_fd=source_root)
    except OSError as error:
        raise ValueError(f"artifact path must be a real directory: {name}") from error
    try:
        entries = sorted(os.listdir(source))
        unexpected = [entry for entry in entries if not entry.endswith(_ARTIFACT_SUFFIXES[name])]
        if unexpected:
            raise ValueError(f"unexpected artifact in {name}: {unexpected[0]}")
        target.mkdir(mode=0o755)
        for entry in entries:
            _copy_regular_file(source, entry, target / entry)
            if name == "specs":
                _assert_public_spec((target / entry).read_text(encoding="utf-8"))
    finally:
        os.close(source)


def _publish_run(source: Path, target: Path) -> None:
    """Atomically replace one public run from a strict, no-follow manifest."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if not stat.S_ISDIR(target.parent.lstat().st_mode):
        raise ValueError(f"publish root must be a real directory: {target.parent}")
    stage = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    source_root = -1
    try:
        source_root = _open_directory(source)
        entries = set(os.listdir(source_root))
        unexpected = sorted(entries - _RUN_MANIFEST)
        if unexpected:
            raise ValueError(f"unexpected artifact in run {source.name}: {unexpected[0]}")
        if "feed.jsonl" not in entries:
            raise ValueError(f"run {source.name} is missing feed.jsonl")
        _copy_regular_file(source_root, "feed.jsonl", stage / "feed.jsonl")
        _assert_public_feed((stage / "feed.jsonl").read_text(encoding="utf-8"))
        for name in ("specs", "mosaics"):
            if name in entries:
                _copy_artifact_directory(source_root, name, stage / name)
        _replace_directory_atomically(stage, target)
        stage = None
    except Exception:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
        raise
    finally:
        if source_root >= 0:
            os.close(source_root)


def _public_run_entry(directory: Path) -> dict[str, object]:
    findings: set[str] = set()
    severities: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    mosaics: set[tuple[object, object]] = set()
    for line in _read_regular_text(directory / "feed.jsonl").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        payload = event["payload"]
        if event["kind"] == "mosaic":
            mosaics.add((payload.get("surface_id"), payload.get("seq")))
        elif event["kind"] == "finding" and payload.get("id") not in findings:
            findings.add(payload["id"])
            if isinstance(payload.get("severity"), str):
                severities[payload["severity"]] += 1
            if isinstance(payload.get("kind"), str):
                kinds[payload["kind"]] += 1
    return {
        "feed": f"runs/{directory.name}/feed.jsonl",
        "mosaics": len(mosaics),
        "findings": len(findings),
        "by_severity": dict(severities),
        "by_kind": dict(kinds),
    }


def _existing_public_runs(public_root: Path) -> list[Path]:
    """Published runs already present, ignoring anything that is not one."""
    if not public_root.is_dir():
        return []
    return [
        entry for entry in sorted(public_root.iterdir())
        if entry.is_dir() and not entry.is_symlink() and (entry / "feed.jsonl").is_file()
    ]


def publish_sweeps(
    runs_root: Path,
    public_root: Path,
    site_names: Iterable[str],
    *,
    latest_site: str = "workspace",
) -> dict[str, dict[str, object]]:
    """Publish complete demo evidence while excluding role storage states.

    Publishing replaces the whole public directory in one exchange, so anything
    already published that this sweep does not produce has to be carried across
    deliberately. Sweeps of real applications live here too — they are run by
    hand against sites the demo fleet does not serve — and without this they
    were deleted, silently, by the next `--publish` of the demo suite.
    """
    names = tuple(str(name) for name in site_names)
    for name in names:
        if not name or name in {".", ".."} or Path(name).name != name:
            raise ValueError(f"invalid demo site name: {name!r}")
    carried = tuple(sorted(
        entry.name for entry in _existing_public_runs(public_root)
        if entry.name not in names and entry.name != "latest"
    ))
    public_root.parent.mkdir(parents=True, exist_ok=True)
    if not stat.S_ISDIR(public_root.parent.lstat().st_mode):
        raise ValueError(f"publish root must be a real directory: {public_root.parent}")
    stage = Path(tempfile.mkdtemp(prefix=f".{public_root.name}-", dir=public_root.parent))
    descriptor = -1
    try:
        for name in names:
            _publish_run(runs_root / name, stage / name)
        # Re-published through the same strict manifest and the same secret
        # checks as a fresh run, rather than moved: a carried run is not exempt
        # from the rules that let it be public in the first place.
        for name in carried:
            _publish_run(public_root / name, stage / name)
        if latest_site in names:
            _publish_run(stage / latest_site, stage / "latest")
        index = {name: _public_run_entry(stage / name) for name in sorted((*names, *carried))}
        descriptor, staged_name = tempfile.mkstemp(prefix=".index-", suffix=".json.tmp", dir=stage)
        staged_index = Path(staged_name)
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            descriptor = -1
            output.write(json.dumps(index, indent=2) + "\n")
        staged_index.replace(stage / "index.json")
        _replace_directory_atomically(stage, public_root)
        stage = None
        return index
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)


def _specialists(no_vision: bool) -> list[object]:
    specialists: list[object] = [AccessSpecialist(), RealtimeSpecialist()]
    if not no_vision and os.environ.get("GEMINI_API_KEY"):
        specialists.append(LayoutI18nSpecialist())
    return specialists


def _relational_scenarios(site: Site, host: str) -> list[RelationalScenario]:
    """Read optional, data-only scenario declarations from a demo site."""
    declarations = getattr(site, "relational_scenarios", [])
    if not declarations:
        return []
    mounted: list[dict[str, object]] = []
    for declaration in declarations:
        if not isinstance(declaration, dict):
            raise SystemExit(f"site {site.name} relational scenarios: each declaration must be an object")
        copy = dict(declaration)
        surface = copy.get("surface")
        if isinstance(surface, str) and not surface.startswith(("http://", "https://")):
            copy["surface"] = f"{host.rstrip('/')}/{site.name}/{surface.lstrip('/')}"
        mounted.append(copy)
    return relational_scenarios_from_data(mounted, host, source=f"site {site.name} relational scenarios")


def _audiences(site: Site, host: str) -> list[AudienceScenario]:
    """Read optional one-actor, many-observer declarations from a demo site."""
    declarations = getattr(site, "audiences", [])
    if not declarations:
        return []
    mounted: list[dict[str, object]] = []
    for declaration in declarations:
        if not isinstance(declaration, dict):
            raise SystemExit(f"site {site.name} audiences: each declaration must be an object")
        copy = dict(declaration)
        copy["surface"] = _mounted(copy.get("surface"), site, host)
        actor = copy.get("actor")
        if isinstance(actor, dict) and actor.get("surface"):
            copy["actor"] = {**actor, "surface": _mounted(actor["surface"], site, host)}
        observers = copy.get("observers")
        if isinstance(observers, list):
            copy["observers"] = [
                {**o, "surface": _mounted(o["surface"], site, host)}
                if isinstance(o, dict) and o.get("surface") else o
                for o in observers
            ]
        mounted.append(copy)
    return audiences_from_data({"audiences": mounted}, host, source=f"site {site.name} audiences")


def _mounted(value: object, site: Site, host: str) -> object:
    """A site-relative path becomes an absolute URL under that site's mount."""
    if isinstance(value, str) and not value.startswith(("http://", "https://")):
        return f"{host.rstrip('/')}/{site.name}/{value.lstrip('/')}"
    return value


def _choreographies(site: Site, host: str) -> list[Choreography]:
    """Read optional ordered-protocol declarations from a demo site.

    Mounting is per-participant as well as per-choreography: each player opens
    their own URL, because a session's identity in these fixtures is part of the
    address rather than a cookie.
    """
    declarations = getattr(site, "choreographies", [])
    if not declarations:
        return []
    def mount(value: object) -> object:
        return _mounted(value, site, host)

    mounted: list[dict[str, object]] = []
    for declaration in declarations:
        if not isinstance(declaration, dict):
            raise SystemExit(f"site {site.name} choreographies: each declaration must be an object")
        copy = dict(declaration)
        copy["surface"] = mount(copy.get("surface"))
        participants = copy.get("participants")
        if isinstance(participants, list):
            copy["participants"] = [
                {**p, "surface": mount(p["surface"])} if isinstance(p, dict) and p.get("surface") else p
                for p in participants
            ]
        mounted.append(copy)
    return choreographies_from_data({"choreographies": mounted}, host, source=f"site {site.name} choreographies")


def storage_state_from_login_response(response: object, origin: str) -> dict[str, object]:
    """Convert a plain HTTP login response into Playwright's storage-state shape."""
    headers = getattr(response, "headers", {})
    raw_cookies = headers.get_all("Set-Cookie") if hasattr(headers, "get_all") else None
    if not raw_cookies:
        raw_cookie = headers.get("Set-Cookie")
        raw_cookies = [raw_cookie] if raw_cookie else []
    host = urlsplit(origin).hostname
    if not host:
        raise ValueError(f"login origin has no host: {origin}")
    cookies: list[dict[str, object]] = []
    for raw_cookie in raw_cookies:
        parsed = SimpleCookie(str(raw_cookie))
        for morsel in parsed.values():
            same_site = morsel["samesite"].capitalize() if morsel["samesite"] else "Lax"
            cookies.append({
                "name": morsel.key,
                "value": morsel.value,
                "domain": host,
                "path": morsel["path"] or "/",
                "httpOnly": bool(morsel["httponly"]),
                "secure": bool(morsel["secure"]),
                "sameSite": same_site,
            })
    if not cookies:
        raise ValueError("login response did not set a session cookie")
    return {"cookies": cookies, "origins": []}


def _storage_state_identity(state: dict[str, object]) -> str:
    """Canonical identity for rejecting roles that received the same session."""
    cookies = state.get("cookies", [])
    origins = state.get("origins", [])
    if not isinstance(cookies, list) or not isinstance(origins, list):
        raise ValueError("login response produced an invalid storage state")
    canonical = {
        "cookies": sorted(cookies, key=lambda cookie: json.dumps(cookie, sort_keys=True, separators=(",", ":"))),
        "origins": sorted(origins, key=lambda origin: json.dumps(origin, sort_keys=True, separators=(",", ":"))),
    }
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"))


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request: Request, fp: object, code: int, msg: str, headers: object, newurl: str) -> None:
        return None

    def http_error_302(self, request: Request, fp: object, code: int, msg: str, headers: object) -> object:
        return fp

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


# Matches the Chromium the sweep drives, so the login helper and the witnesses
# present the same client to the application under test.
_LOGIN_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36"
)


def build_storage_states(site: Site, host: str, run_dir: Path) -> dict[str, Path]:
    """Log in every declared role, requiring distinct usable authenticated states."""
    states: dict[str, Path] = {}
    identities: dict[str, str] = {}
    run_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = _open_directory(run_dir)
    origin = host.rstrip("/")
    try:
        for account in site.accounts:
            if not account.role or Path(account.role).name != account.role:
                raise ValueError(f"invalid account role: {account.role!r}")
            if account.role in states:
                raise ValueError(f"duplicate declared account role: {account.role}")
            request = Request(
                f"{origin}/{site.name}/login",
                data=urlencode({"email": account.email, "username": account.email, "password": account.password}).encode(),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    # A default urllib agent is refused with 403 by the bot
                    # protection in front of the public demo fleet, which made
                    # every role login fail against a real host while working
                    # against localhost. The sweep itself drives a real browser;
                    # only this login helper spoke as a script.
                    "User-Agent": _LOGIN_USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                },
                method="POST",
            )
            response: object | None = None
            try:
                with build_opener(_NoRedirect()).open(request) as response:
                    state = storage_state_from_login_response(response, origin)
            except Exception as error:
                status = getattr(response, "status", getattr(error, "code", "unknown"))
                print(
                    f"login failed for site {site.name}, role {account.role}, "
                    f"server returned HTTP {status}: {error}",
                    file=sys.stderr,
                )
                raise RuntimeError(f"required role login failed for {site.name}/{account.role}") from error
            identity = _storage_state_identity(state)
            duplicate = next((role for role, value in identities.items() if value == identity), None)
            if duplicate is not None:
                raise ValueError(
                    f"duplicate authenticated identity for site {site.name}: {account.role} matches {duplicate}"
                )
            filename = f"storage-{account.role}.json"
            payload = json.dumps(state).encode("utf-8")
            descriptor = os.open(
                filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600, dir_fd=directory,
            )
            try:
                os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "wb") as output:
                    descriptor = -1
                    output.write(payload)
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
            states[account.role] = run_dir / filename
            identities[account.role] = identity
    except Exception:
        for path in states.values():
            path.unlink(missing_ok=True)
        raise
    finally:
        os.close(directory)
    return states


async def _conduct_site(
    site: Site,
    host: str,
    run_dir: Path,
    browser: object,
    *,
    no_vision: bool,
    max_surfaces: int,
) -> object:
    storage_root = Path(tempfile.mkdtemp(prefix=f"parallax-{site.name}-storage-"))
    try:
        artifact_roots = (run_dir.parent, ROOT / "console", ROOT / "web")
        if any(storage_root.resolve().is_relative_to(root.resolve()) for root in artifact_roots):
            raise RuntimeError("private storage-state directory resolved inside a public artifact tree")
        return await Conductor(
            f"{host}/{site.name}/", run_dir, browser=browser,
            specialists=_specialists(no_vision), max_surfaces=max_surfaces,
            storage_states=build_storage_states(site, host, storage_root),
            relational_scenarios=_relational_scenarios(site, host),
            choreographies=_choreographies(site, host),
            audiences=_audiences(site, host),
        ).conduct()
    finally:
        shutil.rmtree(storage_root)


async def _one(sweep: Any, site: Site) -> Any:
    """Run a single sweep, returning its exception rather than raising it."""
    try:
        return await sweep(site)
    except Exception as error:  # noqa: BLE001 - reported by the caller
        return error


async def run(args: argparse.Namespace) -> dict[str, Grade]:
    from playwright.async_api import async_playwright

    sites = [site for site in discover_sites() if args.only is None or site.name == args.only]
    if args.only and not sites:
        raise SystemExit(f"unknown or unavailable site: {args.only}")
    host = args.host.rstrip("/")
    grades: dict[str, Grade] = {}
    # Sites are independent — separate module state, separate run directory,
    # separate mosaic wall — so several can be swept at once. Surfaces within a
    # site cannot: they share one wall with one frame sequence, and interleaving
    # them would publish a mosaic whose tiles came from two different pages.
    #
    # The default is still one at a time, deliberately. Half of what this gate
    # measures is timing — settle windows, tap targets, overflow at a threshold —
    # and a loaded machine moves those. The published figure is produced by the
    # sequential path; --jobs is for iterating, not for grading.
    limit = asyncio.Semaphore(max(1, args.jobs))
    async with async_playwright() as playwright:
        # The call fixture negotiates real peer connections, so the browser needs a
        # synthetic microphone and permission to play without a gesture. Without
        # these every observer measures silence and the room looks broken.
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", *MEDIA_BROWSER_ARGS],
        )

        async def sweep(site: Site) -> tuple[str, Grade]:
            async with limit:
                summary = await _conduct_site(
                    site, host, ROOT / "runs" / site.name, browser,
                    no_vision=args.no_vision, max_surfaces=args.max_surfaces,
                )
                return site.name, grade_findings(summary.findings, site.planted, site.name)

        # A site that measures real-time behaviour is swept on its own. Everything
        # else is deterministic markup and can share the machine.
        realtime = [site for site in sites if getattr(site, "realtime", False)]
        batched = [site for site in sites if not getattr(site, "realtime", False)]
        try:
            if args.jobs > 1:
                print(
                    f"sweeping {len(batched)} sites {args.jobs} at a time"
                    + (f", then {len(realtime)} alone" if realtime else ""),
                    file=sys.stderr,
                )
            swept = list(await asyncio.gather(*(sweep(site) for site in batched), return_exceptions=True))
            for site in realtime:
                swept.append(await _one(sweep, site))
            for site, result in zip([*batched, *realtime], swept):
                if isinstance(result, BaseException):
                    # One site failing must not discard the others' evidence, and
                    # must not be reported as that site passing.
                    raise SystemExit(f"sweep of {site.name} failed: {type(result).__name__}: {result}")
                grades[result[0]] = result[1]
        finally:
            await browser.close()
    # Reported in declaration order however they were scheduled, so two runs of
    # the same commit produce the same report.
    return {site.name: grades[site.name] for site in sites if site.name in grades}


def print_report(grades: dict[str, Grade]) -> None:
    print("site       found  missed  false+  details")
    for name, grade in grades.items():
        details = ", ".join([f"missed:{plant.defect}@{plant.route}" for plant in grade.missed] + [
            f"false+:{_value(finding.kind)}@{urlsplit(finding.surface.path).path}" for finding in grade.false_positives
        ]) or "ok"
        print(f"{name:<10} {len(grade.found):>5}  {len(grade.missed):>6}  {len(grade.false_positives):>6}  {details}")
    found = sum(len(grade.found) for grade in grades.values())
    missed = sum(len(grade.missed) for grade in grades.values())
    false_positives = sum(len(grade.false_positives) for grade in grades.values())
    code = exit_code(grades)
    result = "PASS" if code == 0 else "FAIL"
    print(f"total      {found:>5}  {missed:>6}  {false_positives:>6}  {result} (exit {code})")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="http://127.0.0.1:8080")
    parser.add_argument("--only")
    parser.add_argument("--no-vision", action="store_true")
    parser.add_argument("--max-surfaces", type=int, default=64)
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        metavar="N",
        help="sweep N sites concurrently; the graded figure is produced at the default of 1",
    )
    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="grade without writing web/graded-summary.json or console/runs/; "
        "use this to reproduce the figures without replacing the published evidence",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    grades = asyncio.run(run(args))
    if not args.no_publish:
        write_summary(grades, args.host, ROOT / "web" / "graded-summary.json")
        write_generated_example(ROOT / "web" / "generated-example.spec.ts")
        publish_sweeps(ROOT / "runs", ROOT / "console" / "runs", grades)
    print_report(grades)
    return exit_code(grades)


if __name__ == "__main__":
    raise SystemExit(main())
