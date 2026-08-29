"""Run one sweep: discover an app, witness it from seven contexts, publish.

    python -m parallax https://app.example.com --out runs/first

Everything the run produces lands in one directory — the feed the console reads,
the mosaics it shows, and the failing Playwright specs the findings became.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from .conductor import Conductor
from .specialists import AccessSpecialist, LayoutI18nSpecialist, RealtimeSpecialist
from .types import Privilege, Severity


def _parse(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="parallax", description=__doc__.splitlines()[0])
    parser.add_argument("url", help="where the baseline witness starts")
    parser.add_argument("--out", default="runs/latest", type=Path, help="output directory")
    parser.add_argument("--max-surfaces", type=int, default=12)
    parser.add_argument("--settle-ms", type=int, default=500)
    parser.add_argument("--headed", action="store_true", help="show the browsers (a demo, not a run)")
    parser.add_argument(
        "--storage-state",
        action="append",
        default=[],
        metavar="ROLE=PATH",
        help="Playwright storage state per role, e.g. owner=.auth/owner.json (repeatable)",
    )
    parser.add_argument(
        "--no-vision",
        action="store_true",
        help="skip the Gemini lens; the deterministic ones still run",
    )
    return parser.parse_args(argv)


def _storage_states(pairs: list[str]) -> dict[Privilege | str, str]:
    states: dict[Privilege | str, str] = {}
    for pair in pairs:
        role, _, path = pair.partition("=")
        if not path:
            raise SystemExit(f"--storage-state expects ROLE=PATH, got {pair!r}")
        states[role.strip()] = path.strip()
    return states


def _specialists(no_vision: bool) -> list[object]:
    lenses: list[object] = [AccessSpecialist(), RealtimeSpecialist()]
    if no_vision:
        return lenses
    # The vision lens returns nothing at all without a key rather than failing the
    # run, but silently producing half a report is worse than saying so out loud.
    if not os.environ.get("GEMINI_API_KEY"):
        print("note: GEMINI_API_KEY is unset — running without the vision lens", file=sys.stderr)
        return lenses
    lenses.append(LayoutI18nSpecialist())
    return lenses


async def _run(args: argparse.Namespace) -> int:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=not args.headed, args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        try:
            summary = await Conductor(
                args.url,
                args.out,
                browser=browser,
                specialists=_specialists(args.no_vision),
                storage_states=_storage_states(args.storage_state) or None,
                max_surfaces=args.max_surfaces,
                settle_ms=args.settle_ms,
            ).conduct()
        finally:
            await browser.close()

    counts: dict[str, int] = {}
    for finding in summary.findings:
        counts[finding.severity.value] = counts.get(finding.severity.value, 0) + 1
    print(json.dumps({
        "surfaces": len(summary.surfaces),
        "testimonies": len(summary.testimonies),
        "findings": len(summary.findings),
        "by_severity": {level.value: counts.get(level.value, 0) for level in Severity},
        "feed": str(summary.feed_path),
        "specs": len(summary.spec_paths),
    }, indent=2))
    print(f"\nconsole: open console/index.html?feed=../{summary.feed_path}", file=sys.stderr)
    # A run that found nothing is a finished run, not a failed one.
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
