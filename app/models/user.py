from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


@dataclass
class User:
    id: int = 0
    name: str = "Guest"
    department_id: Optional[int] = None
    is_superadmin: bool = False
    permissions: List[str] = field(default_factory=list)


@dataclass
class UserPayload:
    username: str = ""
    password: str = ""
    fullname: str = ""
    email: str = ""
    phone: str = ""
    area: str = ""
    role_id: int = 0
    department_id: int = 0

    def to_dict(self, include_password: bool = True) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "username": self.username,
            "fullname": self.fullname,
            "email": self.email,
            "phone": self.phone,
            "area": self.area,
            "role_id": int(self.role_id or 0),
            "department_id": int(self.department_id or 0),
        }
        if include_password:
            payload["password"] = self.password
        return payload


@dataclass
class UserResponse:
    username: str = ""
    password: str = ""
    fullname: str = ""
    email: str = ""
    phone: str = ""
    area: str = ""
    role_id: int = 0
    department_id: int = 0
    id: int = 0
    is_superadmin: bool = False
    is_active: bool = False
    role_name: str = ""
    department_name: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "UserResponse":
        role_raw = raw.get("role") if isinstance(raw.get("role"), dict) else {}
        department_raw = raw.get("department") if isinstance(raw.get("department"), dict) else {}
        return cls(
            username=_as_text(raw.get("username")),
            password=_as_text(raw.get("password")),
            fullname=_as_text(raw.get("fullname")),
            email=_as_text(raw.get("email")),
            phone=_as_text(raw.get("phone")),
            area=_as_text(raw.get("area")),
            role_id=_as_int(raw.get("role_id") or role_raw.get("id"), 0),
            department_id=_as_int(raw.get("department_id") or department_raw.get("id"), 0),
            id=_as_int(raw.get("id") or raw.get("user_id"), 0),
            is_superadmin=bool(raw.get("is_superadmin") or raw.get("is_super_admin")),
            is_active=bool(raw.get("is_active")),
            role_name=_as_text(raw.get("role_name") or role_raw.get("name")),
            department_name=_as_text(raw.get("department_name") or department_raw.get("name")),
            created_at=_parse_datetime(raw.get("created_at")),
            updated_at=_parse_datetime(raw.get("updated_at")),
        )


UserResponce = UserResponse
