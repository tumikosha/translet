from __future__ import annotations

from typing import Any

from ..exceptions import ValidationError
from ..store import TargetKind
from .key_builder import shape


class ResultValidator:
    """Validates a converted result against the target specification.

    Strategy depends on target_kind:
      - "schema":      jsonschema validation
      - "sample":      structural compatibility (shape comparison)
      - "description": no validation (only catches jsonata runtime errors)
    """

    def validate(self, result: Any, target_kind: TargetKind, target_spec: Any) -> None:
        if target_kind == "schema":
            self._validate_schema(result, target_spec)
        elif target_kind == "sample":
            self._validate_sample(result, target_spec)
        elif target_kind == "description":
            return
        else:
            raise ValueError(f"Unknown target kind: {target_kind!r}")

    def _validate_schema(self, result: Any, schema: Any) -> None:
        try:
            import jsonschema
        except ImportError as exc:
            raise ImportError(
                "translet requires `jsonschema` for schema validation. "
                "Install translet with its base dependencies."
            ) from exc

        try:
            jsonschema.validate(instance=result, schema=schema)
        except jsonschema.ValidationError as exc:
            raise ValidationError(
                f"Result failed schema validation: {exc.message}",
                expected=schema,
                actual=result,
            ) from exc

    def _validate_sample(self, result: Any, sample: Any) -> None:
        result_shape = shape(result)
        expected_shape = shape(sample)
        if not _shape_compatible(result_shape, expected_shape):
            raise ValidationError(
                "Result shape does not match target sample shape.",
                expected=expected_shape,
                actual=result_shape,
            )


def _shape_compatible(actual: Any, expected: Any) -> bool:
    """Check whether `actual` shape is structurally compatible with `expected`.

    Compatibility rules:
      - Primitive shape strings must match exactly.
      - Dicts: every key in `expected` must appear in `actual` with a
        compatible shape. Extra keys in `actual` are allowed.
      - Lists: if `expected` is empty list, `actual` must be a list. Else
        every actual element must be compatible with the unified expected element.
    """
    if isinstance(expected, str):
        return actual == expected
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(k in actual and _shape_compatible(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        if not expected:
            return True
        if not actual:
            return True
        expected_item = expected[0]
        return all(_shape_compatible(item, expected_item) for item in actual)
    return actual == expected
