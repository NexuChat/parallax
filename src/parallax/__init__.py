"""Parallax: relational browser regression.

Point it at a URL and it gives back failing Playwright specs. Seven isolated
browser contexts witness the same commit of the same page at once, each
differing from the baseline by exactly one property, and a finding is the
disagreement between them — so there is no stored baseline to record and no
golden file to keep, and the first sweep of an application it has never seen
still has something to say.

This file exists so that `parallax` is a real package rather than a namespace
one. Without it the import works by accident: Python treats the directory as an
implicit namespace package, `parallax.__file__` is None, and any other
distribution installed alongside that happens to ship a `parallax/` directory
silently merges into the same name.
"""

from __future__ import annotations

__all__ = ["__version__"]

# Read from the installed distribution rather than repeated here, so a release
# cannot disagree with itself about what it is.
try:  # pragma: no cover - trivial, and exercised by the packaging test
    from importlib.metadata import PackageNotFoundError, version

    __version__ = version("parallax")
except Exception:  # pragma: no cover - a source checkout has no metadata
    __version__ = "0+unknown"
