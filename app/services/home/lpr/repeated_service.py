from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List

from app.api.api_service import ApiService
from app.models.lpr.repeated import LprRepeatedPayload, LprRepeatedResult
from app.utils.list import extract_dict_list


class LprRepeatedService:
    def __init__(self, api: ApiService | None = None) -> None:
        self.api = api or ApiService(os.getenv("Base_URL"))

    def _request_with_fallback(
        self,
        attempts: Iterable[tuple[str, str]],
        data: Dict[str, Any] | None = None,
    ) -> Any:
        last_exc: Exception | None = None
        for method, path in attempts:
            try:
                return self.api.request(method, path, data=data, auth=True)
            except Exception as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No repeated-search API attempts configured.")

    def _extract_items(self, payload: Any) -> List[Dict[str, Any]]:
        items = extract_dict_list(payload, keys=("items", "data", "results", "records", "repeated"))
        if items:
            return items
        if isinstance(payload, dict):
            for key in ("data", "result", "payload"):
                nested = payload.get(key)
                nested_items = extract_dict_list(
                    nested,
                    keys=("items", "data", "results", "records", "repeated"),
                )
                if nested_items:
                    return nested_items
            if any(key in payload for key in ("number", "plate_no", "plate")):
                return [payload]
        elif isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def search(self, payload: Dict[str, Any] | LprRepeatedPayload) -> List[LprRepeatedResult]:
        data = payload.to_dict() if isinstance(payload, LprRepeatedPayload) else dict(payload or {})
        response = self._request_with_fallback(
            (
                ("POST", "/api/v1/repeated/"),
                ("POST", "/api/v1/repeated"),
            ),
            data=data,
        )
        return [
            LprRepeatedResult.from_dict(item)
            for item in self._extract_items(response)
            if isinstance(item, dict)
        ]
