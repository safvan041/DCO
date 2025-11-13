# src/dco/cli.py
import argparse
import importlib
import json
import os
import sys
import time
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from pydantic import BaseModel, ValidationError

from .core import ConfigLoader
from .secrets import NoopSecretsProvider
from .utils import model_schema, model_to_mapping
from .watcher import start_watcher


# NOTE: _load_model_from_path is unchanged — supports module:Class and file paths
def _load_model_from_path(module_path: str):
    """
    Accepts:
      - module:ClassName  e.g. examples.simple_app.app:AppSettings
      - filesystem path: ./examples/simple_app/app.py:AppSettings or examples/simple_app/app.py:AppSettings

    Tries:
      1. importlib.import_module on the module portion (temporarily inserting cwd into sys.path)
      2. fallback: load module from filesystem path via importlib.util.spec_from_file_location
    """
    if ":" not in module_path:
        raise ValueError(
            "Model must be specified as module:ModelName (e.g. examples.simple_app.app:AppSettings)"
        )

    mod_path, cls_name = module_path.split(":", 1)

    # First attempt: try a normal import. Ensure cwd is on sys.path so local directories are discoverable.
    cwd = os.getcwd()
    inserted = False
    try:
        if cwd not in sys.path:
            sys.path.insert(0, cwd)
            inserted = True
        try:
            mod = importlib.import_module(mod_path)
        except ModuleNotFoundError:
            mod = None

        if mod is not None:
            cls = getattr(mod, cls_name, None)
            if cls is None:
                raise AttributeError(
                    f"Module '{mod_path}' found but class '{cls_name}' not in module."
                )
            if not issubclass(cls, BaseModel):
                raise TypeError("Provided class is not a pydantic BaseModel subclass.")
            return cls

        # Second attempt: treat mod_path as a filesystem path (with or without .py)
        candidate_paths = []
        if mod_path.endswith(".py"):
            candidate_paths.append(Path(mod_path))
        else:
            candidate_paths.append(Path(mod_path + ".py"))
            candidate_paths.append(Path(mod_path.replace(".", "/") + ".py"))
            candidate_paths.append(Path(cwd) / (mod_path + ".py"))
            candidate_paths.append(Path(cwd) / (mod_path.replace(".", "/") + ".py"))

        found = None
        for p in candidate_paths:
            if p.exists():
                found = p.resolve()
                break

        if not found:
            raise ModuleNotFoundError(
                f"Could not import module '{mod_path}' and no file found among candidates: {candidate_paths}"
            )

        # load module from file
        spec = spec_from_file_location(found.stem, str(found))
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to create module spec for file: {found}")
        module = module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)  # type: ignore
        cls = getattr(module, cls_name, None)
        if cls is None:
            raise AttributeError(
                f"File '{found}' loaded but class '{cls_name}' not found."
            )
        if not issubclass(cls, BaseModel):
            raise TypeError("Provided class is not a pydantic BaseModel subclass.")
        return cls

    finally:
        if inserted:
            try:
                sys.path.remove(cwd)
            except ValueError:
                pass


# ---------- existing commands ----------
def dump_command(args):
    Model = _load_model_from_path(args.model)
    loader = ConfigLoader(
        Model, config_dir=args.config_dir, secrets_provider=NoopSecretsProvider()
    )
    try:
        cfg = loader.load()
    except ValidationError as e:
        print("Validation failed:\n", e)
        raise SystemExit(2)
    # print merged as JSON using model_to_mapping for pydantic v1/v2 compatibility
    print(json.dumps(model_to_mapping(cfg), indent=2, ensure_ascii=False))


def validate_command(args):
    Model = _load_model_from_path(args.model)
    loader = ConfigLoader(
        Model, config_dir=args.config_dir, secrets_provider=NoopSecretsProvider()
    )
    try:
        loader.load()
    except ValidationError as e:
        print("Validation failed:\n", e)
        raise SystemExit(2)
    print("Validation OK")


def watch_command(args):
    Model = _load_model_from_path(args.model)
    loader = ConfigLoader(
        Model, config_dir=args.config_dir, secrets_provider=NoopSecretsProvider()
    )
    get_settings = loader.get_cached_loader()

    def on_change(path):
        # clear cache and reload
        get_settings.cache_clear()
        try:
            s = get_settings()
            print(f"[dco.watch] reloaded from {path}:")
            print(json.dumps(model_to_mapping(s), indent=2, ensure_ascii=False))
        except Exception as e:
            print("[dco.watch] reload failed:", e)

    print(f"Watching {args.config_dir} for changes. Ctrl-C to stop.")
    start_watcher(args.config_dir, on_change)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopped.")


# ---------- new schema command ----------
def schema_command(args):
    """
    Output JSON Schema for the provided Pydantic model class.
    """
    Model = _load_model_from_path(args.model)
    try:
        schema = model_schema(Model)
    except Exception as e:
        print("Failed to generate schema:", e)
        raise SystemExit(2)

    if args.format == "yaml":
        try:
            import yaml
        except ImportError:
            print("PyYAML not installed; install PyYAML to output YAML.")
            raise SystemExit(3)
        print(yaml.safe_dump(schema, sort_keys=False))
    else:
        print(json.dumps(schema, indent=2, ensure_ascii=False))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dco")
    parser.add_argument("--config-dir", default="config", help="path to config dir")
    sub = parser.add_subparsers(dest="cmd")

    dump = sub.add_parser("dump", help="dump merged config as JSON")
    dump.add_argument("model", help="module:ModelName (pydantic BaseModel)")
    dump.set_defaults(func=dump_command)

    validate = sub.add_parser("validate", help="validate config")
    validate.add_argument("model", help="module:ModelName (pydantic BaseModel)")
    validate.set_defaults(func=validate_command)

    watch = sub.add_parser(
        "watch", help="watch config directory and print reloads (dev only)"
    )
    watch.add_argument("model", help="module:ModelName (pydantic BaseModel)")
    watch.set_defaults(func=watch_command)

    schema = sub.add_parser(
        "schema", help="export JSON Schema for a model (json or yaml)"
    )
    schema.add_argument("model", help="module:ModelName (pydantic BaseModel)")
    schema.add_argument(
        "--format", choices=("json", "yaml"), default="json", help="output format"
    )
    schema.set_defaults(func=schema_command)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        raise SystemExit(1)
    return args.func(args)


if __name__ == "__main__":
    main()
