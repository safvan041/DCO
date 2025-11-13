
# DCO — Dynamic Config Orchestrator

DCO is a small, opinionated toolbox to load, validate and document typed configuration for Python services.

This manual explains how to install and use DCO locally and in CI, describes the CLI commands, configuration layout, and best practices for secure use.

**Quick goals:**
- **Typed config** using Pydantic models
- **Layered loading** (files, environment, .env, secrets, env vars)
- **Schema export, scaffold & docs** generation from Pydantic models
- **Small CLI** for validation, inspection and developer tooling

**Supported Python versions:** 3.10, 3.11, 3.12

**Table of contents**
- Installation
- Configuration layout
- CLI reference and examples
- Generating docs & schema
- CI and packaging
- Security & secrets handling
- Contributing

**Installation**

- From source (developer):

```bash
git clone <repo-url>
cd DCO
pip install -e .
```

- As a wheel (release):

```bash
pip install dco
```

Note: optional features (AWS/Vault integrations) are provided by optional dependencies — see `pyproject.toml` for extras groups if present.

**Configuration layout**

DCO expects a `config` directory (or a path supplied via `--config-dir`) with layered files. Example layout:

- `config/config.yaml` — base config
- `config/config.development.yaml` — environment override
- `config/.env` — dotenv file (APP_ prefixed envs are parsed to nested config)

Environment variable precedence (high -> low):
- explicit program overrides (when using API)
- environment variables (prefixed, e.g. `APP_DB__HOST`)
- secrets provider
- `.env` file
- `config.{env}.yaml`
- `config.yaml`

Keys using double-underscore map to nested dictionaries (e.g. `APP_DB__HOST=host` -> `{"db": {"host": "host"}}`).

**CLI Reference**

Run `dco --help` for a quick list. Below are the primary commands with examples.

- `dco validate <model>`
	- Validate the merged configuration (files + .env + env vars) against a Pydantic model.
	- Example:

```bash
dco --config-dir examples/simple_app/config validate examples.simple_app.app:AppSettings
```

- `dco dump <model>`
	- Print merged configuration as JSON.

```bash
dco --config-dir examples/simple_app/config dump examples.simple_app.app:AppSettings
```

- `dco schema <model> [--format json|yaml]`
	- Export JSON Schema for a model.

```bash
dco schema examples.simple_app.app:AppSettings --format json > schema.json
```

- `dco scaffold <model> [--format json|yaml] [--out FILE]`
	- Generate a config template/scaffold from the model schema.

```bash
dco scaffold examples.simple_app.app:AppSettings --format yaml --out config.template.yaml
```

- `dco validate-file <model> <config_file>`
	- Validate an explicit JSON/YAML file against the model schema using `jsonschema`.

```bash
dco validate-file examples.simple_app.app:AppSettings examples/simple_app/config/config.yaml
```

- `dco validate-merged <model>`
	- Convenience command: load merged config using loader semantics and validate the resulting runtime configuration against the model schema.

```bash
dco --config-dir examples.simple_app/config validate-merged examples.simple_app.app:AppSettings
```

- `dco schema-diff <old_schema> <new_schema>`
	- Compare two schema files and report breaking/non-breaking changes (useful in PR gating).

```bash
dco schema-diff old_schema.json new_schema.json
```

- `dco docs <model> [--out FILE] [--title TITLE]`
	- Render Markdown documentation derived from model JSON Schema.

```bash
PYTHONPATH=src dco docs examples.simple_app.app:AppSettings --out docs/app_settings.md --title "AppSettings Configuration"
```

- `dco watch <model>`
	- Watch configuration directory and print reloads (development only). Secrets are redacted in watch output.

```bash
dco --config-dir examples/simple_app/config watch examples.simple_app.app:AppSettings
```

**Notes on model reference**

Models are referenced as `module.path:ModelName`, for example `examples.simple_app.app:AppSettings`. You may also provide a filesystem path like `./examples/simple_app/app.py:AppSettings`.

**Examples**

1. Scaffold + edit + validate:

```bash
dco scaffold examples.simple_app.app:AppSettings --format yaml > config.template.yaml
# edit config.template.yaml to fill required fields
dco validate-file examples.simple_app.app:AppSettings config.template.yaml
```

2. Generate docs in CI:

```bash
PYTHONPATH=src dco docs examples.simple_app.app:AppSettings --out docs/app_settings.md --title "AppSettings"
```

**CI & Packaging (recommendations)**

- Build wheel and smoke-test in CI before publishing. Example sequence in CI:

```bash
python -m build --wheel --outdir dist
pip install dist/*.whl
python -c "import dco; print(dco.__version__)"
```

- Use `dco schema-diff` in a gating job to prevent breaking schema changes on PRs.

**Security & Secrets Handling**

- Do NOT print secrets or write them into generated docs. Use `filter_secrets_for_logging()` to redact secrets before any printing of config content. Example:

```py
from dco.utils import filter_secrets_for_logging
mapping = model_to_mapping(settings)
print(filter_secrets_for_logging(mapping))
```

- Never commit real secret values to the repo. Use CI secret stores for deployment credentials.

**Packaging metadata and extras**

- Optional dependencies (e.g., AWS/Vault support) are declared in `pyproject.toml` or `setup.cfg` as extras. Install with:

```bash
pip install dco[aws]
```

**Extending & contribution**

- Tests: run `pytest` to verify functionality. New features should include unit tests and CLI integration tests.
- Linting & hooks: the repo uses `ruff`, `black`, `isort`, and `mypy`; pre-commit hooks will run these checks.

**Troubleshooting**

- "Module found twice" mypy error when running tests locally usually means `examples` must be a package — ensure `examples/__init__.py` exists.
- If `jsonschema` yields missing stubs for mypy, install `types-PyYAML` or run `mypy --install-types --non-interactive` in developer environments.

**Support and maintenance**

- For packaging and releases: ensure `pyproject.toml` contains correct metadata (version, classifiers, long_description) and test building a wheel in CI.
- Add schema gating and packaging jobs in CI to keep the project safe for consumers.

---

If you want, I can also:
- add an Examples section with a step-by-step guide for `examples/simple_app`,
- create a `CONTRIBUTING.md` with commit and release workflows, or
- add a `Makefile` or `scripts/` helpers to automate docs and packaging tasks.

Happy to proceed with any of those next steps.
