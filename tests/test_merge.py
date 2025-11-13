from dco.core import deep_merge


def test_deep_merge_simple():
    a = {"x": 1, "y": {"a": 1}}
    b = {"y": {"b": 2}, "z": 3}
    out = deep_merge(a, b)
    assert out["x"] == 1
    assert out["y"]["a"] == 1 and out["y"]["b"] == 2
    assert out["z"] == 3
