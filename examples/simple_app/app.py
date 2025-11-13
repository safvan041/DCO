# examples/simple_app/app.py
"""
Simple demo app for DCO (Dynamic Config Orchestrator).

Usage (from repo root):
  PYTHONPATH=src DCO_ENV=development python examples/simple_app/app.py

Or use the dco CLI once package installed:
  dco watch examples.simple_app.app:AppSettings --config-dir=examples/simple_app/config
"""
import json
import os
from typing import Optional

from pydantic import BaseModel, Field

# Import package from src/
from dco.core import ConfigLoader
from dco.secrets import NoopSecretsProvider
from dco.utils import filter_secrets_for_logging, model_to_mapping


# --------- Define settings model ----------
class DBConfig(BaseModel):
    host: str
    port: int = 5432
    username: Optional[str] = None
    password: Optional[str] = None


class AppSettings(BaseModel):
    debug: bool = False
    environment: str = Field("development")
    sample_value: str = "hello"
    db: DBConfig


# --------- Demo logic ----------
def main():
    # Choose config dir used for this example
    cfg_dir = os.path.join(os.path.dirname(__file__), "config")

    loader = ConfigLoader(
        AppSettings,
        config_dir=cfg_dir,
        secrets_provider=NoopSecretsProvider(),
        load_dotenv=True,
    )
    get_settings = loader.get_cached_loader()

    # initial load
    settings = get_settings()
    safe = filter_secrets_for_logging(model_to_mapping(settings))
    print("[startup] loaded settings:")
    print(json.dumps(safe, indent=2, ensure_ascii=False))

    # simple loop to show usage; hot-reload is optional
    print(
        "\nEnter 'r' to reload programmatically, or run with environment watcher demo."
    )
    print(
        "This example will also automatically reload when config files change if you enable the watcher below.\n"
    )

    # Start watcher only when running interactively (prevents background watcher in non-interactive CI)
    try:
        import sys

        is_interactive = sys.stdin.isatty()
    except Exception:
        is_interactive = False

    if is_interactive:
        from dco.watcher import start_watcher

        def on_change(path):
            print(f"\n[watcher] detected change in: {path}")
            get_settings.cache_clear()
            try:
                s = get_settings()
                print("[watcher] reloaded settings (redacted):")
                print(
                    json.dumps(
                        filter_secrets_for_logging(model_to_mapping(s)),
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            except Exception as e:
                print("[watcher] reload failed:", e)

        # start watcher in background for the example (safe for local dev only)
        start_watcher(cfg_dir, on_change)
    else:
        print(
            "[info] Non-interactive environment detected: watcher disabled. Use manual reloads or run interactively."
        )

    try:
        while True:
            # In non-interactive environments input() raises EOFError. We only reach here if interactive.
            cmd = input("> (r=reload, q=quit) ").strip().lower()
            if cmd == "r":
                get_settings.cache_clear()
                s = get_settings()
                print(
                    "[manual reload] settings:",
                    json.dumps(
                        filter_secrets_for_logging(model_to_mapping(s)),
                        indent=2,
                        ensure_ascii=False,
                    ),
                )
            elif cmd == "q":
                print("Exiting.")
                break
            else:
                print("Unknown. Use 'r' or 'q'.")
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")
        return


if __name__ == "__main__":
    main()
