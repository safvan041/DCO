# src/dco/cli.py
import argparse
import importlib
import json
import os
import sys
import tempfile
import time
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel, ValidationError

from .core import ConfigLoader
from .secrets import NoopSecretsProvider
from .utils import (
    compare_schemas,
    model_schema,
    model_to_mapping,
    scaffold_from_model,
    schema_to_markdown,
)
from .watcher import start_watcher


# loader helper unchanged
def _load_model_from_path(module_path: str):
    if ":" not in module_path:
        raise ValueError(
            "Model must be specified as module:ModelName (e.g. examples.simple_app.app:AppSettings)"
        )

    mod_path, cls_name = module_path.split(":", 1)
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


# existing commands kept (dump, validate, watch, schema, scaffold, validate-file)
def dump_command(args):
    Model = _load_model_from_path(args.model)
    loader = ConfigLoader(
        Model,
        config_dir=args.config_dir,
        secrets_provider=NoopSecretsProvider(),
        lenient_yaml=getattr(args, "lenient_yaml", False),
    )
    try:
        cfg = loader.load()
    except ValidationError as e:
        print("Validation failed:\n", e)
        raise SystemExit(2)
    print(json.dumps(model_to_mapping(cfg), indent=2, ensure_ascii=False))


def validate_command(args):
    Model = _load_model_from_path(args.model)
    loader = ConfigLoader(
        Model,
        config_dir=args.config_dir,
        secrets_provider=NoopSecretsProvider(),
        lenient_yaml=getattr(args, "lenient_yaml", False),
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
        Model,
        config_dir=args.config_dir,
        secrets_provider=NoopSecretsProvider(),
        lenient_yaml=getattr(args, "lenient_yaml", False),
    )
    get_settings = loader.get_cached_loader()

    def on_change(path):
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


def schema_command(args):
    Model = _load_model_from_path(args.model)
    try:
        schema = model_schema(Model)
    except Exception as e:
        print("Failed to generate schema:", e)
        raise SystemExit(2)

    if args.format == "yaml":
        try:
            import yaml  # type: ignore
        except ImportError:
            print("PyYAML not installed; install PyYAML to output YAML.")
            raise SystemExit(3)
        print(yaml.safe_dump(schema, sort_keys=False))
    else:
        print(json.dumps(schema, indent=2, ensure_ascii=False))


def scaffold_command(args):
    Model = _load_model_from_path(args.model)
    try:
        scaffold = scaffold_from_model(Model)
    except Exception as e:
        print("Failed to generate scaffold:", e)
        raise SystemExit(2)

    out_format = args.format or "json"
    if out_format == "yaml":
        try:
            import yaml
        except ImportError:
            print("PyYAML not installed; install PyYAML to output YAML.")
            raise SystemExit(3)
        rendered = yaml.safe_dump(scaffold, sort_keys=False)
    else:
        rendered = json.dumps(scaffold, indent=2, ensure_ascii=False)

    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
        print(f"Wrote scaffold to {args.out}")
    else:
        print(rendered)


def _load_config_file(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    text = p.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except Exception:
        try:
            import yaml
        except ImportError:
            raise RuntimeError(
                "Could not parse config file as JSON and PyYAML not installed to parse YAML."
            )
        try:
            data = yaml.safe_load(text)
            if data is None:
                return {}
            return data
        except Exception as e:
            raise RuntimeError(f"Failed to parse config file {path}: {e}") from e


def validate_file_command(args):
    Model = _load_model_from_path(args.model)
    try:
        schema = model_schema(Model)
    except Exception as e:
        print("Failed to generate schema for model:", e)
        raise SystemExit(2)

    try:
        cfg = _load_config_file(args.config_file)
    except FileNotFoundError:
        print(f"Config file not found: {args.config_file}")
        raise SystemExit(2)
    except RuntimeError as e:
        print(e)
        raise SystemExit(2)

    try:
        import jsonschema
    except Exception:
        print(
            "jsonschema not installed. Install with `pip install jsonschema` to use validate-file."
        )
        raise SystemExit(3)

    try:
        jsonschema.validate(instance=cfg, schema=schema)
    except jsonschema.ValidationError as e:
        print("CONFIG VALIDATION FAILED:")
        print(e.message)
        if e.path:
            print("Path:", ".".join(map(str, list(e.path))))
        if e.schema_path:
            print("Schema Path:", ".".join(map(str, list(e.schema_path))))
        print("\nFull error:\n", e)
        raise SystemExit(2)
    except Exception as e:
        print("Unexpected validation error:", e)
        raise SystemExit(2)

    print("Config file valid against model schema.")


# ---------- NEW: schema-diff command ----------
def _load_schema_file(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    text = p.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except Exception:
        try:
            import yaml
        except ImportError:
            raise RuntimeError(
                "Could not parse schema file as JSON and PyYAML not installed to parse YAML."
            )
        try:
            data = yaml.safe_load(text)
            if data is None:
                return {}
            return data
        except Exception as e:
            raise RuntimeError(f"Failed to parse schema file {path}: {e}") from e


def schema_diff_command(args):
    try:
        old = _load_schema_file(args.old)
        new = _load_schema_file(args.new)
    except FileNotFoundError as e:
        print("Schema file not found:", e)
        raise SystemExit(2)
    except RuntimeError as e:
        print(e)
        raise SystemExit(2)

    result = compare_schemas(old, new)
    breaking = result.get("breaking", [])
    non_breaking = result.get("non_breaking", [])

    if not breaking and not non_breaking:
        print("No differences detected.")
        return

    if non_breaking:
        print("Non-breaking changes:")
        for x in non_breaking:
            print("  -", x)
    if breaking:
        print("\nBREAKING changes:")
        for x in breaking:
            print("  -", x)

    # exit non-zero if there are breaking changes so CI can fail
    if breaking:
        raise SystemExit(2)


def docs_command(args):
    Model = _load_model_from_path(args.model)
    try:
        schema = model_schema(Model)
    except Exception as e:
        print("Failed to generate schema:", e)
        raise SystemExit(2)

    md = schema_to_markdown(schema, title=args.title or None)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"Wrote docs to {args.out}")
    else:
        print(md)


def validate_merged_command(args):
    """
    Dump the merged config (using loader semantics) to a temporary file
    and validate it against the model schema using the existing validate-file logic.
    Exits 0 on success, 2 on validation failure.
    """
    # Load model and produce merged config via ConfigLoader
    Model = _load_model_from_path(args.model)
    loader = ConfigLoader(
        Model,
        config_dir=args.config_dir,
        secrets_provider=NoopSecretsProvider(),
        lenient_yaml=getattr(args, "lenient_yaml", False),
    )
    try:
        cfg = loader.load()
    except Exception as e:
        print("Failed to load merged config:", e)
        raise SystemExit(2)

    # Convert Pydantic model instance to plain mapping (JSON serializable)
    try:
        obj = model_to_mapping(cfg)
    except Exception:
        # fallback - try dict
        try:
            obj = cfg.dict()  # for Pydantic v1 compatibility
        except Exception as e:
            print("Failed to convert config to mapping for validation:", e)
            raise SystemExit(2)

    # Dump to a temp JSON file and call the existing validate-file logic by reusing _load_schema_file + compare via jsonschema
    # But to avoid duplicating parsing code, we'll write to a temp file and call the validate_file_command logic by constructing a fake args object.
    import json
    from types import SimpleNamespace

    tf = None
    try:
        tf = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(obj, tf, indent=2, ensure_ascii=False)
        tf.flush()
        tf.close()
        fake_args = SimpleNamespace(model=args.model, config_file=tf.name)
        # Reuse the validate_file_command implementation defined earlier
        validate_file_command(fake_args)
    finally:
        # remove temp file if exists
        import os

        if tf is not None and os.path.exists(tf.name):
            try:
                os.remove(tf.name)
            except Exception:
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dco")
    parser.add_argument("--config-dir", default="config", help="path to config dir")
    parser.add_argument(
        "--lenient-yaml",
        action="store_true",
        default=False,
        help="attempt lenient YAML parsing (sanitization) when YAML parsing fails",
    )
    sub = parser.add_subparsers(dest="cmd")

    dump = sub.add_parser("dump", help="dump merged config as JSON")
    dump.add_argument("model", help="module:ModelName (pydantic BaseModel)")
    dump.set_defaults(func=dump_command)

    validate = sub.add_parser(
        "validate", help="validate config (using loader merge semantics)"
    )
    validate.add_argument("model", help="module:ModelName (pydantic BaseModel)")
    validate.set_defaults(func=validate_command)

    validate_file = sub.add_parser(
        "validate-file",
        help="validate an explicit config file against the model schema (json/yaml)",
    )
    validate_file.add_argument("model", help="module:ModelName (pydantic BaseModel)")
    validate_file.add_argument(
        "config_file", help="path to JSON or YAML config file to validate"
    )
    validate_file.set_defaults(func=validate_file_command)

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

    scaffold = sub.add_parser(
        "scaffold", help="scaffold a config template from model schema"
    )
    scaffold.add_argument("model", help="module:ModelName (pydantic BaseModel)")
    scaffold.add_argument(
        "--format", choices=("json", "yaml"), default="json", help="output format"
    )
    scaffold.add_argument(
        "--out", help="optional output file path (writes file instead of stdout)"
    )
    scaffold.set_defaults(func=scaffold_command)

    schema_diff = sub.add_parser(
        "schema-diff", help="compare two schema files and detect breaking changes"
    )
    schema_diff.add_argument("old", help="path to old schema (json or yaml)")
    schema_diff.add_argument("new", help="path to new schema (json or yaml)")
    schema_diff.set_defaults(func=schema_diff_command)

    docs = sub.add_parser("docs", help="generate Markdown docs from model schema")
    docs.add_argument("model", help="module:ModelName (pydantic BaseModel)")
    docs.add_argument(
        "--out", help="optional output file path (writes file instead of stdout)"
    )
    docs.add_argument("--title", help="optional document title")
    docs.set_defaults(func=docs_command)
    validate_merged = sub.add_parser(
        "validate-merged",
        help="dump merged config and validate it against the model schema",
    )
    validate_merged.add_argument("model", help="module:ModelName (pydantic BaseModel)")
    validate_merged.set_defaults(func=validate_merged_command)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        raise SystemExit(1)
    return args.func(args)


if __name__ == "__main__":
    main()
