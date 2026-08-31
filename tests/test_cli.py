from __future__ import annotations

from pathlib import Path

import pytest

from parallax import cli, config


def write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / config.CONFIG_NAME
    path.write_text(body, encoding="utf-8")
    return path


def test_init_writes_a_file_a_sweep_can_actually_use(tmp_path: Path) -> None:
    assert cli.main(["init", str(tmp_path)]) == 0

    settings = config.load(tmp_path / config.CONFIG_NAME)

    assert settings.url == "https://app.example.com"
    assert settings.max_surfaces == 12
    assert settings.vision is True


def test_init_refuses_to_overwrite_without_being_told_to(tmp_path: Path) -> None:
    cli.main(["init", str(tmp_path)])
    (tmp_path / config.CONFIG_NAME).write_text("# mine\n", encoding="utf-8")

    assert cli.main(["init", str(tmp_path)]) == 1
    assert (tmp_path / config.CONFIG_NAME).read_text(encoding="utf-8") == "# mine\n"
    assert cli.main(["init", str(tmp_path), "--force"]) == 0


def test_paths_resolve_against_the_file_not_the_shell(tmp_path: Path) -> None:
    """The same configuration must mean the same thing from any directory."""
    path = write_config(tmp_path, '[target]\nout = "runs/x"\n[auth]\ncredentials = ".auth/c.json"\n')

    settings = config.load(path)

    assert settings.out == tmp_path / "runs/x"
    assert settings.credentials == tmp_path / ".auth/c.json"


def test_a_missing_file_is_not_an_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    settings = config.load()

    assert settings.source is None
    assert settings.url is None
    assert "no configuration file" in settings.describe()


def test_the_file_is_found_from_a_subdirectory(tmp_path: Path, monkeypatch) -> None:
    write_config(tmp_path, '[target]\nurl = "https://app.example.com"\n')
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    assert config.load().url == "https://app.example.com"


def test_a_malformed_file_names_itself_rather_than_failing_obscurely(tmp_path: Path) -> None:
    path = write_config(tmp_path, "[target\nurl =")

    with pytest.raises(SystemExit) as raised:
        config.load(path)

    assert str(path) in str(raised.value)


def _captured(monkeypatch) -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.setattr(cli, "sweep_main", lambda argv: calls.append(list(argv)) or 0)
    return calls


def test_settings_become_arguments(tmp_path: Path, monkeypatch) -> None:
    path = write_config(tmp_path, (
        '[target]\nurl = "https://app.example.com"\nout = "runs/x"\nmax_surfaces = 4\n'
        '[models]\nvision = false\npropose_scenarios = true\n'
    ))
    calls = _captured(monkeypatch)

    assert cli.main(["sweep", "--config", str(path), "--quiet"]) == 0

    argv = calls[0]
    assert argv[0] == "https://app.example.com"
    assert argv[argv.index("--max-surfaces") + 1] == "4"
    assert "--no-vision" in argv and "--propose-scenarios" in argv


def test_a_flag_beats_the_file(tmp_path: Path, monkeypatch) -> None:
    """The reason to type a flag is to override what is written down."""
    path = write_config(tmp_path, '[target]\nurl = "https://app.example.com"\nout = "runs/x"\n')
    calls = _captured(monkeypatch)

    cli.main(["sweep", "--config", str(path), "--quiet", "--out", "runs/override"])

    argv = calls[0]
    assert argv.count("--out") == 1
    assert argv[argv.index("--out") + 1] == "runs/override"


def test_a_flag_value_is_never_mistaken_for_the_target(tmp_path: Path, monkeypatch) -> None:
    """argparse binds an unknown flag's value to a positional; `runs/x` is not a URL."""
    path = write_config(tmp_path, '[target]\nurl = "https://app.example.com"\n')
    calls = _captured(monkeypatch)

    cli.main(["sweep", "--config", str(path), "--quiet", "--out", "runs/x", "--max-surfaces", "2"])

    argv = calls[0]
    assert argv[0] == "https://app.example.com"
    assert argv[argv.index("--out") + 1] == "runs/x"


def test_a_leading_url_overrides_the_configured_target(tmp_path: Path, monkeypatch) -> None:
    path = write_config(tmp_path, '[target]\nurl = "https://configured.example"\n')
    calls = _captured(monkeypatch)

    cli.main(["sweep", "https://typed.example", "--config", str(path), "--quiet"])

    assert calls[0][0] == "https://typed.example"


def test_no_target_anywhere_says_what_to_do_about_it(tmp_path: Path, monkeypatch) -> None:
    path = write_config(tmp_path, "[target]\n")
    monkeypatch.setattr(cli, "sweep_main", lambda argv: 0)

    with pytest.raises(SystemExit) as raised:
        cli.main(["sweep", "--config", str(path)])

    assert "parallax init" in str(raised.value)


def test_an_exported_variable_is_never_overwritten_by_the_file(tmp_path: Path, monkeypatch) -> None:
    """Exporting one is a deliberate act; the file is a default."""
    path = write_config(tmp_path, (
        '[target]\nurl = "https://app.example.com"\n[models]\ngoogle_cloud_project = "from-file"\n'
    ))
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "from-environment")
    _captured(monkeypatch)

    cli.main(["sweep", "--config", str(path), "--quiet"])

    import os

    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "from-environment"


def test_the_file_supplies_the_variable_when_nothing_else_has(tmp_path: Path, monkeypatch) -> None:
    path = write_config(tmp_path, (
        '[target]\nurl = "https://app.example.com"\n[models]\ngoogle_cloud_project = "from-file"\n'
    ))
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    _captured(monkeypatch)

    cli.main(["sweep", "--config", str(path), "--quiet"])

    import os

    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "from-file"
