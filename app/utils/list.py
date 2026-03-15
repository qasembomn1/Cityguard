from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

DEFAULT_LIST_KEYS: tuple[str, ...] = ("items", "data", "results")


def extract_dict_list(payload: Any, keys: Sequence[str] = DEFAULT_LIST_KEYS) -> list[dict[str, Any]]:
    """
    Extract a list of dict objects from common API payload shapes.

    Supported shapes:
    - `[{}, {}]`
    - `{"items": [...]}` / `{"data": [...]}` / `{"results": [...]}`
    - custom keys passed via `keys`
    """
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, Mapping):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

    return []
