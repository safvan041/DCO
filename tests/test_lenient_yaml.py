# tests/test_lenient_yaml.py
from pathlib import Path

import pytest

from dco.cli import _load_model_from_path
from dco.core import ConfigLoader, MergeError

AppSettings = _load_model_from_path("examples.simple_app.app:AppSettings")


def write_file(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


def test_valid_yaml_parses(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    write_file(cfg / "config.yaml", "debug: false\ndb:\n  host: host1\n  port: 1\n")
    loader = ConfigLoader(AppSettings, config_dir=str(cfg))
    settings = loader.load()
    assert settings.db.host == "host1"


def test_malformed_yaml_parses_when_lenient(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    # malformed: leading space before top-level 'db' key
    write_file(cfg / "config.yaml", "debug: false\n db:\n  host: host1\n  port: 1\n")
    loader = ConfigLoader(AppSettings, config_dir=str(cfg), lenient_yaml=True)
    settings = loader.load()
    assert settings.db.host == "host1"


def test_malformed_yaml_fails_when_not_lenient(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    write_file(cfg / "config.yaml", "debug: false\n db:\n  host: host1\n  port: 1\n")
    loader = ConfigLoader(AppSettings, config_dir=str(cfg), lenient_yaml=False)
    with pytest.raises(MergeError):
        loader.load()
