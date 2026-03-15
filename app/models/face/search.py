from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


SEARCH_TIMEZONE = timezone(timedelta(hours=3))


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_optional_int(value: Any) -> Optional[int]:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
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


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _as_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize_colors(value: Any) -> List[str]:
    if isinstance(value, list):
        return [_as_text(item) for item in value if _as_text(item)]

    text = _as_text(value)
    if not text:
        return []

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [_as_text(item) for item in parsed if _as_text(item)]

    delimiter = "|" if "|" in text else ","
    if delimiter in text:
        return [part.strip() for part in text.split(delimiter) if part.strip()]
    return [text]


def _embedding_payload(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value)


def _iso_text(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=SEARCH_TIMEZONE)
        else:
            value = value.astimezone(SEARCH_TIMEZONE)
        return value.isoformat(timespec="seconds")
    text = str(value).strip()
    return text or None


def _to_search_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=SEARCH_TIMEZONE)
    return value.astimezone(SEARCH_TIMEZONE)


@dataclass
class FaceSearchPayload:
    start: int = 0
    length: int = 50
    date_from: Optional[Any] = None
    date_to: Optional[Any] = None
    embedding: Any = ""
    age_from: int = 0
    age_to: int = 100
    gender: str = ""
    top_color: List[str] = field(default_factory=list)
    bottom_color: List[str] = field(default_factory=list)
    match: float = 60.0
    camera_ids: List[int] = field(default_factory=list)
    blacklist: bool = False
    whitelist: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": int(self.start),
            "length": int(self.length),
            "date_from": _iso_text(self.date_from),
            "date_to": _iso_text(self.date_to),
            "embedding": _embedding_payload(self.embedding),
            "age_from": int(self.age_from),
            "age_to": int(self.age_to),
            "gender": _as_text(self.gender) or None,
            "top_color": [color for color in (_as_text(item) for item in self.top_color) if color],
            "bottom_color": [color for color in (_as_text(item) for item in self.bottom_color) if color],
            "match": float(self.match or 0),
            "camera_ids": [int(item) for item in self.camera_ids if _as_int(item, 0) > 0],
            "blacklist": bool(self.blacklist),
            "whitelist": bool(self.whitelist),
        }


@dataclass
class FaceEmbeddingResult:
    embedding: Any = ""
    image_url: str = ""
    crop_image_url: str = ""
    raw: Any = None


@dataclass
class FaceSearchResult:
    id: int = 0
    record_type: str = ""
    filename: str = ""
    camera_id: int = 0
    camera_name: str = ""
    ip: str = ""
    port: int = 0
    gender: str = ""
    age: Optional[int] = None
    similarity: float = 0.0
    top_color: List[str] = field(default_factory=list)
    bottom_color: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    created_raw: str = ""
    is_blacklist: bool = False
    is_whitelist: bool = False
    image_url: str = ""
    crop_image_url: str = ""
    face_url: str = ""
    note: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "FaceSearchResult":
        nested_camera = raw.get("camera") if isinstance(raw.get("camera"), dict) else {}
        created_raw = (
            _as_text(raw.get("created"))
            or _as_text(raw.get("created_at"))
            or _as_text(raw.get("timestamp"))
            or _as_text(raw.get("datetime"))
            or _as_text(raw.get("date"))
        )
        camera_id = _as_int(raw.get("cam_id") or raw.get("camera_id") or nested_camera.get("id"), 0)
        return cls(
            id=_as_int(raw.get("id"), 0),
            record_type=_as_text(raw.get("type") or raw.get("record_type") or raw.get("source")),
            filename=_as_text(raw.get("filename") or raw.get("file") or raw.get("image")),
            camera_id=camera_id,
            camera_name=(
                _as_text(raw.get("camera_name"))
                or _as_text(nested_camera.get("name"))
                or (f"Camera #{camera_id}" if camera_id > 0 else "Unknown Camera")
            ),
            ip=_as_text(raw.get("ip") or nested_camera.get("ip") or nested_camera.get("camera_ip")),
            port=_as_int(raw.get("port") or nested_camera.get("port") or nested_camera.get("camera_port"), 0),
            gender=_as_text(raw.get("gender")),
            age=_as_optional_int(raw.get("age")),
            similarity=_as_float(raw.get("similarity") or raw.get("match") or raw.get("confidence"), 0.0),
            top_color=_normalize_colors(raw.get("top_color") or raw.get("face_color")),
            bottom_color=_normalize_colors(raw.get("bottom_color") or raw.get("hair_color")),
            created_at=_as_datetime(created_raw),
            created_raw=created_raw,
            is_blacklist=_as_bool(raw.get("blacklist") or raw.get("is_blacklist")),
            is_whitelist=_as_bool(raw.get("whitelist") or raw.get("is_whitelist")),
            image_url=_as_text(raw.get("image_url") or raw.get("image") or raw.get("url")),
            crop_image_url=_as_text(raw.get("crop_face") or raw.get("cropped_face") or raw.get("crop_image")),
            face_url=_as_text(raw.get("face") or raw.get("full_image") or raw.get("frame_url")),
            note=_as_text(raw.get("note") or raw.get("detail")),
            raw=dict(raw),
        )

    @property
    def similarity_text(self) -> str:
        if self.similarity <= 0:
            return "-"
        if float(self.similarity).is_integer():
            return f"{int(self.similarity)}%"
        return f"{self.similarity:.1f}%"

    @property
    def created_text(self) -> str:
        if self.created_at is None:
            return self.created_raw or "-"
        try:
            return _to_search_timezone(self.created_at).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return self.created_at.strftime("%Y-%m-%d %H:%M")

    @property
    def top_color_text(self) -> str:
        return ", ".join(self.top_color) if self.top_color else "-"

    @property
    def bottom_color_text(self) -> str:
        return ", ".join(self.bottom_color) if self.bottom_color else "-"
