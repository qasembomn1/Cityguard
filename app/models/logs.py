from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_datetime(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class LogUser:
    id: int = 0
    fullname: str = ""
    username: str = ""

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "LogUser":
        return cls(
            id=_as_int(raw.get("id"), 0),
            fullname=str(raw.get("fullname") or raw.get("name") or "").strip(),
            username=str(raw.get("username") or "").strip(),
        )

    @property
    def display_name(self) -> str:
        return self.fullname or self.username or f"User #{self.id or 0}"


@dataclass
class UserLogResponse:
    id: int = 0
    action: str = ""
    detail: str = ""
    created_at: Optional[datetime] = None
    user: LogUser = field(default_factory=LogUser)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "UserLogResponse":
        nested_user = raw.get("user")
        if not isinstance(nested_user, dict):
            nested_user = {}
        if not nested_user:
            nested_user = {
                "id": raw.get("user_id"),
                "fullname": raw.get("fullname") or raw.get("user_fullname") or raw.get("name"),
                "username": raw.get("username"),
            }
        return cls(
            id=_as_int(raw.get("id"), 0),
            action=str(raw.get("action") or "").strip(),
            detail=str(raw.get("detail") or raw.get("message") or "").strip(),
            created_at=_as_datetime(raw.get("created_at") or raw.get("created") or raw.get("timestamp")),
            user=LogUser.from_dict(nested_user),
        )

    @property
    def created_at_text(self) -> str:
        if self.created_at is None:
            return "-"
        try:
            return self.created_at.astimezone().strftime("%Y-%m-%d %H:%M")
        except Exception:
            return self.created_at.strftime("%Y-%m-%d %H:%M")


LogUserResponse = LogUser
UserLogResponce = UserLogResponse


@dataclass
class LogSubject:
    id: int = 0
    name: str = ""
    subtitle: str = ""

    @classmethod
    def from_dict(cls, raw: Dict[str, Any], kind: str = "") -> "LogSubject":
        return cls(
            id=_as_int(raw.get("id") or raw.get(f"{kind}_id"), 0),
            name=str(
                raw.get("fullname")
                or raw.get("display_name")
                or raw.get("name")
                or raw.get("username")
                or ""
            ).strip(),
            subtitle=str(
                raw.get("username")
                or raw.get("ip")
                or raw.get("camera_ip")
                or raw.get("email")
                or ""
            ).strip(),
        )

    @property
    def display_name(self) -> str:
        if self.name:
            return self.name
        if self.id > 0:
            return f"#{self.id}"
        return "Unknown"


@dataclass
class ActivityLogEntry:
    id: int = 0
    action: str = ""
    detail: str = ""
    created_at: Optional[datetime] = None
    subject: LogSubject = field(default_factory=LogSubject)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any], entity_key: str) -> "ActivityLogEntry":
        nested = raw.get(entity_key)
        if not isinstance(nested, dict):
            nested = {}
        if not nested:
            nested = {
                "id": raw.get(f"{entity_key}_id"),
                "name": raw.get(f"{entity_key}_name") or raw.get("name"),
                "fullname": raw.get("fullname") or raw.get(f"{entity_key}_fullname"),
                "username": raw.get("username") or raw.get(f"{entity_key}_username"),
                "ip": raw.get("ip") or raw.get(f"{entity_key}_ip"),
                "camera_ip": raw.get("camera_ip"),
                "email": raw.get("email"),
            }
        return cls(
            id=_as_int(raw.get("id"), 0),
            action=str(raw.get("action") or "").strip(),
            detail=str(raw.get("detail") or raw.get("message") or "").strip(),
            created_at=_as_datetime(
                raw.get("created_at")
                or raw.get("created")
                or raw.get("timestamp")
                or raw.get("datetime")
            ),
            subject=LogSubject.from_dict(nested, entity_key),
        )

    @property
    def created_at_text(self) -> str:
        if self.created_at is None:
            return "-"
        try:
            return self.created_at.astimezone().strftime("%Y-%m-%d %H:%M")
        except Exception:
            return self.created_at.strftime("%Y-%m-%d %H:%M")
