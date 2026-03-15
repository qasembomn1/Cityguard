from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


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


def _as_datetime(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class ProfileUpdatePayload:
    fullname: str = ""
    email: str = ""
    phone: str = ""
    area: str = ""
    role_id: int = 0
    department_id: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fullname": self.fullname,
            "email": self.email,
            "phone": self.phone,
            "area": self.area,
            "role_id": self.role_id,
            "department_id": self.department_id,
        }


@dataclass
class PasswordChangePayload:
    old_password: str = ""
    new_password: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "old_password": self.old_password,
            "new_password": self.new_password,
        }


@dataclass
class ProfileResponse:
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
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "ProfileResponse":
        return cls(
            username=str(raw.get("username") or "").strip(),
            password=str(raw.get("password") or ""),
            fullname=str(raw.get("fullname") or "").strip(),
            email=str(raw.get("email") or "").strip(),
            phone=str(raw.get("phone") or "").strip(),
            area=str(raw.get("area") or "").strip(),
            role_id=_as_int(raw.get("role_id"), 0),
            department_id=_as_int(raw.get("department_id"), 0),
            id=_as_int(raw.get("id"), 0),
            is_superadmin=_as_bool(raw.get("is_superadmin"), False),
            is_active=_as_bool(raw.get("is_active"), False),
            created_at=_as_datetime(raw.get("created_at")),
            updated_at=_as_datetime(raw.get("updated_at")),
        )

    @property
    def display_name(self) -> str:
        return self.fullname or self.username or "User Profile"

    def to_update_payload(self) -> ProfileUpdatePayload:
        return ProfileUpdatePayload(
            fullname=self.fullname,
            email=self.email,
            phone=self.phone,
            area=self.area,
            role_id=self.role_id,
            department_id=self.department_id,
        )


ProfileResponce = ProfileResponse
