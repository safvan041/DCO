# tests/test_core.py
from pathlib import Path

from pydantic import BaseModel

from dco.core import ConfigLoader, deep_merge


class AppSettings(BaseModel):
    debug: bool = False
    environment: str = "development"
    db: dict


def write_file(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


def test_merge_and_load_files(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    # defaults
    write_file(cfg_dir / "config.yaml", "debug: false\ndb:\n  host: host1\n  port: 1\n")
    # env-specific (already fine)
    write_file(cfg_dir / "config.development.yaml", "db:\n  port: 2\n  user: dev\n")
    # .env
    write_file(cfg_dir / ".env", "APP_DB__PASSWORD=secret\nSIMPLE_VAL=42\n")
    # env var override
    monkeypatch.setenv("APP_DB__HOST", "host-override")
    loader = ConfigLoader(AppSettings, config_dir=cfg_dir, load_dotenv=True)
    settings = loader.load()
    assert settings.db["host"] == "host-override"
    assert settings.db["port"] == 2
    assert settings.db["user"] == "dev"
    assert settings.db["password"] == "secret"


def test_deep_merge_simple():
    a = {"x": 1, "y": {"a": 1}}
    b = {"y": {"b": 2}, "z": 3}
    out = deep_merge(a, b)
    assert out["x"] == 1
    assert out["y"]["a"] == 1 and out["y"]["b"] == 2
    assert out["z"] == 3
