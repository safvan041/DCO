# src/dco/core.py
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Type

import yaml  # type: ignore
from dotenv import dotenv_values
from pydantic import BaseModel, ValidationError
from yaml.scanner import ScannerError  # type: ignore[import-untyped]

from .secrets import NoopSecretsProvider, SecretsProvider

DEFAULT_ENV_KEY = "DCO_ENV"
DEFAULT_PREFIX = "APP_"


class MergeError(Exception):
    pass


def deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge b into a (b takes precedence) and return new dict.
    Handles nested dict merging.
    """
    out = dict(a or {})
    for k, v in (b or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _envvar_to_nested(
    key: str, value: str, prefix: str = DEFAULT_PREFIX
) -> Dict[str, Any]:
    """
    Translate e.g. APP_DB__HOST= -> {'db': {'host': value}}
    Double underscore separates nesting, single underscore preserved in key names.
    """
    assert key.startswith(prefix)
    key_path = key[len(prefix) :].split("__")
    # normalize to lowercase keys
    key_path = [p.lower() for p in key_path if p != ""]
    cur: Dict[str, Any] = {}
    node = cur
    for part in key_path[:-1]:
        node[part] = {}
        node = node[part]
    node[key_path[-1]] = value
    return cur


def validate_model(model_cls: Type[BaseModel], payload: Dict[str, Any]) -> BaseModel:
    """
    Validate the payload against model_cls, supporting both Pydantic v2+ and v1.
    Returns an instance of model_cls or raises pydantic.ValidationError.
    """
    # Prefer v2 API if available
    if hasattr(model_cls, "model_validate"):
        # Pydantic v2: model_validate may raise pydantic.ValidationError
        return model_cls.model_validate(payload)  # type: ignore[attr-defined]
    # Fall back to v1 API
    if hasattr(model_cls, "parse_obj"):
        return model_cls.parse_obj(payload)  # type: ignore[attr-defined]
    raise RuntimeError(
        "Provided model class does not expose a known Pydantic validation API."
    )


def _parse_yaml(text: str, lenient: bool = False) -> Any:
    """
    Parse YAML text. If `lenient` is True and a ScannerError occurs,
    attempt a conservative sanitization (strip a single leading space
    from lines) and re-parse. Returns the parsed object or raises the
    original ScannerError on failure.
    """
    try:
        return yaml.safe_load(text)
    except ScannerError as e:
        if not lenient:
            raise
        # Log a warning that we are attempting lenient parsing
        logging.warning(
            "YAML parsing failed; attempting lenient sanitization: %s", str(e)
        )
        sanitized = "\n".join(
            [line[1:] if line.startswith(" ") else line for line in text.splitlines()]
        )
        # Try one more time; if this fails let the ScannerError propagate
        return yaml.safe_load(sanitized)


class ConfigLoader:
    """
    ConfigLoader handles layered config loading and validation.

    Precedence (low -> high):
      - config.yaml / config.json
      - config.{env}.yaml / config.{env}.json
      - .env
      - secrets manager
      - environment variables (prefixed)
      - programmatic overrides (passed to load())

    Usage:
        loader = ConfigLoader(AppSettings, config_dir="config")
        settings = loader.load()
    """

    def __init__(
        self,
        model_cls: Type[BaseModel],
        config_dir: str | Path = "config",
        env_key: str = DEFAULT_ENV_KEY,
        secrets_provider: Optional[SecretsProvider] = None,
        load_dotenv: bool = True,
        envvar_prefix: str = DEFAULT_PREFIX,
        lenient_yaml: bool = False,
    ):
        self.model_cls = model_cls
        self.config_dir = Path(config_dir)
        self.env_key = env_key
        self.env = os.getenv(env_key, "development")
        self.secrets_provider = secrets_provider or NoopSecretsProvider()
        self.load_dotenv = load_dotenv
        self.envvar_prefix = envvar_prefix
        self.lenient_yaml = bool(lenient_yaml)

    # ---------- source readers ----------
    def _read_files(self) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        candidate_files = [
            self.config_dir / "config.yaml",
            self.config_dir / "config.yml",
            self.config_dir / "config.json",
            self.config_dir / f"config.{self.env}.yaml",
            self.config_dir / f"config.{self.env}.yml",
            self.config_dir / f"config.{self.env}.json",
        ]
        for p in candidate_files:
            if not p.exists():
                continue
            try:
                text = p.read_text(encoding="utf-8")
                if p.suffix in (".yaml", ".yml"):
                    try:
                        data = _parse_yaml(text, lenient=self.lenient_yaml) or {}
                    except ScannerError as e:
                        # Preserve the original error semantics for callers
                        # — raise a MergeError which will be handled by the
                        # caller/CLI. Include the scanner message for clarity.
                        raise MergeError(f"Failed reading {p}: {e}") from e
                elif p.suffix == ".json":
                    data = json.loads(text) or {}
                else:
                    data = {}
                if not isinstance(data, dict):
                    raise MergeError(
                        f"Config file {p} must contain a mapping / dict at top level."
                    )
                merged = deep_merge(merged, data)
            except Exception as e:
                raise MergeError(f"Failed reading {p}: {e}") from e
        return merged

    def _read_dotenv(self) -> Dict[str, Any]:
        if not self.load_dotenv:
            return {}
        env_path = self.config_dir / ".env"
        if not env_path.exists():
            return {}
        try:
            parsed = dict(dotenv_values(env_path))
            out: Dict[str, Any] = {}
            for k, v in parsed.items():
                if k is None:
                    continue
                if k.startswith(self.envvar_prefix):
                    nested = _envvar_to_nested(k, v, prefix=self.envvar_prefix)
                    out = deep_merge(out, nested)
                elif "." in k:
                    # allow dot notation in .env: DB.HOST= -> {'db': {'host': v}}
                    parts = [p.lower() for p in k.split(".")]
                    cur = out
                    for part in parts[:-1]:
                        cur = cur.setdefault(part, {})
                    cur[parts[-1]] = v
                else:
                    out[k.lower()] = v
            return out
        except Exception:
            return {}

    def _read_secrets(self) -> Dict[str, Any]:
        try:
            s = self.secrets_provider.get_secrets(self.env) or {}
            if not isinstance(s, dict):
                return {}
            return s
        except Exception:
            return {}

    def _read_envvars(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        prefix = self.envvar_prefix
        for k, v in os.environ.items():
            if not k.startswith(prefix):
                continue
            try:
                nested = _envvar_to_nested(k, v, prefix=prefix)
                out = deep_merge(out, nested)
            except Exception:
                # skip malformed env var names
                continue
        return out

    # ---------- load & validate ----------
    def load(self, overrides: Optional[Dict[str, Any]] = None) -> BaseModel:
        """
        Load merged config and return an instance of model_cls (validated).
        Overrides is highest precedence.
        """
        overrides = overrides or {}

        files = self._read_files()
        dotenv = self._read_dotenv()
        secrets = self._read_secrets()
        envvars = self._read_envvars()

        # merge order: files <- dotenv <- secrets <- envvars <- overrides
        merged: Dict[str, Any] = {}
        for layer in (files, dotenv, secrets, envvars, overrides):
            merged = deep_merge(merged, layer)

        try:
            cfg = validate_model(self.model_cls, merged)
        except ValidationError as e:
            # re-raise for caller/CI to surface nicely
            raise e

        return cfg

    # ---------- convenience cached getter ----------
    def get_cached_loader(self):
        """
        Return a cached zero-arg loader function: calling it returns the validated settings instance.
        Useful for modules that want a singleton settings getter.
        """

        @lru_cache()
        def _get():
            return self.load()

        return _get
