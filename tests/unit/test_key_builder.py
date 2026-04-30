from translet.transjson import build_key, normalize_target, shape


def test_shape_primitive_values():
    assert shape(1) == "<int>"
    assert shape(1.5) == "<float>"
    assert shape("x") == "<str>"
    assert shape(True) == "<bool>"
    assert shape(None) == "<null>"


def test_shape_dict_orders_keys():
    s1 = shape({"b": 1, "a": "x"})
    s2 = shape({"a": "y", "b": 99})
    assert s1 == s2 == {"a": "<str>", "b": "<int>"}


def test_shape_list_homogeneous_dicts_unifies_keys():
    payload = [{"a": 1}, {"a": 2, "b": "x"}]
    assert shape(payload) == [{"a": "<int>", "b": "<str>"}]


def test_shape_empty_list_is_stable():
    assert shape([]) == []


def test_normalize_target_sample_uses_shape():
    spec = {"value": 42}
    assert normalize_target("sample", spec) == {"value": "<int>"}


def test_normalize_target_description_lowercases_and_strips():
    assert normalize_target("description", "  HELLO World  ") == "hello world"


def test_build_key_with_name():
    key = build_key(name="orders_v1", source={"a": 1}, target_kind="sample", target_spec={"b": 2})
    assert key == "name:orders_v1"


def test_build_key_hash_is_deterministic():
    k1 = build_key(name=None, source={"a": 1}, target_kind="sample", target_spec={"b": 2})
    k2 = build_key(name=None, source={"a": 99}, target_kind="sample", target_spec={"b": 7})
    assert k1 == k2
    assert k1.startswith("hash:")


def test_build_key_differs_for_different_target_kind():
    src = {"a": 1}
    schema = {"type": "object"}
    k1 = build_key(name=None, source=src, target_kind="schema", target_spec=schema)
    k2 = build_key(name=None, source=src, target_kind="sample", target_spec=schema)
    assert k1 != k2


def test_build_key_differs_for_different_source_shape():
    k1 = build_key(name=None, source={"a": 1}, target_kind="sample", target_spec={"b": 2})
    k2 = build_key(name=None, source={"a": 1, "x": "y"}, target_kind="sample", target_spec={"b": 2})
    assert k1 != k2
