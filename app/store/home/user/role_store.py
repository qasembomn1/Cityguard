from __future__ import annotations

from typing import Any, Dict, List

from app.models.role import PermissionResponse, RolePayload, RoleResponse
from app.services.home.user.role_service import RoleService
from app.store._init_ import BaseStore


class RoleStore(BaseStore):
    def __init__(self, service: RoleService) -> None:
        super().__init__()
        self.service = service
        self.roles: List[RoleResponse] = []
        self.permissions: List[PermissionResponse] = []

    def load_roles(self) -> List[RoleResponse]:
        try:
            self.roles = self.service.list_roles()
            self.changed.emit()
            return list(self.roles)
        except Exception as exc:
            self.emit_error(str(exc))
            return []

    def load_permissions(self) -> List[PermissionResponse]:
        try:
            self.permissions = self.service.list_permissions()
            self.changed.emit()
            return list(self.permissions)
        except Exception as exc:
            self.emit_error(str(exc))
            return []

    def create_role(self, payload: Dict[str, Any]) -> None:
        try:
            message = self.service.create_role(RolePayload(**payload))
            self.roles = self.service.list_roles()
            self.emit_success(message)
        except Exception as exc:
            self.emit_error(str(exc))

    def update_role(self, role_id: int, payload: Dict[str, Any]) -> None:
        try:
            message = self.service.update_role(role_id, RolePayload(**payload))
            self.roles = self.service.list_roles()
            self.emit_success(message)
        except Exception as exc:
            self.emit_error(str(exc))

    def delete_role(self, role_id: int) -> None:
        try:
            message = self.service.delete_role(role_id)
            self.roles = [item for item in self.roles if item.id != role_id]
            self.emit_success(message)
        except Exception as exc:
            self.emit_error(str(exc))
