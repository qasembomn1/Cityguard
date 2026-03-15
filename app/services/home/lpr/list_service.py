from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List

from app.api.api_service import ApiService
from app.models.lpr.list_entry import LprListEntry, LprListPayload
from app.utils.list import extract_dict_list


class LprRegistryService:
    def __init__(
        self,
        resource: str,
        entity_label: str,
        api: ApiService | None = None,
    ) -> None:
        self.resource = resource.strip().strip("/")
        self.entity_label = entity_label.strip() or "Record"
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
        raise RuntimeError(f"No API attempts configured for {self.resource}.")

    def _extract_items(self, payload: Any) -> List[Dict[str, Any]]:
        keys = (
            "items",
            "data",
            "results",
            "records",
            self.resource,
            self.resource.rstrip("s"),
        )
        items = extract_dict_list(payload, keys=keys)
        if items:
            return items
        if isinstance(payload, dict):
            for key in ("data", "result", "payload"):
                nested = payload.get(key)
                nested_items = extract_dict_list(nested, keys=keys)
                if nested_items:
                    return nested_items
            if "id" in payload and ("plate_no" in payload or "plate" in payload):
                return [payload]
        elif isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def _extract_message(self, payload: Any, default: str) -> str:
        if isinstance(payload, str) and payload.strip():
            return payload.strip()
        if isinstance(payload, dict):
            message = str(payload.get("message") or payload.get("detail") or payload.get("result") or "").strip()
            if message:
                return message
        return default

    def list_entries(self) -> List[LprListEntry]:
        payload = self._request_with_fallback(
            (
                ("GET", f"/api/v1/{self.resource}/"),
                ("GET", f"/api/v1/{self.resource}"),
            )
        )
        return [
            LprListEntry.from_dict(item)
            for item in self._extract_items(payload)
            if isinstance(item, dict)
        ]

    def create_entry(self, payload: Dict[str, Any] | LprListPayload) -> str:
        data = payload.to_dict() if isinstance(payload, LprListPayload) else dict(payload or {})
        response = self._request_with_fallback(
            (
                ("POST", f"/api/v1/{self.resource}/create"),
                ("POST", f"/api/v1/{self.resource}/create/"),
            ),
            data=data,
        )
        return self._extract_message(response, f"{self.entity_label} created successfully.")

    def update_entry(self, entry_id: int, payload: Dict[str, Any] | LprListPayload) -> str:
        data = payload.to_dict() if isinstance(payload, LprListPayload) else dict(payload or {})
        response = self._request_with_fallback(
            (
                ("PATCH", f"/api/v1/{self.resource}/update/{entry_id}"),
                ("PATCH", f"/api/v1/{self.resource}/update/{entry_id}/"),
            ),
            data=data,
        )
        return self._extract_message(response, f"{self.entity_label} updated successfully.")

    def delete_entry(self, entry_id: int) -> str:
        response = self._request_with_fallback(
            (
                ("DELETE", f"/api/v1/{self.resource}/delete/{entry_id}"),
                ("DELETE", f"/api/v1/{self.resource}/delete/{entry_id}/"),
            )
        )
        return self._extract_message(response, f"{self.entity_label} deleted successfully.")
