from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional

from app.api.api_service import ApiService
from app.models.logs import ActivityLogEntry
from app.utils.list import extract_dict_list


class ActivityLogService:
    def __init__(
        self,
        resource: str,
        entity_key: str,
        api: ApiService | None = None,
    ) -> None:
        self.resource = resource.strip().strip("/")
        self.entity_key = entity_key.strip()
        self.api = api or ApiService(os.getenv("Base_URL"))

    def _request_with_fallback(
        self,
        attempts: Iterable[tuple[str, str]],
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        last_exc: Exception | None = None
        for method, path in attempts:
            try:
                return self.api.request(method, path, params=params, auth=True)
            except Exception as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"No API attempts configured for {self.resource}.")

    def _extract_items(self, payload: Any) -> List[Dict[str, Any]]:
        keys = ("items", "data", "results", "logs", f"{self.resource}s", self.resource)
        items = extract_dict_list(payload, keys=keys)
        if items:
            return items
        if isinstance(payload, dict):
            for key in ("data", "result", "payload"):
                nested = payload.get(key)
                nested_items = extract_dict_list(nested, keys=keys)
                if nested_items:
                    return nested_items
            if "id" in payload and "action" in payload:
                return [payload]
        elif isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def list_logs(
        self,
        entity_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        action: Optional[str] = None,
    ) -> List[ActivityLogEntry]:
        params = {
            f"{self.entity_key}_id": entity_id,
            "action": action,
            "start_date": start_date,
            "end_date": end_date,
        }
        payload = self._request_with_fallback(
            (
                ("GET", f"/api/v1/logs/{self.resource}"),
                ("GET", f"/api/v1/logs/{self.resource}/"),
            ),
            params=params,
        )
        return [
            ActivityLogEntry.from_dict(item, self.entity_key)
            for item in self._extract_items(payload)
            if isinstance(item, dict)
        ]
