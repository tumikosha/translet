from __future__ import annotations

from typing import Any

from ..exceptions import JsonataError


class JsonataRunner:
    """Thin wrapper over `jsonata-python` that normalizes exceptions."""

    def apply(self, rule: str, source: Any) -> Any:
        try:
            import jsonata
        except ImportError as exc:
            raise ImportError(
                "translet requires the `jsonata-python` package. "
                "Install translet with its base dependencies."
            ) from exc

        try:
            expr = jsonata.Jsonata(rule)
        except Exception as exc:
            raise JsonataError(f"Failed to compile JSONata expression: {exc}") from exc

        try:
            return expr.evaluate(source)
        except Exception as exc:
            raise JsonataError(f"Failed to evaluate JSONata expression: {exc}") from exc
