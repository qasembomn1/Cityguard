from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.models.lpr.region import plate_region


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_text(value: Any) -> str:
    return str(value or "").strip()


@dataclass
class LprListCamera:
    id: int = 0
    name: str = ""

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "LprListCamera":
        return cls(
            id=_as_int(raw.get("id") or raw.get("camera_id"), 0),
            name=_as_text(raw.get("name") or raw.get("camera_name")),
        )


@dataclass
class LprListPayload:
    plate_no: str = ""
    color: str = ""
    region: str = ""
    type: str = ""
    note: str = ""
    name: str = ""
    apart_name: str = ""
    phone: str = ""
    car_model: str = ""
    car_type: str = ""
    user_id: int = 0
    camera_ids: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plate_no": self.plate_no,
            "color": self.color,
            "region": self.region,
            "type": self.type,
            "note": self.note,
            "name": self.name,
            "apart_name": self.apart_name,
            "phone": self.phone,
            "car_model": self.car_model,
            "car_type": self.car_type,
            "user_id": int(self.user_id or 0),
            "camera_ids": [int(item) for item in self.camera_ids if int(item) > 0],
        }


@dataclass
class LprListEntry:
    id: int = 0
    plate_no: str = ""
    color: str = ""
    region: str = ""
    type: str = ""
    note: str = ""
    name: str = ""
    apart_name: str = ""
    phone: str = ""
    car_model: str = ""
    car_type: str = ""
    user_id: int = 0
    cameras: List[LprListCamera] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "LprListEntry":
        raw_cameras = raw.get("cameras") if isinstance(raw.get("cameras"), list) else []
        if not raw_cameras and isinstance(raw.get("camera_ids"), list):
            raw_cameras = [
                {"id": camera_id, "name": f"Camera #{_as_int(camera_id, 0)}"}
                for camera_id in raw.get("camera_ids", [])
            ]

        user_raw = raw.get("user") if isinstance(raw.get("user"), dict) else {}
        plate_no = _as_text(raw.get("plate_no") or raw.get("plate") or raw.get("plate_number"))
        return cls(
            id=_as_int(raw.get("id") or raw.get("whitelist_id") or raw.get("blacklist_id"), 0),
            plate_no=plate_no,
            color=_as_text(raw.get("color")),
            region=plate_region(raw.get("region"), plate_no),
            type=_as_text(raw.get("type")),
            note=_as_text(raw.get("note")),
            name=_as_text(raw.get("name") or raw.get("fullname") or user_raw.get("fullname")),
            apart_name=_as_text(raw.get("apart_name") or raw.get("apartment_name")),
            phone=_as_text(raw.get("phone") or user_raw.get("phone")),
            car_model=_as_text(raw.get("car_model")),
            car_type=_as_text(raw.get("car_type")),
            user_id=_as_int(raw.get("user_id") or user_raw.get("id"), 0),
            cameras=[
                LprListCamera.from_dict(item)
                for item in raw_cameras
                if isinstance(item, dict)
            ],
        )

    @property
    def camera_ids(self) -> List[int]:
        return [item.id for item in self.cameras if item.id > 0]
