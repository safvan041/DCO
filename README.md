# DCO — Dynamic Config Orchestrator

Opinionated, typed, layered configuration loader for Python services.

Goals:
- load from files, .env, env vars, secrets manager
- typed validation via Pydantic
- deterministic precedence and hot-reload for local dev
- simple CLI: `dco validate`, `dco dump`, `dco scaffold`, `dco schema`, `dco validate-file`

## CLI Commands

- `dco validate <model>` - Validate configuration against a Pydantic model
- `dco dump <model>` - Dump merged configuration as JSON
- `dco schema <model>` - Export JSON Schema for a model (json or yaml format)
- `dco scaffold <model>` - Generate a configuration template/scaffold from a model schema (json or yaml format, optional --out for file output)
- `dco validate-file <model> <config_file>` - Validate an explicit config file (JSON/YAML) against the model schema
- `dco watch <model>` - Watch configuration directory and print reloads (dev only)
