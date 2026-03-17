from __future__ import annotations

import json
import sys
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from app.models.camera import Camera
from app.utils.env import resolve_http_base_url
from app.utils.list import extract_dict_list


def _base_url() -> str:
    return resolve_http_base_url()


def _auth_token() -> str:
    return (
        os.getenv("AUTH_TOKEN")
        or os.getenv("ACCESS_TOKEN")
        or os.getenv("TOKEN")
        or ""
    ).strip()


def _api_request_json(
    path: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    auth: bool = False,
) -> Any:
    normalized_path = path if path.startswith("/") else f"/{path}"
    url = f"{_base_url()}{normalized_path}"
    query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
    if query:
        url = f"{url}?{query}"

    headers = {"accept": "application/json"}
    if data is not None:
        headers["content-type"] = "application/json"
    if auth:
        token = _auth_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(
        url=url,
        method=method.upper(),
        data=body,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = response.read().decode("utf-8").strip()
            if not payload:
                return {}
            return json.loads(payload)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore").strip()
        raise RuntimeError(
            f"API request failed [{exc.code}] {method.upper()} {url}. {detail}".strip()
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Unable to reach API at {url}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON response from {url}.") from exc

class CameraService:
    def __init__(self) -> None:
        self._items: List[Camera] = []
        self._next_id = 1

    def list_cameras(self, department_id: Optional[int] = None) -> List[Camera]:
        response = _api_request_json("/api/v1/cameras/")
        raw_items = extract_dict_list(response, keys=("items", "data", "results", "cameras"))
        if not raw_items and isinstance(response, dict):
            raise RuntimeError("Camera API response did not contain a valid camera list.")
        self._items = [self._normalize_camera(raw, idx) for idx, raw in enumerate(raw_items, start=1)]
        self._next_id = max((cam.id for cam in self._items), default=0) + 1
        return list(self._items)

    def _pick_nested_dict(self, raw: Dict[str, Any], keys: tuple[str, ...]) -> Optional[Dict[str, Any]]:
        for key in keys:
            value = raw.get(key)
            if isinstance(value, dict):
                return value
        return None

    def _pick_client_id(
        self,
        raw: Dict[str, Any],
        id_keys: tuple[str, ...],
        nested_keys: tuple[str, ...],
    ) -> Optional[int]:
        for key in id_keys:
            value = self._as_optional_int(raw.get(key))
            if value is not None:
                return value

        nested = self._pick_nested_dict(raw, nested_keys)
        if nested is None:
            return None

        for key in ("id", "client_id"):
            value = self._as_optional_int(nested.get(key))
            if value is not None:
                return value
        return None

    def _normalize_camera(self, raw: Dict[str, Any], fallback_id: int) -> Camera:
        camera_type_id = raw.get("camera_type_id")
        if camera_type_id is None and isinstance(raw.get("camera_type"), dict):
            camera_type_id = raw["camera_type"].get("id")

        client_1 = self._pick_nested_dict(
            raw,
            ("client_1", "client1", "primary_client", "process_client", "client"),
        )
        client_2 = self._pick_nested_dict(
            raw,
            ("client_2", "client2", "secondary_client", "failover_client"),
        )
        client_3 = self._pick_nested_dict(
            raw,
            ("client_3", "client3", "record_client", "recorder_client", "recording_client"),
        )

        return Camera(
            id=self._as_int(raw.get("id"), fallback_id),
            name=str(raw.get("name") or f"Camera {fallback_id}"),
            client_id_1=self._pick_client_id(
                raw,
                ("client_id_1", "client_1_id", "primary_client_id", "process_client_id"),
                ("client_1", "client1", "primary_client", "process_client", "client"),
            ),
            client_id_2=self._pick_client_id(
                raw,
                ("client_id_2", "client_2_id", "secondary_client_id", "failover_client_id"),
                ("client_2", "client2", "secondary_client", "failover_client"),
            ),
            client_id_3=self._pick_client_id(
                raw,
                ("client_id_3", "client_3_id", "record_client_id", "recorder_client_id", "recording_client_id"),
                ("client_3", "client3", "record_client", "recorder_client", "recording_client"),
            ),
            client_1=client_1,
            client_2=client_2,
            client_3=client_3,
            access_control_id=self._as_optional_int(raw.get("access_control_id")),
            door_number=self._as_optional_int(raw.get("door_number")),
            roi=str(raw.get("roi") or ""),
            map_pos=str(raw.get("map_pos") or ""),
            is_record=self._as_bool(raw.get("is_record")),
            is_process=self._as_bool(raw.get("is_process")),
            is_live=self._as_bool(raw.get("is_live"), True),
            is_ptz=self._as_bool(raw.get("is_ptz")),
            forward_stream=self._as_bool(raw.get("forward_stream")),
            is_ai_cam=self._as_bool(raw.get("is_ai_cam")),
            fps_delay=self._as_int(raw.get("fps_delay"), 5),
            process_type=str(raw.get("process_type") or "lpr"),
            camera_type_id=self._as_optional_int(camera_type_id),
            camera_ip=str(raw.get("camera_ip") or raw.get("ip") or ""),
            camera_username=str(raw.get("camera_username") or raw.get("username") or ""),
            camera_password=str(raw.get("camera_password") or raw.get("password") or ""),
            camera_port=self._as_int(raw.get("camera_port"), 554),
            face_person_count=self._as_bool(raw.get("face_person_count")),
            face_color_detection=self._as_bool(raw.get("face_color_detection")),
            face_min_size=self._as_int(raw.get("face_min_size"), 5),
            face_max_size=self._as_int(raw.get("face_max_size"), 40),
            face_show_rect=self._as_bool(raw.get("face_show_rect")),
            face_count_line=str(raw.get("face_count_line") or ""),
            image=raw.get("image"),
            camera_type=raw.get("camera_type") if isinstance(raw.get("camera_type"), dict) else None,
            online=self._as_bool(raw.get("online"), self._as_bool(raw.get("is_live"))),
            total_in=self._as_int(raw.get("total_in")),
            total_out=self._as_int(raw.get("total_out")),
        )

    def _as_optional_int(self, value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _as_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _as_bool(self, value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "no", "n", "off", ""}:
                return False
        return default

    def add_camera(self, payload: Dict[str, Any]) -> Camera:
        response = _api_request_json(
            "/api/v1/cameras/create",
            method="POST",
            data=payload,
            auth=True,
        )
        self.list_cameras(None)
        if isinstance(response, dict):
            camera_id = self._as_optional_int(response.get("id"))
            if camera_id is not None:
                return self.get_camera(camera_id)
        if self._items:
            return self._items[-1]
        raise RuntimeError("Camera created but no camera data was returned.")

    def update_camera(self, payload: Dict[str, Any]) -> Camera:
        camera_id = payload["id"]
        _api_request_json(
            f"/api/v1/cameras/update/{camera_id}",
            method="PATCH",
            data=payload,
            auth=True,
        )
        self.list_cameras(None)
        return self.get_camera(camera_id)

    def delete_camera(self, camera_id: int) -> None:
        _api_request_json(
            f"/api/v1/cameras/delete/{camera_id}",
            method="DELETE",
            auth=True,
        )
        self._items = [c for c in self._items if c.id != camera_id]

    def get_camera(self, camera_id: int) -> Camera:
        for cam in self._items:
            if cam.id == camera_id:
                return cam
        raise ValueError(f"Camera {camera_id} not found")

    def update_camera_roi(self, camera_id: int, roi: str) -> Camera:
        _api_request_json(
            f"/api/v1/cameras/update_roi/{camera_id}",
            method="PATCH",
            params={"roi_data": roi},
            auth=True,
        )
        self.list_cameras(None)
        return self.get_camera(camera_id)

    def update_camera_countline(self, camera_id: int, countline: str) -> Camera:
        _api_request_json(
            f"/api/v1/cameras/update_count_line/{camera_id}",
            method="PATCH",
            params={"line_data": countline},
            auth=True,
        )
        self.list_cameras(None)
        return self.get_camera(camera_id)

    def get_camera_frame(self, camera_id: int) -> str:
        response = _api_request_json(
            "/api/v1/camera/camera_test",
            method="POST",
            params={"camera_id": camera_id},
            auth=True,
        )
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            nested_candidates: list[Any] = [
                response,
                response.get("data"),
                response.get("result"),
                response.get("payload"),
            ]
            for candidate in nested_candidates:
                if not isinstance(candidate, dict):
                    continue
                for key in ("image", "frame", "image_data", "image_url"):
                    value = candidate.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        return ""
