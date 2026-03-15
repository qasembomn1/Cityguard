from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
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


def _as_date_text(value: Any) -> Optional[str]:
    text = _as_text(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    for candidate in (normalized, normalized.replace("T", " ")):
        try:
            return datetime.fromisoformat(candidate).date().isoformat()
        except ValueError:
            continue
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date().isoformat()
        except ValueError:
            continue
    if len(text) >= 10:
        prefix = text[:10]
        try:
            return datetime.strptime(prefix, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None
    return None


@dataclass
class RecordSetting:
    valid_space: int = 0
    save_path: str = ""
    quality: str = "normal"
    is_remove: bool = False
    is_record: bool = False
    fps_delay: int = 0
    media_server_ip: str = ""
    media_server_port: int = 0
    server_public_ip: str = ""
    server_public_port: int = 0
    db_limit_days: int = 0
    backup_days: int = 0
    backup_path: str = ""
    backup_last_date: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "RecordSetting":
        return cls(
            valid_space=_as_int(raw.get("valid_space"), 0),
            save_path=_as_text(raw.get("save_path")),
            quality=_as_text(raw.get("quality")).lower() or "normal",
            is_remove=_as_bool(raw.get("is_remove"), False),
            is_record=_as_bool(raw.get("is_record"), False),
            fps_delay=_as_int(raw.get("fps_delay"), 0),
            media_server_ip=_as_text(raw.get("media_server_ip")),
            media_server_port=_as_int(raw.get("media_server_port"), 0),
            server_public_ip=_as_text(raw.get("server_public_ip")),
            server_public_port=_as_int(raw.get("server_public_port"), 0),
            db_limit_days=_as_int(raw.get("db_limit_days"), 0),
            backup_days=_as_int(raw.get("backup_days"), 0),
            backup_path=_as_text(raw.get("backup_path")),
            backup_last_date=_as_date_text(raw.get("backup_last_date")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid_space": int(self.valid_space or 0),
            "save_path": self.save_path.strip(),
            "quality": (self.quality or "normal").strip().lower(),
            "is_remove": bool(self.is_remove),
            "is_record": bool(self.is_record),
            "fps_delay": int(self.fps_delay or 0),
            "media_server_ip": self.media_server_ip.strip(),
            "media_server_port": int(self.media_server_port or 0),
            "server_public_ip": self.server_public_ip.strip(),
            "server_public_port": int(self.server_public_port or 0),
            "db_limit_days": int(self.db_limit_days or 0),
            "backup_days": int(self.backup_days or 0),
            "backup_path": self.backup_path.strip(),
            "backup_last_date": self.backup_last_date or None,
        }


@dataclass
class AlarmSetting:
    blacklist_date: Optional[str] = None
    repeated_date: Optional[str] = None
    blacklist_alarm: bool = False

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "AlarmSetting":
        return cls(
            blacklist_date=_as_date_text(raw.get("blacklist_date")),
            repeated_date=_as_date_text(raw.get("repeated_date")),
            blacklist_alarm=_as_bool(raw.get("blacklist_alarm"), False),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blacklist_date": self.blacklist_date or None,
            "repeated_date": self.repeated_date or None,
            "blacklist_alarm": bool(self.blacklist_alarm),
        }


@dataclass
class RepeatedSetting:
    repeated_cars: int = 0
    in_time: int = 0

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "RepeatedSetting":
        return cls(
            repeated_cars=_as_int(raw.get("repeated_cars"), 0),
            in_time=_as_int(raw.get("in_time"), 0),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repeated_cars": int(self.repeated_cars or 0),
            "in_time": int(self.in_time or 0),
        }
