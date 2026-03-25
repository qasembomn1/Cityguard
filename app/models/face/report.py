from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.models._api_datetime import to_api_iso_text
from app.utils.list import extract_dict_list


REPORT_TIMEZONE = timezone(timedelta(hours=3))


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _iso_text(value: Any) -> Optional[str]:
    return to_api_iso_text(value, REPORT_TIMEZONE)


def _coerce_cell_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        parts: List[str] = []
        for key, nested in value.items():
            nested_text = _as_text(nested)
            if nested_text:
                parts.append(f"{key}: {nested_text}")
        return ", ".join(parts)
    if isinstance(value, list):
        parts = [_as_text(item) for item in value if _as_text(item)]
        return ", ".join(parts)
    return _as_text(value)


def _normalize_key(key: str) -> str:
    raw = _as_text(key).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "cam_name": "camera_name",
        "camera": "camera_name",
        "cam": "camera_name",
        "created": "created_at",
        "timestamp": "created_at",
        "datetime": "created_at",
    }
    return aliases.get(raw, raw)


@dataclass
class FaceReportPayload:
    date_from: Optional[Any] = None
    date_to: Optional[Any] = None
    camera_ids: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date_from": _iso_text(self.date_from),
            "date_to": _iso_text(self.date_to),
            "camera_ids": [int(item) for item in self.camera_ids if _as_int(item, 0) > 0],
        }


@dataclass
class FaceReportRow:
    values: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "FaceReportRow":
        values: Dict[str, Any] = {}
        for key, value in raw.items():
            normalized_key = _normalize_key(key)
            if normalized_key in values and values[normalized_key] not in (None, ""):
                continue
            values[normalized_key] = _coerce_cell_value(value)

        camera_raw = raw.get("camera")
        if "camera_name" not in values and isinstance(camera_raw, dict):
            camera_name = _as_text(camera_raw.get("name") or camera_raw.get("camera_name"))
            if camera_name:
                values["camera_name"] = camera_name

        return cls(values=values, raw=dict(raw))

    def table_dict(self) -> Dict[str, Any]:
        return dict(self.values)


@dataclass
class FaceReportResult:
    rows: List[FaceReportRow] = field(default_factory=list)
    message: str = ""


def extract_face_report_result(payload: Any) -> FaceReportResult:
    keys = ("items", "data", "results", "records", "report", "rows", "result")
    items = extract_dict_list(payload, keys=keys)
    if items:
        return FaceReportResult(rows=[FaceReportRow.from_dict(item) for item in items if isinstance(item, dict)])

    if isinstance(payload, dict):
        for key in ("data", "result", "payload"):
            nested = payload.get(key)
            nested_items = extract_dict_list(nested, keys=keys)
            if nested_items:
                return FaceReportResult(rows=[FaceReportRow.from_dict(item) for item in nested_items if isinstance(item, dict)])

        message = _as_text(payload.get("message") or payload.get("detail") or payload.get("status"))
        scalar_like = {
            _normalize_key(str(key)): _coerce_cell_value(value)
            for key, value in payload.items()
            if not isinstance(value, (dict, list))
        }
        if scalar_like and any(_as_text(value) for value in scalar_like.values()):
            return FaceReportResult(rows=[FaceReportRow(values=scalar_like, raw=dict(payload))], message=message)
        return FaceReportResult(message=message)

    if isinstance(payload, list):
        return FaceReportResult(rows=[FaceReportRow.from_dict(item) for item in payload if isinstance(item, dict)])

    if isinstance(payload, str):
        return FaceReportResult(message=payload.strip())

    return FaceReportResult()
