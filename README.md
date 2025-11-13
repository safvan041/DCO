✅ DCO – Dynamic Config Orchestrator

Zero-hardcoded configs. Automatic merging. Schema-driven validation. Secrets integration. Developer-friendly.

DCO is a Python package designed to eliminate hardcoded configuration from backend applications by providing:

Dynamic config loading

Automatic merging across environments

Env var + .env + YAML/JSON support

Secrets provider abstraction (AWS, Vault, custom)

JSON Schema generation

Config scaffolding

Schema diffing (detect breaking changes!)

CLI for validation, dumping, watching

Full Pydantic model integration

CI-friendly commands for teams

Stop maintaining messy settings.py files, duplicated YAMLs, and inconsistent environment config.
DCO centralizes everything with a clean, predictable, and IDE-friendly workflow.

✨ Features
🚀 Dynamic Config Loading

Automatically merges:

config.yaml

config.<env>.yaml

.env

environment variables (APP__DB__HOST)

secret provider values

Pydantic defaults

🔄 Hot Reload (dev only)

Watch config directory and reload settings on file change.

🔐 Secrets Providers

Optional built-in integrations:

AWS Secrets Manager

AWS SSM

HashiCorp Vault

or implement your own with a simple interface.

🛡 JSON Schema + CI Validation

Generate schema from your Pydantic model.
Validate real config files or the merged effective config.

🛠 CLI Tools

dco dump – print merged config

dco validate – validate merged config

dco validate-file – validate a specific YAML/JSON file

dco scaffold – auto-generate starter config file

dco schema – export JSON/YAML schema

dco schema-diff – detect breaking config changes

dco watch – file watcher for dev reloading

dco docs – generate Markdown docs from schema

🔧 Zero Hardcoding

No more:

hardcoded hosts

hardcoded ports

duplicated YAMLs

manual “dev/stage/prod” handling

📦 Installation
Stable release (after publishing to PyPI):
pip install dco

Latest GitHub version:
pip install "git+https://github.com/safvan041/DCO.git#egg=dco"

🚀 Quick Start
1. Define your settings using Pydantic
# settings.py
from pydantic import BaseModel
from dco import ConfigLoader

class DatabaseSettings(BaseModel):
    host: str
    port: int = 5432

class AppSettings(BaseModel):
    debug: bool = False
    db: DatabaseSettings

2. Create a config directory
config/
    config.yaml
    config.development.yaml
    .env

Example config.yaml:
debug: false
db:
  host: "localhost"
  port: 5432

Example .env:
DB__PASSWORD=supersecret

3. Load configuration in your app
from settings import AppSettings
from dco import ConfigLoader

loader = ConfigLoader(AppSettings, config_dir="config")
settings = loader.load()

print(settings.debug)
print(settings.db.host)

4. Switch environments
export DCO_ENV=development
python app.py

🧰 CLI Usage
Dump merged config
dco --config-dir=config dump settings:AppSettings

Validate merged config
dco --config-dir=config validate settings:AppSettings

Validate a single file
dco validate-file settings:AppSettings config/config.yaml

Generate JSON Schema
dco schema settings:AppSettings --out app.schema.json

Generate YAML Schema
dco schema settings:AppSettings --format yaml --out app.schema.yaml

Auto-generate config scaffold
dco scaffold settings:AppSettings --format yaml --out example.config.yaml

Detect breaking schema changes
dco schema-diff old.schema.json new.schema.json

Generate Markdown docs
dco docs settings:AppSettings --out docs/app_settings.md

Watch config for live reload (dev)
dco watch settings:AppSettings

🔐 Secrets Providers

Configure via:

from dco.secrets import AwsSecretsManagerProvider

loader = ConfigLoader(
    AppSettings,
    secrets_provider=AwsSecretsManagerProvider(prefix="myapp/")
)
settings = loader.load()


Or build your own provider:

from dco.secrets import SecretProvider

class MyProvider(SecretProvider):
    def get_secret(self, path: str) -> str:
        return "value"

🧪 Testing
pytest -q


Or run example integration test:

PYTHONPATH=src python examples/simple_app/test_integration.py

📄 Configuration File Rules

Environment-specific files override base config

.env overrides YAML

Env vars override .env

Secrets override everything

Model defaults apply if key missing

Type validation enforced by Pydantic

Schema ensures structural correctness

📚 Tips for Real Projects

Commit your schema (JSON) to detect breaking changes in CI

Use schema-diff in pull requests

Use dco scaffold to bootstrap new services

Use Env vars like DB__HOST to override nested settings

Use watch during development for auto-reload

Keep .env out of production; use secrets provider instead

🤝 Contributing

Pull requests welcome!
Please run:

ruff check .
black .
pytest -q


before submitting.
