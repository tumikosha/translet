import pytest

from translet.exceptions import JsonataError
from translet.transjson import JsonataRunner


def test_apply_simple_expression():
    result = JsonataRunner().apply("$sum(items.value)", {"items": [{"value": 4}, {"value": 7}, {"value": 13}]})
    assert result == 24


def test_apply_field_access():
    result = JsonataRunner().apply("user.name", {"user": {"name": "Alice"}})
    assert result == "Alice"


def test_apply_invalid_expression_raises():
    with pytest.raises(JsonataError):
        JsonataRunner().apply("(((", {})
