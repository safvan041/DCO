# scripts/test_secrets_quick.py
import time
from types import SimpleNamespace

from dco.secrets import (
    AWSSecretsProvider,
    CachedProvider,
    SSMParameterProvider,
    VaultProvider,
)


# Fake boto3 secretsmanager client returning JSON
class FakeSecretsClient:
    def get_secret_value(self, SecretId):
        return {"SecretString": '{"db":{"host":"h.local","port":5432}}'}


aws = AWSSecretsProvider(
    FakeSecretsClient(), secret_name_template="/{app}/{env}/secrets", app="myapp"
)
print("AWSSecretsProvider:", aws.get_secrets("dev"))


# Fake SSM client
class FakeSSMClient:
    def get_parameters_by_path(self, **kwargs):
        return {
            "Parameters": [
                {"Name": "/myapp/dev/db/host", "Value": "h.local"},
                {"Name": "/myapp/dev/db/port", "Value": "5432"},
            ],
            "NextToken": None,
        }


ssm = SSMParameterProvider(FakeSSMClient(), path_template="/{app}/{env}/", app="myapp")
print("SSMParameterProvider:", ssm.get_secrets("dev"))


# Fake Vault client for KV v2
class FakeVault:
    def __init__(self):
        self.secrets = SimpleNamespace(
            kv=SimpleNamespace(
                v2=SimpleNamespace(
                    read_secret_version=lambda path, mount_point: {
                        "data": {"data": {"k": "v"}}
                    }
                )
            )
        )


vault = VaultProvider(
    FakeVault(), mount_template="secret/myapp/{env}", app="myapp", versioned=True
)
print("VaultProvider:", vault.get_secrets("dev"))

# Test caching
cached = CachedProvider(aws, ttl=1)
print("cached1:", cached.get_secrets("dev"))
time.sleep(0.6)
print("cached2 (should be cached):", cached.get_secrets("dev"))
time.sleep(1.1)
print("cached3 (expired -> fresh):", cached.get_secrets("dev"))
