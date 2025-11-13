# examples/simple_app/test_integration.py
import os
import sys

# ensure repo root is importable
sys.path.insert(0, os.getcwd())

from dco.core import ConfigLoader
from dco.secrets import AWSSecretsProvider, CachedProvider
from dco.utils import model_to_mapping
from examples.simple_app.app import AppSettings


# Fake secrets client (simulate AWS Secrets Manager)
class FakeSecretsClient:
    def get_secret_value(self, SecretId):
        return {"SecretString": '{"db":{"host":"aws-secret-host","port":7770}}'}


provider = CachedProvider(
    AWSSecretsProvider(
        FakeSecretsClient(), app="myapp", secret_name_template="/{app}/{env}/secrets"
    ),
    ttl=60,
)
loader = ConfigLoader(
    AppSettings, config_dir="examples/simple_app/config", secrets_provider=provider
)
cfg = loader.load()
print(model_to_mapping(cfg))
