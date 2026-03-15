from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional

from app.api.api_service import ApiService
from app.models.logs import UserLogResponse
from app.utils.list import extract_dict_list


class UserLogService:
    def __init__(self, api: ApiService | None = None) -> None:
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
        raise RuntimeError("No user log API attempts configured.")

    def _extract_items(self, payload: Any) -> List[Dict[str, Any]]:
        items = extract_dict_list(payload, keys=("items", "data", "results", "logs", "user_logs"))
        if items:
            return items

        if isinstance(payload, dict):
            for key in ("data", "result", "payload"):
                nested = payload.get(key)
                nested_items = extract_dict_list(
                    nested,
                    keys=("items", "data", "results", "logs", "user_logs"),
                )
                if nested_items:
                    return nested_items
            if "id" in payload and "action" in payload:
                return [payload]
        elif isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def list_user_logs(
        self,
        user_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        action: Optional[str] = None,
    ) -> List[UserLogResponse]:
        params = {
            "user_id": user_id,
            "start_date": start_date,
            "end_date": end_date,
            "action": action,
        }
        payload = self._request_with_fallback(
            (
                ("GET", "/api/v1/logs/user_log"),
                ("GET", "/api/v1/logs/user_log/"),
            ),
            params=params,
        )
        return [
            UserLogResponse.from_dict(item)
            for item in self._extract_items(payload)
            if isinstance(item, dict)
        ]
