from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_python_package_declares_runtime_auth_and_probe_asset() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "google-auth[requests]>=2.56.0,<3.0.0" in project["project"]["dependencies"]
    assert "probe.js" in project["tool"]["setuptools"]["package-data"]["parallax"]
    assert (ROOT / "src" / "parallax" / "probe.js").is_file()


def test_generated_playwright_harness_is_pinned_and_scoped() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    config = (ROOT / "playwright.config.ts").read_text(encoding="utf-8")

    assert package["private"] is True
    assert package["devDependencies"] == {"@playwright/test": "1.62.0"}
    assert package["scripts"]["test:generated"] == "playwright test"
    assert package["scripts"]["test:generated:list"] == "playwright test --list"
    assert 'testDir: "./console/runs"' in config
    assert 'testMatch: "**/*.spec.ts"' in config
    assert "process.env.PARALLAX_BASE_URL" in config
    assert '"http://127.0.0.1:8080"' in config


def test_playwright_lock_matches_the_declared_harness_version() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))

    assert lock["packages"][""]["devDependencies"] == package["devDependencies"]
    assert lock["packages"]["node_modules/@playwright/test"]["version"] == "1.62.0"


def test_generated_spec_verifier_is_a_reproducible_json_gate() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    verifier = ROOT / "scripts" / "verify-generated-specs.mjs"

    assert package["scripts"]["verify:generated"] == "node scripts/verify-generated-specs.mjs --expected 18"
    # console/runs also holds sweeps of real sites whose specs address their own
    # origin; verifying those against the demo fleet fails for the wrong reason.
    assert "--runs" in verifier.read_text(encoding="utf-8")
    assert verifier.is_file()

    help_result = subprocess.run(
        ["node", str(verifier), "--help"],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert help_result.returncode == 0
    assert "PARALLAX_OWNER_STORAGE_STATE" in help_result.stdout
    assert "--expected COUNT" in help_result.stdout
    assert "assertion_failures" in verifier.read_text(encoding="utf-8")
    assert "--reporter=json" in verifier.read_text(encoding="utf-8")


def test_demo_verifier_builds_private_mount_scoped_states_and_cleans_them() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    wrapper = ROOT / "scripts" / "verify_demo_generated.py"

    assert package["scripts"]["verify:demo-generated"] == "python scripts/verify_demo_generated.py"
    assert wrapper.is_file()

    # sys.executable, not a hardcoded .venv path: CI installs the package into
    # the runner's interpreter and never creates one, so the literal path made
    # this test pass only on a checkout that happened to have a local venv.
    help_result = subprocess.run(
        [sys.executable, str(wrapper), "--help"],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert help_result.returncode == 0
    assert "mount-scoped" in help_result.stdout
    source = wrapper.read_text(encoding="utf-8")
    assert "TemporaryDirectory" in source
    assert 'cookie["path"] = f"/{site.name}"' in source


def test_parallax_is_a_real_package_not_a_namespace_one() -> None:
    """A namespace package imports by accident and merges with anything sharing its name.

    Without __init__.py, Python treats src/parallax as an implicit namespace
    package: the import works, `__file__` is None, and any other installed
    distribution shipping a `parallax/` directory silently joins the same name.
    """
    import parallax

    assert parallax.__file__ is not None
    assert parallax.__file__.endswith("__init__.py")
    assert (ROOT / "src" / "parallax" / "__init__.py").is_file()


def test_the_package_reports_a_version_rather_than_asserting_one() -> None:
    import parallax

    assert isinstance(parallax.__version__, str) and parallax.__version__
