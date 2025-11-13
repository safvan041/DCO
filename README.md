# DCO — Dynamic Config Orchestrator

Opinionated, typed, layered configuration loader for Python services.

Goals:
- load from files, .env, env vars, secrets manager
- typed validation via Pydantic
- deterministic precedence and hot-reload for local dev
- simple CLI: `dco validate`, `dco dump`
