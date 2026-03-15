from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class PermissionResponse:
    id: int = 0
    name: str = ""
    comment: str = ""

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "PermissionResponse":
        return cls(
            id=_as_int(raw.get("id"), 0),
            name=str(raw.get("name") or raw.get("permission") or raw.get("slug") or "").strip(),
            comment=str(raw.get("comment") or raw.get("label") or "").strip(),
        )

    @property
    def display_name(self) -> str:
        return self.comment or self.name or f"Permission #{self.id or 0}"


@dataclass
class RolePayload:
    name: str = ""
    permission_ids: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "permission_ids": [int(item) for item in self.permission_ids if int(item) > 0],
        }


@dataclass
class RoleResponse:
    id: int = 0
    name: str = ""
    permissions: List[PermissionResponse] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "RoleResponse":
        raw_permissions = raw.get("permissions") if isinstance(raw.get("permissions"), list) else []
        if not raw_permissions and isinstance(raw.get("permission_ids"), list):
            raw_permissions = [
                {"id": permission_id, "name": f"Permission #{_as_int(permission_id, 0)}"}
                for permission_id in raw.get("permission_ids", [])
            ]
        return cls(
            id=_as_int(raw.get("id") or raw.get("role_id"), 0),
            name=str(raw.get("name") or "").strip(),
            permissions=[
                PermissionResponse.from_dict(item)
                for item in raw_permissions
                if isinstance(item, dict)
            ],
        )

    @property
    def permission_ids(self) -> List[int]:
        return [item.id for item in self.permissions if item.id > 0]


PermissionResponce = PermissionResponse
RoleResponce = RoleResponse
