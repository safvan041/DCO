# src/dco/utils.py
from typing import Any, Dict, List

from pydantic import BaseModel


def filter_secrets_for_logging(
    d: Dict[str, Any], secret_keys=("password", "secret", "token", "key")
) -> Dict[str, Any]:
    """
    Return a copy of d with values replaced for keys that contain secret substrings.
    """
    import copy

    out = copy.deepcopy(d)

    def walk(node):
        if isinstance(node, dict):
            for k, v in list(node.items()):
                if any(sk in k.lower() for sk in secret_keys):
                    node[k] = "<redacted>"
                else:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(out)
    return out


def model_to_mapping(m: BaseModel) -> Dict[str, Any]:
    """
    Convert a Pydantic model to a plain mapping in a way that is compatible with
    both Pydantic v2 (model_dump) and v1 (dict).
    """
    # Prefer v2 API if present
    if hasattr(m, "model_dump"):
        return m.model_dump()  # type: ignore[attr-defined]
    # Fallback to v1
    return m.dict()  # type: ignore[attr-defined]


def model_schema(model_cls: type[BaseModel]) -> Dict[str, Any]:
    """
    Return a JSON Schema (as a dict) for the provided pydantic model class.
    Supports Pydantic v2 (model_json_schema) and v1 (schema).
    """
    # Pydantic v2 class method
    if hasattr(model_cls, "model_json_schema"):
        return model_cls.model_json_schema()  # type: ignore[attr-defined]
    # Pydantic v1 fallback
    if hasattr(model_cls, "schema"):
        return model_cls.schema()  # type: ignore[attr-defined]
    raise RuntimeError(
        "Provided model class doesn't expose a known Pydantic schema API."
    )


# ---------------- scaffold helpers ----------------
def _pick_example_from_schema(sch: Dict[str, Any]) -> Any:
    """
    Choose a value from schema if default/examples/enum present or basic type fallback.
    """
    if sch is None:
        return None
    # prefer explicit default
    if "default" in sch:
        return sch["default"]
    # examples (list) -> first
    if "examples" in sch and isinstance(sch["examples"], list) and sch["examples"]:
        return sch["examples"][0]
    # enum -> first
    if "enum" in sch and isinstance(sch["enum"], list) and sch["enum"]:
        return sch["enum"][0]

    # handle combined schemas (allOf/oneOf/anyOf) conservatively
    if "allOf" in sch and isinstance(sch["allOf"], list) and sch["allOf"]:
        # merge by preferring later entries
        merged = {}
        for subs in sch["allOf"]:
            if isinstance(subs, dict):
                merged.update(subs)
        return _pick_example_from_schema(merged)
    if "oneOf" in sch and isinstance(sch["oneOf"], list) and sch["oneOf"]:
        # pick first sub-schema
        first = sch["oneOf"][0]
        if isinstance(first, dict):
            return _pick_example_from_schema(first)

    # fallback by declared type
    t = sch.get("type")
    if isinstance(t, list):
        # choose first non-null-like
        for tt in t:
            if tt != "null":
                t = tt
                break
        else:
            t = t[0]

    if t == "string" or t is None:
        return ""
    if t == "integer":
        return 0
    if t == "number":
        return 0
    if t == "boolean":
        return False
    if t == "array":
        items = sch.get("items", {})
        # produce a one-element example
        return [_pick_example_from_schema(items or {})]
    if t == "object":
        # fallback to properties handling in scaffold function
        return {}
    # unknown -> null
    return None


def _scaffold_from_properties(
    properties: Dict[str, Any], required: List[str] | None = None
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    required = required or []
    for name, subschema in properties.items():
        # If property is itself object with properties, recurse
        if not isinstance(subschema, dict):
            out[name] = None
            continue
        if subschema.get("type") == "object" or "properties" in subschema:
            # get nested properties
            nested_props = subschema.get("properties", {})
            nested_required = subschema.get("required", [])
            out[name] = _scaffold_from_properties(nested_props, nested_required)
        elif subschema.get("type") == "array":
            items = subschema.get("items", {})
            out[name] = [_pick_example_from_schema(items)]
        else:
            out[name] = _pick_example_from_schema(subschema)
    return out


def scaffold_from_model(model_cls: type[BaseModel]) -> Dict[str, Any]:
    """
    Generate a mapping (dict) scaffold for the given Pydantic model class using its JSON Schema.
    """
    schema = model_schema(model_cls)
    # Pydantic v2 may wrap 'components' and use $ref for the root model.
    # We attempt to find the root schema's properties.
    root = schema
    # If it's a wrapped schema with 'definitions' or '$ref', try to resolve a root definition
    if "$ref" in schema:
        ref = schema["$ref"]
        # ref format: '#/definitions/Model' or '#/$defs/Model' etc.
        if ref.startswith("#/"):
            path = ref[2:].split("/")
            node = schema
            try:
                for p in path:
                    node = node[p]
                root = node
            except Exception:
                root = schema
    # pydantic v2 sometimes uses "$defs" or "definitions" top-level
    if "properties" not in root:
        # try to locate a definitions/$defs entry with matching model name
        defs = (
            root.get("definitions")
            or root.get("$defs")
            or root.get("components", {}).get("schemas", {})
        )
        if isinstance(defs, dict) and defs:
            # choose the first definition as a heuristic
            first_def = next(iter(defs.values()))
            if isinstance(first_def, dict) and "properties" in first_def:
                root = first_def

    props = root.get("properties", {})
    required = root.get("required", [])
    scaffold = _scaffold_from_properties(props, required)
    return scaffold
