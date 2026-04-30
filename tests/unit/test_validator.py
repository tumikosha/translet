import pytest

from translet.exceptions import ValidationError
from translet.transjson import ResultValidator


def test_schema_validation_passes():
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
    ResultValidator().validate({"x": 1}, "schema", schema)


def test_schema_validation_fails():
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
    with pytest.raises(ValidationError):
        ResultValidator().validate({"x": "not int"}, "schema", schema)


def test_sample_validation_passes_with_extra_keys():
    sample = {"name": "x", "age": 1}
    ResultValidator().validate({"name": "y", "age": 99, "extra": True}, "sample", sample)


def test_sample_validation_fails_on_missing_key():
    sample = {"name": "x", "age": 1}
    with pytest.raises(ValidationError):
        ResultValidator().validate({"name": "y"}, "sample", sample)


def test_sample_validation_fails_on_type_mismatch():
    sample = {"x": 1}
    with pytest.raises(ValidationError):
        ResultValidator().validate({"x": "string"}, "sample", sample)


def test_description_validation_is_noop():
    ResultValidator().validate({"any": "value"}, "description", "make a flat list")
