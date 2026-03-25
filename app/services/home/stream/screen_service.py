from __future__ import annotations

import os
import re
from math import isqrt
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from app.api.api_service import ApiService
from app.models.screen import ScreenCamera, ScreenResponse
from app.utils.list import extract_dict_list


class ScreenService:
    def __init__(self, api: ApiService | None = None) -> None:
        self.api = api or ApiService(os.getenv("Base_URL"))
        self._items: List[ScreenResponse] = []

    def _as_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _as_grid_size(self, value: Any, default: int = 2) -> int:
        if isinstance(value, str):
            matches = re.findall(r"\d+", value)
            if len(matches) >= 2:
                left = self._as_int(matches[0], default)
                right = self._as_int(matches[1], default)
                if left > 0 and left == right:
                    return max(2, min(8, left))
            if len(matches) == 1:
                value = matches[0]

        size = self._as_int(value, default)
        if size <= 0:
            return default
        if 2 <= size <= 8:
            return size

        root = isqrt(size)
        if root * root == size and 2 <= root <= 8:
            return root
        return default

    def _as_bool(self, value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default

    def _screen_is_main(self, raw: Dict[str, Any]) -> bool:
        for key in ("is_main", "main", "is_default", "default"):
            if key in raw and raw.get(key) is not None:
                return self._as_bool(raw.get(key), False)
        return False

    def _infer_grid_size_from_cameras(self, cameras: List[ScreenCamera], default: int = 2) -> int:
        if not cameras:
            return default
        highest_index = max((camera.index for camera in cameras), default=-1)
        if highest_index < 0:
            return default
        slots = highest_index + 1
        root = isqrt(slots)
        if root * root == slots and 2 <= root <= 8:
            return root
        while root * root < slots:
            root += 1
        return max(2, min(8, root))

    def _as_datetime(self, value: Any) -> Optional[datetime]:
        raw = str(value or "").strip()
        if not raw:
            return None
        normalized = raw.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None

    def _request_with_fallback(
        self,
        attempts: Iterable[tuple[str, str]],
        data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        last_exc: Exception | None = None
        for method, path in attempts:
            try:
                return self.api.request(method, path, data=data, auth=True)
            except Exception as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No screen API attempts configured.")

    def _normalize_camera(self, raw: Dict[str, Any], fallback_index: int) -> ScreenCamera:
        nested_camera = raw.get("camera")
        if not isinstance(nested_camera, dict):
            nested_camera = {}
        return ScreenCamera(
            camera_id=self._as_int(
                raw.get("camera_id") or raw.get("id") or nested_camera.get("id"),
                0,
            ),
            index=self._as_int(raw.get("index") or raw.get("camera_index"), fallback_index),
            name=str(
                raw.get("name")
                or raw.get("camera_name")
                or nested_camera.get("name")
                or ""
            ).strip(),
            camera_ip=str(
                raw.get("camera_ip")
                or raw.get("ip")
                or nested_camera.get("camera_ip")
                or nested_camera.get("ip")
                or ""
            ).strip(),
        )

    def _normalize_screen(self, raw: Dict[str, Any], fallback_id: int) -> ScreenResponse:
        raw_cameras = (
            raw.get("cameras")
            or raw.get("screen_cameras")
            or raw.get("screen_camera")
            or raw.get("camera_assignments")
        )
        cameras_list = raw_cameras if isinstance(raw_cameras, list) else []
        if not cameras_list:
            raw_ids = raw.get("camera_ids")
            if isinstance(raw_ids, list):
                cameras_list = [
                    {"camera_id": camera_id, "index": index}
                    for index, camera_id in enumerate(raw_ids)
                ]
        cameras = [
            self._normalize_camera(item, idx)
            for idx, item in enumerate(cameras_list)
            if isinstance(item, dict)
        ]
        resolved_screen_type = self._as_grid_size(raw.get("screen_type"), 0)
        if resolved_screen_type <= 0:
            resolved_screen_type = self._infer_grid_size_from_cameras(cameras, 2)

        return ScreenResponse(
            id=self._as_int(raw.get("id"), fallback_id),
            screen_type=resolved_screen_type,
            is_main=self._screen_is_main(raw),
            created_at=self._as_datetime(raw.get("created_at") or raw.get("updated_at")),
            cameras=cameras,
        )

    def _extract_screen_items(self, payload: Any) -> List[Dict[str, Any]]:
        items = extract_dict_list(payload, keys=("items", "data", "results", "screens"))
        if items:
            return items

        if isinstance(payload, dict):
            for key in ("data", "result", "payload"):
                nested = payload.get(key)
                nested_items = extract_dict_list(nested, keys=("items", "data", "results", "screens"))
                if nested_items:
                    return nested_items
                if isinstance(nested, dict) and ("id" in nested or "screen_type" in nested):
                    return [nested]

            for key in ("screen", "screens"):
                nested = payload.get(key)
                if isinstance(nested, dict):
                    return [nested]
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]

            if "id" in payload or "screen_type" in payload:
                return [payload]

        return []

    def _normalize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        cameras: List[Dict[str, int]] = []
        raw_cameras = payload.get("cameras")
        if isinstance(raw_cameras, list):
            for index, item in enumerate(raw_cameras):
                if not isinstance(item, dict):
                    continue
                camera_id = self._as_int(item.get("camera_id") or item.get("id"), 0)
                if camera_id <= 0:
                    continue
                cameras.append(
                    {
                        "camera_id": camera_id,
                        "index": self._as_int(item.get("index"), index),
                    }
                )

        normalized = dict(payload)
        normalized["screen_type"] = str(self._as_grid_size(payload.get("screen_type"), 2))
        if "is_main" in normalized:
            normalized["is_main"] = self._as_bool(normalized.get("is_main"), False)
        if cameras:
            normalized["cameras"] = cameras
            normalized["camera_ids"] = [item["camera_id"] for item in cameras]
        if "screen_id" in normalized:
            normalized["screen_id"] = self._as_int(normalized.get("screen_id"), 0)
        return normalized

    def _refresh_cache(self) -> List[ScreenResponse]:
        self._items = self.list_screens()
        return list(self._items)

    def _find_cached(self, screen_id: int) -> Optional[ScreenResponse]:
        for item in self._items:
            if item.id == screen_id:
                return item
        return None

    def list_screens(self) -> List[ScreenResponse]:
        payload = self._request_with_fallback(
            (
                ("GET", "/api/v1/screens/list"),
                ("GET", "/api/v1/screens/list/"),
            )
        )
        items = self._extract_screen_items(payload)
        self._items = [
            self._normalize_screen(raw, idx)
            for idx, raw in enumerate(items, start=1)
        ]
        return list(self._items)

    def create_screen(self, payload: Dict[str, Any]) -> ScreenResponse:
        normalized_payload = self._normalize_payload(payload)
        response = self._request_with_fallback(
            (
                ("POST", "/api/v1/screens/create"),
                ("POST", "/api/v1/screens/create/"),
            ),
            data=normalized_payload,
        )

        created_id = 0
        if isinstance(response, dict):
            created_id = self._as_int(response.get("id") or response.get("screen_id"), 0)

        screens = self._refresh_cache()
        if created_id:
            found = self._find_cached(created_id)
            if found is not None:
                return found
        if isinstance(response, dict):
            extracted = self._extract_screen_items(response)
            if extracted:
                return self._normalize_screen(extracted[0], created_id or 1)
            if response.get("id") or response.get("screen_type"):
                return self._normalize_screen(response, created_id or 1)
        if screens:
            return max(screens, key=lambda item: item.id)
        raise RuntimeError("Screen created but no screen data was returned.")

    def update_screen(self, payload: Dict[str, Any]) -> ScreenResponse:
        normalized_payload = self._normalize_payload(payload)
        screen_id = self._as_int(normalized_payload.get("screen_id") or normalized_payload.get("id"), 0)
        if screen_id <= 0:
            raise ValueError("Screen ID is required for updates.")

        self._request_with_fallback(
            (
                ("PATCH", "/api/v1/screens/update"),
                ("PATCH", "/api/v1/screens/update/"),
            ),
            data=normalized_payload,
        )

        self._refresh_cache()
        found = self._find_cached(screen_id)
        if found is not None:
            return found
        raise RuntimeError(f"Screen {screen_id} updated but was not found in the refreshed list.")

    def add_camera_to_screen(self, screen_id: int, payload: Dict[str, Any]) -> ScreenResponse:
        self._request_with_fallback(
            (
                ("POST", f"/api/v1/screens/{screen_id}/cameras"),
                ("POST", f"/api/v1/screens/{screen_id}/cameras/"),
            ),
            data=payload,
        )
        self._refresh_cache()
        found = self._find_cached(screen_id)
        if found is not None:
            return found
        raise RuntimeError(f"Camera assignment saved but screen {screen_id} was not found.")

    def delete_screen(self, screen_id: int) -> None:
        self._request_with_fallback(
            (
                ("DELETE", f"/api/v1/screens/{screen_id}"),
                ("DELETE", f"/api/v1/screens/{screen_id}/"),
            )
        )
        self._items = [item for item in self._items if item.id != screen_id]
