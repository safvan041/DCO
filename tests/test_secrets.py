# tests/test_secrets.py
from types import SimpleNamespace

from dco.secrets import (
    AWSSecretsProvider,
    CachedProvider,
    NoopSecretsProvider,
    SSMParameterProvider,
    VaultProvider,
)


def test_noop_provider():
    p = NoopSecretsProvider()
    assert p.get_secrets("dev") == {}


def test_cached_provider(monkeypatch):
    class Dummy(SimpleNamespace):
        def get_secrets(self, env):
            return {"x": env}

    dummy = Dummy()
    cp = CachedProvider(dummy, ttl=1)
    v1 = cp.get_secrets("dev")
    v2 = cp.get_secrets("dev")
    assert v1 is v2 or v1 == v2  # same content; cached
    import time

    time.sleep(1.1)
    v3 = cp.get_secrets("dev")
    assert v3 == {"x": "dev"}


def test_aws_provider_parse_json(monkeypatch):
    # fake boto3 client that returns JSON string
    class FakeClient:
        def get_secret_value(self, SecretId):
            return {"SecretString": '{"db": {"host": "h", "port": 1}}'}

    p = AWSSecretsProvider(
        FakeClient(),
        secret_name_template="/{app}/{env}/secrets",
        app="myapp",
        parse_json=True,
    )
    out = p.get_secrets("dev")
    assert out["db"]["host"] == "h"
    assert out["db"]["port"] == 1


def test_aws_provider_non_json(monkeypatch):
    class FakeClient:
        def get_secret_value(self, SecretId):
            return {"SecretString": "plain-text"}

    p = AWSSecretsProvider(FakeClient(), parse_json=True)
    out = p.get_secrets("dev")
    assert out.get("value") == "plain-text"


def test_ssm_parameter_provider(monkeypatch):
    # fake client returning a page of params
    class FakeClient:
        def __init__(self):
            self.calls = 0

        def get_parameters_by_path(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {
                    "Parameters": [
                        {"Name": "/myapp/dev/db/host", "Value": "h"},
                        {"Name": "/myapp/dev/db/port", "Value": "1234"},
                    ],
                    "NextToken": None,
                }
            return {"Parameters": []}

    p = SSMParameterProvider(FakeClient(), path_template="/{app}/{env}/", app="myapp")
    out = p.get_secrets("dev")
    assert out["db"]["host"] == "h"
    assert out["db"]["port"] == "1234"


def test_vault_provider(monkeypatch):
    # Fake hvac client with minimal interface; simulate kv v2 read response
    class FakeKVv2:
        def read_secret_version(self, path, mount_point):
            return {"data": {"data": {"k": "v"}}}

    class FakeClient:
        def __init__(self):
            self.secrets = SimpleNamespace(
                kv=SimpleNamespace(
                    v2=SimpleNamespace(
                        read_secret_version=lambda **k: {"data": {"data": {"k": "v"}}}
                    )
                )
            )

    client = FakeClient()
    p = VaultProvider(
        client, mount_template="secret/myapp/{env}", app="myapp", versioned=True
    )
    out = p.get_secrets("dev")
    assert out.get("k") == "v"
