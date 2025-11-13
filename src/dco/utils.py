# src/dco/utils.py
from typing import Any, Dict

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

    Returns:
        mapping representing the model's JSON Schema.
    """
    # Pydantic v2 class method
    if hasattr(model_cls, "model_json_schema"):
        # model_json_schema() returns a dict-like schema
        return model_cls.model_json_schema()  # type: ignore[attr-defined]
    # Pydantic v1 fallback
    if hasattr(model_cls, "schema"):
        return model_cls.schema()  # type: ignore[attr-defined]
    raise RuntimeError(
        "Provided model class doesn't expose a known Pydantic schema API."
    )
