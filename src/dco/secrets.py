# src/dco/secrets.py
"""
Secrets provider abstractions.

Provides:
 - SecretsProvider (interface)
 - NoopSecretsProvider
 - AWSSecretsProvider (AWS Secrets Manager)
 - SSMParameterProvider (AWS SSM Parameter Store)
 - VaultProvider (HashiCorp Vault) - optional, requires `hvac`

All providers implement:
    get_secrets(env: str) -> dict | None

Returned dict MUST be a mapping (nested dicts allowed) or None/{} on failure.
This module includes a tiny in-memory TTL cache to avoid repeated network calls.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SecretsProvider:
    def get_secrets(self, env: str) -> Optional[Dict[str, Any]]:
        """Return structured secrets (mapping) for the given env or None/{} on failure."""
        raise NotImplementedError


class NoopSecretsProvider(SecretsProvider):
    def get_secrets(self, env: str) -> Optional[Dict[str, Any]]:
        return {}


# ------------------------ caching wrapper ------------------------
class CachedProvider(SecretsProvider):
    """
    Wraps another SecretsProvider and caches the result for `ttl` seconds.
    If ttl == 0, effectively no caching.
    """

    def __init__(self, provider: SecretsProvider, ttl: int = 300):
        self.provider = provider
        self.ttl = int(ttl)
        self._cache: Dict[str, tuple[float, Optional[Dict[str, Any]]]] = {}

    def get_secrets(self, env: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        entry = self._cache.get(env)
        if entry:
            ts, value = entry
            if self.ttl == 0 or (now - ts) < self.ttl:
                return value
        try:
            value = self.provider.get_secrets(env)
            # ensure mapping or empty dict
            if not isinstance(value, dict):
                value = {}
        except Exception as e:
            logger.exception("Secrets provider failed: %s", e)
            value = {}
        self._cache[env] = (now, value)
        return value


# ------------------------ AWS Secrets Manager provider ------------------------
class AWSSecretsProvider(SecretsProvider):
    """
    Uses boto3 Secrets Manager client: client = boto3.client('secretsmanager')

    secret_name_template: a format string that receives {app} and {env}, e.g. "/{app}/{env}/secrets"
    app: application name portion used by the template.
    parse_json: if True, attempts to parse SecretString as JSON and return dict
    """

    def __init__(
        self,
        client,
        secret_name_template: str = "/{app}/{env}/secrets",
        app: str = "app",
        parse_json: bool = True,
    ):
        self.client = client
        self.template = secret_name_template
        self.app = app
        self.parse_json = bool(parse_json)

    def get_secrets(self, env: str) -> Optional[Dict[str, Any]]:
        name = self.template.format(app=self.app, env=env)
        try:
            resp = self.client.get_secret_value(SecretId=name)
            s = resp.get("SecretString")
            if not s:
                # Could be binary secrets; ignore for now
                return {}
            if self.parse_json:
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, dict):
                        return parsed
                    # if not dict, put it under 'value'
                    return {"value": parsed}
                except Exception:
                    # not JSON - return raw string under default key
                    return {"value": s}
            else:
                return {"value": s}
        except Exception as e:
            logger.debug("AWSSecretsProvider failed to fetch %s: %s", name, e)
            return {}


# ------------------------ AWS SSM Parameter Store provider ------------------------
class SSMParameterProvider(SecretsProvider):
    """
    Uses boto3 SSM client. Fetches parameters under a path and returns them as nested mapping.
    Example:
      - path_template="/{app}/{env}/"
      - stored params: "/myapp/dev/db/host" -> "db/host" -> nested mapping {'db': {'host': value}}
    Options:
      - with_decryption: whether to request decryption for SecureString
    """

    def __init__(
        self,
        client,
        path_template: str = "/{app}/{env}/",
        app: str = "app",
        with_decryption: bool = True,
    ):
        self.client = client
        self.template = path_template
        self.app = app
        self.with_decryption = bool(with_decryption)

    def _insert_nested(self, out: Dict[str, Any], key_path: list[str], value: Any):
        cur = out
        for p in key_path[:-1]:
            cur = cur.setdefault(p, {})
        cur[key_path[-1]] = value

    def get_secrets(self, env: str) -> Optional[Dict[str, Any]]:
        path = self.template.format(app=self.app, env=env)
        # ensure path ends with '/'
        if not path.endswith("/"):
            path = path + "/"
        next_token = None
        out: Dict[str, Any] = {}
        try:
            while True:
                kwargs = {
                    "Path": path,
                    "Recursive": True,
                    "WithDecryption": self.with_decryption,
                    "MaxResults": 10,
                }
                if next_token:
                    kwargs["NextToken"] = next_token
                resp = self.client.get_parameters_by_path(**kwargs)
                params = resp.get("Parameters", [])
                for p in params:
                    name = p.get("Name", "")
                    # remove path prefix and leading slash
                    rel = name[len(path) :].lstrip("/")
                    # split by '/' to nested keys
                    parts = [part for part in rel.split("/") if part != ""]
                    if not parts:
                        continue
                    self._insert_nested(out, parts, p.get("Value"))
                next_token = resp.get("NextToken")
                if not next_token:
                    break
            return out
        except Exception as e:
            logger.debug("SSMParameterProvider failed for path %s: %s", path, e)
            return {}


# ------------------------ Vault provider (optional hvac dependency) ------------------------
class VaultProvider(SecretsProvider):
    """
    Simple HashiCorp Vault provider using hvac.Client.
    - client: hvac.Client instance
    - mount_template: path template to read secret (format accepts {app} and {env})
    - versioned: if True uses KV v2 read API (requires mounted path like "secret")
    """

    def __init__(
        self,
        client,
        mount_template: str = "secret/{app}/{env}",
        app: str = "app",
        versioned: bool = True,
    ):
        self.client = client
        self.template = mount_template
        self.app = app
        self.versioned = bool(versioned)

    def get_secrets(self, env: str) -> Optional[Dict[str, Any]]:
        name = self.template.format(app=self.app, env=env)
        try:
            if self.versioned:
                # hvac kv v2 read
                # client.secrets.kv.v2.read_secret_version(path=relpath, mount_point=mount_point)
                # Split mount and rel path if template contains '/'
                parts = name.split("/", 1)
                if len(parts) == 1:
                    mount_point, rel = parts[0], ""
                else:
                    mount_point, rel = parts[0], parts[1]
                resp = self.client.secrets.kv.v2.read_secret_version(
                    path=rel, mount_point=mount_point
                )
                data = resp.get("data", {}).get("data", {})
                return data or {}
            else:
                # kv v1 - direct read
                resp = self.client.read(name)
                data = resp.get("data", {})
                return data or {}
        except Exception as e:
            logger.debug("VaultProvider failed to read %s: %s", name, e)
            return {}
