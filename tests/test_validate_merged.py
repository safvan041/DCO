# tests/test_validate_merged.py
from pathlib import Path

from dco.cli import main as dco_main


def write_file(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


def test_validate_merged_success(tmp_path, monkeypatch):
    # prepare config dir
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    # base config contains db.host so merged config is valid
    write_file(cfg / "config.yaml", "debug: false\n db:\n  host: host1\n  port: 1\n")
    write_file(cfg / "config.development.yaml", "db:\n  port: 2\n  username: dev\n")
    write_file(cfg / ".env", "APP_DB__PASSWORD=secret\n")
    # ensure env override doesn't break
    monkeypatch.setenv("DCO_ENV", "development")
    # call CLI main for validate-merged, expect no SystemExit (success)
    argv = [
        "--config-dir",
        str(cfg),
        "--lenient-yaml",
        "validate-merged",
        "examples.simple_app.app:AppSettings",
    ]
    # Should return normally (no SystemExit)
    dco_main(argv)


def test_validate_merged_failure_missing_required(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    # missing db.host in all sources -> should fail
    write_file(cfg / "config.yaml", "debug: false\n db:\n  port: 1\n")
    monkeypatch.setenv("DCO_ENV", "development")
    argv = [
        "--config-dir",
        str(cfg),
        "validate-merged",
        "examples.simple_app.app:AppSettings",
    ]
    try:
        dco_main(argv)
        # if we reach here then validation didn't fail — that's an error
        assert False, "validate-merged succeeded but should have failed"
    except SystemExit as e:
        # our validate_file_command uses exit code 2 on validation failure
        assert e.code == 2
