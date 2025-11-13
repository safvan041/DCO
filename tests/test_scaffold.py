# tests/test_scaffold.py
from typing import Any, Dict, Optional

from pydantic import BaseModel

from dco.utils import scaffold_from_model


class SimpleModel(BaseModel):
    name: str = "default_name"
    count: int = 0
    enabled: bool = True


class NestedModel(BaseModel):
    debug: bool = False
    database: Dict[str, Any] = {"host": "localhost", "port": 5432}
    optional_field: Optional[str] = None


class ComplexModel(BaseModel):
    app_name: str = "MyApp"
    settings: SimpleModel = SimpleModel()
    config: NestedModel = NestedModel()


def test_scaffold_simple_model():
    scaffold = scaffold_from_model(SimpleModel)
    assert isinstance(scaffold, dict)
    assert "name" in scaffold
    assert "count" in scaffold
    assert "enabled" in scaffold
    assert scaffold["name"] == "default_name"
    assert scaffold["count"] == 0
    assert scaffold["enabled"] is True


def test_scaffold_nested_model():
    scaffold = scaffold_from_model(NestedModel)
    assert isinstance(scaffold, dict)
    assert "debug" in scaffold
    assert "database" in scaffold
    assert "optional_field" in scaffold
    assert scaffold["debug"] is False
    assert isinstance(scaffold["database"], dict)
    assert scaffold["optional_field"] is None


def test_scaffold_complex_model():
    scaffold = scaffold_from_model(ComplexModel)
    assert isinstance(scaffold, dict)
    assert "app_name" in scaffold
    assert "settings" in scaffold
    assert "config" in scaffold
    assert scaffold["app_name"] == "MyApp"
    assert isinstance(scaffold["settings"], dict)
    assert isinstance(scaffold["config"], dict)
