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


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _iso_text(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=SEARCH_TIMEZONE)
        else:
            value = value.astimezone(SEARCH_TIMEZONE)
        return value.isoformat(timespec="seconds")
    return _as_text(value) or None


@dataclass
class LprRepeatedPayload:
    date_from: Optional[Any] = None
    date_to: Optional[Any] = None
    camera_ids: List[int] = field(default_factory=list)
    repeated_number: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date_from": _iso_text(self.date_from),
            "date_to": _iso_text(self.date_to),
            "camera_ids": [int(item) for item in self.camera_ids if _as_int(item, 0) > 0],
            "repeated_number": max(1, int(self.repeated_number or 1)),
        }


@dataclass
class LprRepeatedResult:
    id: str = ""
    number: str = ""
    color: str = ""
    plate_type: str = ""
    region: str = ""
    count: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "LprRepeatedResult":
        plate_number = (
            _as_text(raw.get("number"))
            or _as_text(raw.get("plate_no"))
            or _as_text(raw.get("plate"))
            or _as_text(raw.get("name"))
        )
        return cls(
            id=_as_text(raw.get("id") or plate_number),
            number=plate_number,
            color=_as_text(raw.get("color") or raw.get("color_name") or raw.get("plate_color")),
            plate_type=_as_text(raw.get("type") or raw.get("plate_type")),
            region=plate_region(raw.get("region"), plate_number),
            count=_as_int(
                raw.get("cnt")
                or raw.get("count")
                or raw.get("repeated_count")
                or raw.get("repeated_number"),
                0,
            ),
            raw=dict(raw),
        )

    @property
    def count_text(self) -> str:
        return str(self.count or 0)
