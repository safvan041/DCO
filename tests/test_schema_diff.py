# tests/test_schema_diff.py
from dco.utils import compare_schemas


def test_added_property():
    old = {"properties": {"a": {"type": "string"}}}
    new = {"properties": {"a": {"type": "string"}, "b": {"type": "integer"}}}
    res = compare_schemas(old, new)
    assert "added property: b" in res["non_breaking"]
    assert res["breaking"] == []


def test_removed_property_is_breaking():
    old = {"properties": {"a": {"type": "string"}, "b": {"type": "integer"}}}
    new = {"properties": {"a": {"type": "string"}}}
    res = compare_schemas(old, new)
    assert "removed property: b" in res["breaking"]


def test_property_became_required():
    old = {"properties": {"a": {"type": "string"}}, "required": []}
    new = {"properties": {"a": {"type": "string"}}, "required": ["a"]}
    res = compare_schemas(old, new)
    assert "property became required: a" in res["breaking"]


def test_type_change_breaking():
    old = {"properties": {"x": {"type": "string"}}}
    new = {"properties": {"x": {"type": "integer"}}}
    res = compare_schemas(old, new)
    assert any("type changed for property x" in s for s in res["breaking"])
