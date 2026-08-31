"""Subset the demo fleet's bundled webfonts.

The graded figures only mean something if the same checkout produces them on
someone else's machine, and it did not. The demo sites asked for `Georgia`,
`system-ui` and `ui-monospace`; none of those is installed everywhere, so each
host resolved a different fallback with different text metrics, and a
measurement like horizontal overflow or tap-target size moved across its
threshold. The same commit that grades 15/15/0 here reported two render findings
nobody planted on a GitHub runner, and twenty under a Liberation-only font set.

Fonts the demo serves itself remove the variable. This script rebuilds them from
GNU FreeFont, which is available under the GPL with the font exception and — in
its serif and mono faces — covers Latin and Arabic, so the locale witness also
renders the same way whatever the host has installed.

    python scripts/build_demo_fonts.py

Run it only to regenerate `demo/assets/fonts/`; the results are committed, so an
ordinary checkout never needs fontTools.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/usr/share/fonts/truetype/freefont")
TARGET = ROOT / "demo" / "assets" / "fonts"

# Latin for the interface, Arabic for the locale witness, plus the punctuation
# and shapes the demo chrome draws. Subsetting by range rather than by the
# current strings keeps the fonts valid when the demo copy changes.
UNICODES = (
    "U+0020-007E",  # ASCII
    "U+00A0-00FF",  # Latin-1 supplement
    "U+0100-017F",  # Latin Extended-A
    "U+0600-06FF",  # Arabic
    "U+FB50-FDFF",  # Arabic presentation forms A
    "U+FE70-FEFF",  # Arabic presentation forms B
    "U+2000-206F",  # general punctuation
    "U+2190-21FF",  # arrows
    "U+25A0-25FF",  # geometric shapes
)

FACES = (
    ("FreeSerif.ttf", "parallax-serif-400.woff2"),
    ("FreeSerifBold.ttf", "parallax-serif-700.woff2"),
    ("FreeSans.ttf", "parallax-sans-400.woff2"),
    ("FreeSansBold.ttf", "parallax-sans-700.woff2"),
    ("FreeMono.ttf", "parallax-mono-400.woff2"),
    ("FreeMonoBold.ttf", "parallax-mono-700.woff2"),
)


def main() -> int:
    try:
        from fontTools.subset import main as subset_main
    except ImportError:
        print("needs fontTools: python -m pip install fonttools brotli", file=sys.stderr)
        return 2
    if not SOURCE.is_dir():
        print(f"GNU FreeFont not found at {SOURCE}", file=sys.stderr)
        return 2

    TARGET.mkdir(parents=True, exist_ok=True)
    for source_name, target_name in FACES:
        source = SOURCE / source_name
        if not source.is_file():
            print(f"missing source face: {source}", file=sys.stderr)
            return 2
        subset_main([
            str(source),
            f"--unicodes={','.join(UNICODES)}",
            "--layout-features=*",
            "--flavor=woff2",
            f"--output-file={TARGET / target_name}",
        ])
        print(f"  {target_name:28s} {(TARGET / target_name).stat().st_size // 1024:>4} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
