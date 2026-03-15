from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


REPORT_TIMEZONE = timezone(timedelta(hours=3))
REPORT_TYPES = {"lpr", "monthly"}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _iso_text(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=REPORT_TIMEZONE)
        else:
            value = value.astimezone(REPORT_TIMEZONE)
        return value.isoformat(timespec="seconds")
    return _as_text(value) or None


def _normalize_report_type(value: Any) -> str:
    normalized = _as_text(value).lower()
    return normalized if normalized in REPORT_TYPES else "lpr"


@dataclass
class LprReportPayload:
    date_from: Optional[Any] = None
    date_to: Optional[Any] = None
    camera_ids: List[int] = field(default_factory=list)
    report_type: str = "lpr"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date_from": _iso_text(self.date_from),
            "date_to": _iso_text(self.date_to),
            "camera_ids": [int(item) for item in self.camera_ids if _as_int(item, 0) > 0],
            "report_type": _normalize_report_type(self.report_type),
        }


@dataclass
class LprReportRow:
    row_no: int = 0
    camera_name: str = ""
    total_records: int = 0
    unique_vehicles: int = 0
    english_plates: int = 0
    taxi_plates: int = 0
    private_plates: int = 0
    transport_plates: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "LprReportRow":
        camera_raw = raw.get("camera")
        if isinstance(camera_raw, dict):
            camera_name = _as_text(camera_raw.get("name") or camera_raw.get("camera_name"))
        else:
            camera_name = ""

        camera_name = (
            camera_name
            or _as_text(raw.get("cam_name"))
            or _as_text(raw.get("camera_name"))
            or _as_text(raw.get("camera"))
            or _as_text(raw.get("period"))
            or _as_text(raw.get("month"))
            or _as_text(raw.get("month_name"))
            or _as_text(raw.get("date"))
        )

        return cls(
            row_no=_as_int(raw.get("no") or raw.get("row_no") or raw.get("id"), 0),
            camera_name=camera_name,
            total_records=_as_int(raw.get("total1") or raw.get("total_records") or raw.get("total"), 0),
            unique_vehicles=_as_int(raw.get("total2") or raw.get("unique_vehicles") or raw.get("unique"), 0),
            english_plates=_as_int(raw.get("total_english") or raw.get("english") or raw.get("english_plates"), 0),
            taxi_plates=_as_int(raw.get("total_taxi") or raw.get("taxi") or raw.get("taxi_plates"), 0),
            private_plates=_as_int(raw.get("total_private") or raw.get("private") or raw.get("private_plates"), 0),
            transport_plates=_as_int(raw.get("total_transport") or raw.get("transport") or raw.get("transport_plates"), 0),
            raw=dict(raw),
        )

    @property
    def camera_display(self) -> str:
        if self.camera_name:
            return self.camera_name
        if self.row_no > 0:
            return f"Row {self.row_no}"
        return "-"
