from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class DepartmentCamera:
    id: int = 0
    name: str = ""

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "DepartmentCamera":
        return cls(
            id=_as_int(raw.get("id") or raw.get("camera_id"), 0),
            name=str(raw.get("name") or raw.get("camera_name") or "").strip(),
        )


@dataclass
class DepartmentPayload:
    name: str = ""
    camera_ids: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "camera_ids": [int(item) for item in self.camera_ids if int(item) > 0],
        }


@dataclass
class DepartmentResponse:
    id: int = 0
    name: str = ""
    cameras: List[DepartmentCamera] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "DepartmentResponse":
        raw_cameras = raw.get("cameras") if isinstance(raw.get("cameras"), list) else []
        if not raw_cameras and isinstance(raw.get("camera_ids"), list):
            raw_cameras = [
                {"id": camera_id, "name": f"Camera #{_as_int(camera_id, 0)}"}
                for camera_id in raw.get("camera_ids", [])
            ]
        return cls(
            id=_as_int(raw.get("id"), 0),
            name=str(raw.get("name") or "").strip(),
            cameras=[
                DepartmentCamera.from_dict(item)
                for item in raw_cameras
                if isinstance(item, dict)
            ],
        )

    @property
    def camera_ids(self) -> List[int]:
        return [item.id for item in self.cameras if item.id > 0]


DepartmentResponce = DepartmentResponse
