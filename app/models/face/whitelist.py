from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from typing import Any, Dict, List, Optional


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


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _parse_datetime(value: Any) -> Optional[datetime]:
    text = _as_text(value)
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _normalize_camera_ids(value: Any) -> List[int]:
    if value in (None, "", []):
        return []

    raw_items: List[Any]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = [item.strip() for item in text.strip("[]").split(",")]
            raw_items = parsed if isinstance(parsed, list) else [parsed]
        elif "," in text:
            raw_items = [item.strip() for item in text.split(",")]
        else:
            raw_items = [text]
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = [value]

    normalized: List[int] = []
    for item in raw_items:
        candidate = item
        if isinstance(item, dict):
            candidate = item.get("id") or item.get("camera_id") or item.get("value")
        camera_id = _as_optional_int(candidate)
        if camera_id is not None and camera_id > 0:
            normalized.append(camera_id)
    return normalized


def _extract_preview_images(raw: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    sources = raw.get("preview_images")
    if not isinstance(sources, list):
        sources = raw.get("photos")
    if not isinstance(sources, list):
        sources = raw.get("images")
    if not isinstance(sources, list):
        sources = raw.get("templates")

    if not isinstance(sources, list):
        return values

    for item in sources:
        if isinstance(item, dict):
            candidate = (
                item.get("image_url")
                or item.get("image")
                or item.get("url")
                or item.get("file")
                or item.get("filename")
            )
        else:
            candidate = item
        text = _as_text(candidate)
        if text:
            values.append(text)
    return values


def _extract_camera_names(raw: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    cameras = raw.get("cameras")
    if isinstance(cameras, list):
        for item in cameras:
            if not isinstance(item, dict):
                continue
            name = _as_text(item.get("name") or item.get("camera_name"))
            if name:
                names.append(name)

    direct = raw.get("camera")
    if isinstance(direct, str) and direct.strip():
        names.extend([part.strip() for part in direct.split(",") if part.strip()])
    elif isinstance(direct, list):
        for item in direct:
            if isinstance(item, dict):
                name = _as_text(item.get("name") or item.get("camera_name"))
            else:
                name = _as_text(item)
            if name:
                names.append(name)
    return names


@dataclass
class FaceWhitelistTemplate:
    template_id: str = ""
    image_url: str = ""
    created_at: Optional[datetime] = None
    created_text: str = ""

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "FaceWhitelistTemplate":
        created = raw.get("created_at") or raw.get("created") or raw.get("date")
        created_at = _parse_datetime(created)
        return cls(
            template_id=_as_text(raw.get("template_id") or raw.get("id")),
            image_url=_as_text(
                raw.get("image_url")
                or raw.get("image")
                or raw.get("url")
                or raw.get("file")
                or raw.get("filename")
            ),
            created_at=created_at,
            created_text=created_at.strftime("%Y-%m-%d %H:%M") if created_at else _as_text(created),
        )


@dataclass
class FaceWhitelistPayload:
    name: str = ""
    face_color: str = ""
    hair_color: str = ""
    gender: str = ""
    age: Optional[int] = None
    match: float = 60.0
    camera_ids: List[int] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": self.name,
            "gender": self.gender,
            "face_color": self.face_color,
            "hair_color": self.hair_color,
            "similarity": float(self.match),
            "match": float(self.match),
            "camera_ids": [int(item) for item in self.camera_ids if int(item) > 0],
            "note": self.note,
        }
        if self.age is not None:
            payload["age"] = int(self.age)
        return payload


@dataclass
class FaceWhitelistEntry:
    id: int = 0
    person_id: str = ""
    name: str = ""
    image_url: str = ""
    preview_images: List[str] = field(default_factory=list)
    image_count: int = 0
    similarity: float = 60.0
    gender: str = ""
    age: Optional[int] = None
    face_color: str = ""
    hair_color: str = ""
    note: str = ""
    camera_ids: List[int] = field(default_factory=list)
    camera_names: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "FaceWhitelistEntry":
        person_id = _as_text(raw.get("person_id") or raw.get("id"))
        preview_images = _extract_preview_images(raw)
        image_url = _as_text(
            raw.get("image")
            or raw.get("image_url")
            or raw.get("face")
            or raw.get("photo")
            or (preview_images[0] if preview_images else "")
        )
        note = _as_text(raw.get("note") or raw.get("Note"))
        return cls(
            id=_as_int(raw.get("id") or raw.get("person_id"), 0),
            person_id=person_id,
            name=_as_text(raw.get("name") or raw.get("fullname")),
            image_url=image_url,
            preview_images=preview_images,
            image_count=max(
                _as_int(raw.get("image_count") or raw.get("photos_count") or raw.get("template_count"), 0),
                len(preview_images),
            ),
            similarity=_as_float(raw.get("similarity") or raw.get("match"), 60.0),
            gender=_as_text(raw.get("gender")),
            age=_as_optional_int(raw.get("age")),
            face_color=_as_text(raw.get("face_color")),
            hair_color=_as_text(raw.get("hair_color")),
            note=note,
            camera_ids=_normalize_camera_ids(raw.get("camera_ids") or raw.get("cameras")),
            camera_names=_extract_camera_names(raw),
        )

    @property
    def identifier(self) -> str:
        return self.person_id or str(self.id or "")

    @property
    def similarity_text(self) -> str:
        return f"{self.similarity:.2f}%"

    @property
    def cameras_text(self) -> str:
        if self.camera_names:
            return ", ".join(self.camera_names)
        if self.camera_ids:
            return ", ".join(f"Camera #{camera_id}" for camera_id in self.camera_ids)
        return "All cameras"
