from __future__ import annotations

import hashlib
import json
from typing import Any

from ..store import TargetKind


def shape(value: Any) -> Any:
    """Return a structural fingerprint of a JSON-like value (no actual values)."""
    if value is None:
        return "<null>"
    if isinstance(value, bool):
        return "<bool>"
    if isinstance(value, int):
        return "<int>"
    if isinstance(value, float):
        return "<float>"
    if isinstance(value, str):
        return "<str>"
    if isinstance(value, dict):
        return {k: shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        if not value:
            return []
        merged: dict[str, Any] = {}
        non_dict_items: list[Any] = []
        for item in value:
            item_shape = shape(item)
            if isinstance(item_shape, dict):
                for k, v in item_shape.items():
                    if k not in merged:
                        merged[k] = v
            else:
                non_dict_items.append(item_shape)
        if merged and not non_dict_items:
            return [dict(sorted(merged.items()))]
        unique = sorted({json.dumps(s, sort_keys=True) for s in non_dict_items + ([merged] if merged else [])})
        return [json.loads(u) for u in unique][:1] if unique else []
    return f"<{type(value).__name__}>"


def normalize_target(kind: TargetKind, spec: Any) -> Any:
    if kind == "schema":
        return spec
    if kind == "sample":
        return shape(spec)
    if kind == "description":
        return str(spec).strip().lower()
    raise ValueError(f"Unknown target kind: {kind!r}")


def build_key(
    *,
    name: str | None,
    source: Any,
    target_kind: TargetKind,
    target_spec: Any,
) -> str:
    if name:
        return f"name:{name}"
    payload = json.dumps(
        [shape(source), target_kind, normalize_target(target_kind, target_spec)],
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"hash:{digest}"
