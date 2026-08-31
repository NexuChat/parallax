#!/usr/bin/env python3
"""Verify generated specs with private, mount-scoped demo role sessions."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_demo_suite  # noqa: E402


def _combined_states(host: str, private_root: Path) -> dict[str, Path]:
    merged: dict[str, dict[str, list[object]]] = {
        "owner": {"cookies": [], "origins": []},
        "member": {"cookies": [], "origins": []},
    }
    for site in run_demo_suite.discover_sites():
        if not site.accounts:
            continue
        states = run_demo_suite.build_storage_states(site, host, private_root / site.name)
        for role, state_path in states.items():
            if role not in merged:
                continue
            state = json.loads(state_path.read_text(encoding="utf-8"))
            for cookie in state["cookies"]:
                cookie["path"] = f"/{site.name}"
                merged[role]["cookies"].append(cookie)
            merged[role]["origins"].extend(state.get("origins", []))

    paths: dict[str, Path] = {}
    for role, state in merged.items():
        if not state["cookies"]:
            raise RuntimeError(f"demo release state has no {role} session")
        path = private_root / f"storage-{role}.json"
        path.write_text(json.dumps(state), encoding="utf-8")
        os.chmod(path, 0o600)
        paths[role] = path
    return paths


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build temporary mount-scoped role states, execute every public generated "
            "spec against the running demo fleet, then remove the private states."
        ),
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--expected", type=int, default=18)
    parser.add_argument("--report", default="web/generated-spec-verification.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.expected < 1:
        raise SystemExit("--expected must be positive")
    with TemporaryDirectory(prefix="parallax-demo-release-states-") as private:
        states = _combined_states(args.base_url.rstrip("/"), Path(private))
        command = [
            "node",
            str(ROOT / "scripts" / "verify-generated-specs.mjs"),
            "--expected",
            str(args.expected),
            "--base-url",
            args.base_url,
            "--owner-state",
            str(states["owner"]),
            "--member-state",
            str(states["member"]),
            "--report",
            str(ROOT / args.report),
        ]
        return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
