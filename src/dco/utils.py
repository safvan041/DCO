# src/dco/utils.py
from typing import Any, Dict, List

from pydantic import BaseModel


def filter_secrets_for_logging(
    d: Dict[str, Any], secret_keys=("password", "secret", "token", "key")
) -> Dict[str, Any]:
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
    if hasattr(m, "model_dump"):
        return m.model_dump()  # type: ignore[attr-defined]
    return m.dict()  # type: ignore[attr-defined]


def model_schema(model_cls: type[BaseModel]) -> Dict[str, Any]:
    if hasattr(model_cls, "model_json_schema"):
        return model_cls.model_json_schema()  # type: ignore[attr-defined]
    if hasattr(model_cls, "schema"):
        return model_cls.schema()  # type: ignore[attr-defined]
    raise RuntimeError(
        "Provided model class doesn't expose a known Pydantic schema API."
    )


# ---------------- scaffold helpers ----------------
def _pick_example_from_schema(sch: Dict[str, Any]) -> Any:
    if sch is None:
        return None
    if "default" in sch:
        return sch["default"]
    if "examples" in sch and isinstance(sch["examples"], list) and sch["examples"]:
        return sch["examples"][0]
    if "enum" in sch and isinstance(sch["enum"], list) and sch["enum"]:
        return sch["enum"][0]
    if "allOf" in sch and isinstance(sch["allOf"], list) and sch["allOf"]:
        merged = {}
        for subs in sch["allOf"]:
            if isinstance(subs, dict):
                merged.update(subs)
        return _pick_example_from_schema(merged)
    if "oneOf" in sch and isinstance(sch["oneOf"], list) and sch["oneOf"]:
        first = sch["oneOf"][0]
        if isinstance(first, dict):
            return _pick_example_from_schema(first)

    t = sch.get("type")
    if isinstance(t, list):
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
        return [_pick_example_from_schema(items or {})]
    if t == "object":
        return {}
    return None


def _scaffold_from_properties(
    properties: Dict[str, Any], required: List[str] | None = None
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    required = required or []
    for name, subschema in properties.items():
        if not isinstance(subschema, dict):
            out[name] = None
            continue
        if subschema.get("type") == "object" or "properties" in subschema:
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
    schema = model_schema(model_cls)
    root = schema
    if "$ref" in schema:
        ref = schema["$ref"]
        if isinstance(ref, str) and ref.startswith("#/"):
            path = ref[2:].split("/")
            node = schema
            try:
                for p in path:
                    node = node[p]
                root = node
            except Exception:
                root = schema
    if "properties" not in root:
        defs = (
            root.get("definitions")
            or root.get("$defs")
            or root.get("components", {}).get("schemas", {})
        )
        if isinstance(defs, dict) and defs:
            first_def = next(iter(defs.values()))
            if isinstance(first_def, dict) and "properties" in first_def:
                root = first_def
    props = root.get("properties", {})
    required = root.get("required", [])
    scaffold = _scaffold_from_properties(props, required)
    return scaffold


# ---------------- schema diff helpers ----------------
def _normalize_type(t: Any) -> List[str]:
    if t is None:
        return []
    if isinstance(t, list):
        return [str(x) for x in t]
    return [str(t)]


def _get_props(schema: Dict[str, Any]) -> Dict[str, Any]:
    root = schema
    if "$ref" in schema:
        ref = schema["$ref"]
        if isinstance(ref, str) and ref.startswith("#/"):
            path = ref[2:].split("/")
            node = schema
            try:
                for p in path:
                    node = node[p]
                root = node
            except Exception:
                root = schema
    if "properties" not in root:
        defs = (
            root.get("definitions")
            or root.get("$defs")
            or root.get("components", {}).get("schemas", {})
        )
        if isinstance(defs, dict) and defs:
            first_def = next(iter(defs.values()))
            if isinstance(first_def, dict) and "properties" in first_def:
                root = first_def
    props = root.get("properties", {})
    required = root.get("required", [])
    return {"properties": props or {}, "required": required or []}


def compare_schemas(
    old_schema: Dict[str, Any], new_schema: Dict[str, Any]
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"breaking": [], "non_breaking": []}
    old = _get_props(old_schema)
    new = _get_props(new_schema)
    old_props = old["properties"]
    new_props = new["properties"]
    old_required = set(old["required"])
    new_required = set(new["required"])

    for k in sorted(old_props.keys()):
        if k not in new_props:
            out["breaking"].append(f"removed property: {k}")

    for k in sorted(new_props.keys()):
        if k not in old_props:
            out["non_breaking"].append(f"added property: {k}")

    for k in sorted(set(old_props.keys()).intersection(new_props.keys())):
        old_p = old_props[k] or {}
        new_p = new_props[k] or {}

        old_req = k in old_required
        new_req = k in new_required
        if not old_req and new_req:
            out["breaking"].append(f"property became required: {k}")
        if old_req and not new_req:
            out["non_breaking"].append(f"property became optional: {k}")

        old_types = _normalize_type(old_p.get("type"))
        new_types = _normalize_type(new_p.get("type"))
        if not old_types:
            if "anyOf" in old_p or "oneOf" in old_p:
                old_types = ["mixed"]
        if not new_types:
            if "anyOf" in new_p or "oneOf" in new_p:
                new_types = ["mixed"]

        if old_types and new_types and set(old_types) != set(new_types):
            if set(old_types).issubset(set(new_types)):
                out["non_breaking"].append(
                    f"property type widened: {k} ({old_types} -> {new_types})"
                )
            else:
                out["breaking"].append(
                    f"type changed for property {k}: {old_types} -> {new_types}"
                )

        old_enum = old_p.get("enum")
        new_enum = new_p.get("enum")
        if isinstance(old_enum, list) and isinstance(new_enum, list):
            removed_vals = [v for v in old_enum if v not in new_enum]
            if removed_vals:
                out["breaking"].append(f"enum values removed for {k}: {removed_vals}")
            added_vals = [v for v in new_enum if v not in old_enum]
            if added_vals:
                out["non_breaking"].append(f"enum values added for {k}: {added_vals}")

    return out


# ---------------- schema -> markdown docs ----------------
def _type_from_schema(sch: Dict[str, Any]) -> str:
    """
    Return a friendly type description for the property schema.
    """
    t = sch.get("type")
    if isinstance(t, list):
        return "|".join(str(x) for x in t)
    if t is None:
        # infer from presence of anyOf/oneOf/enum
        if "anyOf" in sch or "oneOf" in sch:
            return "mixed"
        if "enum" in sch:
            return "enum"
        return "any"
    return str(t)


def _render_property_md(
    name: str, sch: Dict[str, Any], required: bool, level: int = 2
) -> str:
    """
    Render a single property to Markdown lines.
    """
    indent = "#" * level
    lines = []
    # heading with name
    lines.append(f"{indent} `{name}`")
    # short metadata line
    typ = _type_from_schema(sch)
    meta = f"- **Type:** {typ}"
    if required:
        meta += " • **Required**"
    else:
        meta += " • Optional"
    # default / enum / examples
    if "default" in sch:
        meta += f" • **Default:** `{sch['default']}`"
    if "enum" in sch:
        meta += f" • **Allowed:** `{sch['enum']}`"
    if "examples" in sch:
        meta += f" • **Example:** `{sch['examples'][0]}`"
    lines.append(meta)
    # description text
    desc = sch.get("description") or sch.get("title") or ""
    if desc:
        lines.append("")
        lines.append(desc)
    # if object, recursively render nested props
    if sch.get("type") == "object" or "properties" in sch:
        nested = sch.get("properties", {})
        nested_required = set(sch.get("required", []))
        if nested:
            lines.append("")
            lines.append("**Properties:**")
            for k, subs in nested.items():
                lines.append("")
                lines.append(
                    _render_property_md(
                        k, subs or {}, k in nested_required, level=level + 1
                    )
                )
    # if array with object items, render item schema
    if sch.get("type") == "array":
        items = sch.get("items", {})
        if items and (items.get("type") == "object" or "properties" in items):
            lines.append("")
            lines.append("**Array item properties:**")
            nested = items.get("properties", {})
            nested_required = set(items.get("required", []))
            for k, subs in nested.items():
                lines.append("")
                lines.append(
                    _render_property_md(
                        k, subs or {}, k in nested_required, level=level + 1
                    )
                )
    return "\n".join(lines)


def schema_to_markdown(schema: Dict[str, Any], title: str | None = None) -> str:
    """
    Convert a JSON Schema mapping into a Markdown document string.
    """
    root = schema
    # resolve wrapper / $ref heuristics used earlier
    if "$ref" in schema:
        ref = schema["$ref"]
        if isinstance(ref, str) and ref.startswith("#/"):
            path = ref[2:].split("/")
            node = schema
            try:
                for p in path:
                    node = node[p]
                root = node
            except Exception:
                root = schema
    if "properties" not in root:
        defs = (
            root.get("definitions")
            or root.get("$defs")
            or root.get("components", {}).get("schemas", {})
        )
        if isinstance(defs, dict) and defs:
            first_def = next(iter(defs.values()))
            if isinstance(first_def, dict) and "properties" in first_def:
                root = first_def

    doc_lines: List[str] = []
    if title:
        doc_lines.append(f"# {title}")
        doc_lines.append("")

    description = root.get("description") or root.get("title")
    if description:
        doc_lines.append(description)
        doc_lines.append("")

    props = root.get("properties", {})
    required = set(root.get("required", []))

    if not props:
        doc_lines.append("_No documented properties in schema._")
        return "\n".join(doc_lines)

    doc_lines.append("## Properties")
    doc_lines.append("")
    for name, sch in props.items():
        sch = sch or {}
        req = name in required
        doc_lines.append(_render_property_md(name, sch, req, level=3))
        doc_lines.append("")  # spacing

    return "\n".join(doc_lines)
