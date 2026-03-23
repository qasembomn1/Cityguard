from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.models.lpr.region import plate_region


SEARCH_TIMEZONE = timezone(timedelta(hours=3))


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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


def _color_names(value: Any) -> List[str]:
    if isinstance(value, list):
        return [_as_text(item) for item in value if _as_text(item)]
    text = _as_text(value)
    if not text:
        return []
    if "," in text:
        return [part.strip() for part in text.split(",") if part.strip()]
    return [text]


def _iso_text(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    parsed: Optional[datetime]
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        parsed = _as_datetime(text)
        if parsed is None:
            return text

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SEARCH_TIMEZONE)
    parsed_utc = parsed.astimezone(timezone.utc)
    return parsed_utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _to_search_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=SEARCH_TIMEZONE)
    return value.astimezone(SEARCH_TIMEZONE)


@dataclass
class LprSearchPayload:
    start: int = 0
    length: int = 300
    order_col: int = 0
    order: str = "asc"
    date_from: Optional[Any] = None
    date_to: Optional[Any] = None
    color_names: List[str] = field(default_factory=list)
    type: Optional[str] = None
    region: Optional[str] = None
    camera_ids: List[int] = field(default_factory=list)
    compare: Optional[str] = None
    plate_no: str = ""
    number_digits: Optional[int] = None
    conf: float = 0.0
    blacklist: bool = False
    whitelist: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": int(self.start),
            "length": int(self.length),
            "order_col": int(self.order_col),
            "order": _as_text(self.order) or "asc",
            "date_from": _iso_text(self.date_from),
            "date_to": _iso_text(self.date_to),
            "color_names": [name for name in (_as_text(item) for item in self.color_names) if name],
            "type": _as_text(self.type) or None,
            "region": _as_text(self.region) or None,
            "camera_ids": [int(item) for item in self.camera_ids if _as_int(item, 0) > 0],
            "compare": _as_text(self.compare) or None,
            "plate_no": _as_text(self.plate_no),
            "number_digits": int(self.number_digits) if self.number_digits not in (None, "") else None,
            "conf": float(self.conf or 0),
            "blacklist": bool(self.blacklist),
            "whitelist": bool(self.whitelist),
        }


@dataclass
class LprSearchResult:
    id: int = 0
    number: str = ""
    region: str = ""
    color_names: List[str] = field(default_factory=list)
    plate_type: str = ""
    confidence: float = 0.0
    camera_name: str = ""
    camera_id: int = 0
    filename: str = ""
    ip: str = ""
    port: int = 0
    map_pos: str = ""
    note: str = ""
    created_at: Optional[datetime] = None
    created_raw: str = ""
    is_blacklist: bool = False
    is_whitelist: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "LprSearchResult":
        nested_camera = raw.get("camera") if isinstance(raw.get("camera"), dict) else {}
        created_raw = (
            _as_text(raw.get("created"))
            or _as_text(raw.get("created_at"))
            or _as_text(raw.get("timestamp"))
            or _as_text(raw.get("datetime"))
        )
        plate_number = (
            _as_text(raw.get("number"))
            or _as_text(raw.get("plate_no"))
            or _as_text(raw.get("plate"))
            or _as_text(raw.get("name"))
        )
        return cls(
            id=_as_int(raw.get("id"), 0),
            number=plate_number,
            region=plate_region(raw.get("region"), plate_number),
            color_names=_color_names(raw.get("color_names") or raw.get("color")),
            plate_type=_as_text(raw.get("type") or raw.get("plate_type")),
            confidence=_as_float(raw.get("conf") or raw.get("confidence") or raw.get("score"), 0.0),
            camera_name=(
                _as_text(raw.get("camera_name"))
                or _as_text(nested_camera.get("name"))
                or f"Camera #{_as_int(raw.get('cam_id') or raw.get('camera_id') or nested_camera.get('id'), 0)}"
            ),
            camera_id=_as_int(raw.get("cam_id") or raw.get("camera_id") or nested_camera.get("id"), 0),
            filename=_as_text(raw.get("filename") or raw.get("file") or raw.get("image")),
            ip=_as_text(raw.get("ip") or nested_camera.get("ip") or nested_camera.get("camera_ip")),
            port=_as_int(raw.get("port") or nested_camera.get("port") or nested_camera.get("camera_port"), 0),
            map_pos=_as_text(raw.get("map_pos") or nested_camera.get("map_pos")),
            note=_as_text(raw.get("note") or raw.get("detail")),
            created_at=_as_datetime(created_raw),
            created_raw=created_raw,
            is_blacklist=_as_bool(raw.get("blacklist") or raw.get("is_blacklist")),
            is_whitelist=_as_bool(raw.get("whitelist") or raw.get("is_whitelist")),
            raw=dict(raw),
        )

    @property
    def color_text(self) -> str:
        return ", ".join(self.color_names) if self.color_names else "-"

    @property
    def confidence_text(self) -> str:
        if self.confidence <= 0:
            return "-"
        if float(self.confidence).is_integer():
            return f"{int(self.confidence)}%"
        return f"{self.confidence:.1f}%"

    @property
    def created_text(self) -> str:
        if self.created_at is None:
            return self.created_raw or "-"
        try:
            return _to_search_timezone(self.created_at).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return self.created_at.strftime("%Y-%m-%d %H:%M")
