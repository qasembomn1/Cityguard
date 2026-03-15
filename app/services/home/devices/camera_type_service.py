from __future__ import annotations

import os
from typing import Any, Dict, List

from app.api.api_service import ApiService
from app.models.camera import CameraType
from app.utils.list import extract_dict_list


class CameraTypeService:
    def __init__(self, api: ApiService | None = None) -> None:
        self.api = api or ApiService(os.getenv("Base_URL"))
        self._items: List[CameraType] = []

    def _as_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _as_text(self, value: Any) -> str:
        return str(value or "").strip()

    def _normalize_camera_type(self, raw: Dict[str, Any], fallback_id: int) -> CameraType:
        return CameraType(
            id=self._as_int(raw.get("id") or raw.get("camera_type_id"), fallback_id),
            name=self._as_text(raw.get("name") or raw.get("title") or f"Camera Type {fallback_id}"),
            protocol=self._as_text(raw.get("protocol")),
            main_url=self._as_text(raw.get("main_url")),
            sub_url=self._as_text(raw.get("sub_url")),
            ptz_url=self._as_text(raw.get("ptz_url")),
            network_url=self._as_text(raw.get("network_url")),
        )

    def _has_camera_type_content(self, raw: Dict[str, Any]) -> bool:
        if raw.get("id") not in (None, "") or raw.get("camera_type_id") not in (None, ""):
            return True
        for key in ("name", "title", "protocol", "main_url", "sub_url", "ptz_url", "network_url"):
            if self._as_text(raw.get(key)):
                return True
        return False

    def _sanitize_payload(self, payload: Dict[str, Any]) -> Dict[str, str]:
        return {
            "name": self._as_text(payload.get("name")),
            "protocol": self._as_text(payload.get("protocol")),
            "main_url": self._as_text(payload.get("main_url")),
            "sub_url": self._as_text(payload.get("sub_url")),
            "ptz_url": self._as_text(payload.get("ptz_url")),
            "network_url": self._as_text(payload.get("network_url")),
        }

    def _extract_message(self, payload: Any, default: str) -> str:
        if isinstance(payload, str) and payload.strip():
            return payload.strip()
        if isinstance(payload, dict):
            for key in ("message", "detail", "status", "result"):
                value = payload.get(key)
                if value:
                    return str(value).strip()
        return default

    def get_all_camera_types(self) -> List[CameraType]:
        payload = self.api.get("/api/v1/camera_types/", auth=True)
        items = extract_dict_list(payload, keys=("items", "data", "results", "camera_types"))
        if not items and isinstance(payload, dict):
            single = payload.get("camera_type")
            if isinstance(single, dict):
                items = [single]
        items = [raw for raw in items if self._has_camera_type_content(raw)]

        self._items = [
            self._normalize_camera_type(raw, idx)
            for idx, raw in enumerate(items, start=1)
        ]
        return list(self._items)

    def create_camera_type(self, payload: Dict[str, Any]) -> str:
        response = self.api.post(
            "/api/v1/camera_types/create",
            data=self._sanitize_payload(payload),
            auth=True,
        )
        return self._extract_message(response, "Camera type added successfully.")

    def update_camera_type(self, camera_type_id: int, payload: Dict[str, Any]) -> str:
        response = self.api.patch(
            f"/api/v1/camera_types/update/{camera_type_id}",
            data=self._sanitize_payload(payload),
            auth=True,
        )
        return self._extract_message(response, "Camera type updated successfully.")

    def delete_camera_type(self, camera_type_id: int) -> str:
        response = self.api.delete(
            f"/api/v1/camera_types/delete/{camera_type_id}",
            auth=True,
        )
        self._items = [item for item in self._items if item.id != camera_type_id]
        return self._extract_message(response, "Camera type deleted successfully.")
