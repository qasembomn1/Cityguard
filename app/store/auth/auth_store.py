from __future__ import annotations

from typing import Optional

from app.models.auth import ActivationInfo
from app.models.client import Client
from app.models.user import User
from app.services.auth.auth_service import AuthService
from app.store._init_ import BaseStore


class AuthStore(BaseStore):
    def __init__(self, service: AuthService) -> None:
        super().__init__()
        self.service = service
        self.current_user: Optional[User] = None
        self.server_activation_info: Optional[ActivationInfo] = None
        self.client_activation_info: dict[int, ActivationInfo] = {}

    def load(self) -> None:
        try:
            self.current_user = self.service.get_current_user()
            self.server_activation_info = self.service.get_activation_info()
            self.changed.emit()
        except Exception as exc:
            self.emit_error(str(exc))

    def has_permission(self, permission: str) -> bool:
        if not self.current_user:
            return False
        if self.current_user.is_superadmin:
            return True
        return permission in self.current_user.permissions

    def clear(self) -> None:
        self.current_user = None
        self.server_activation_info = None
        self.client_activation_info = {}
        self.changed.emit()

    def get_client_activation_info(self, client: Client, silent: bool = False) -> ActivationInfo:
        try:
            info = self.service.get_activation_info(client)
            self.client_activation_info[int(client.id)] = info
            self.changed.emit()
            return info
        except Exception as exc:
            if not silent:
                self.emit_error(str(exc))
            return ActivationInfo(camera_limit=-1)

    def load_client_activation_infos(self, clients: list[Client]) -> None:
        updated: dict[int, ActivationInfo] = {}
        for client in clients:
            try:
                updated[int(client.id)] = self.service.get_activation_info(client)
            except Exception:
                updated[int(client.id)] = ActivationInfo(camera_limit=-1)
        self.client_activation_info.update(updated)
        self.changed.emit()

    def activate_client(self, client: Client, key_file_path: str) -> ActivationInfo:
        try:
            info = self.service.activate_client(client, key_file_path)
            self.client_activation_info[int(client.id)] = info
            self.emit_success(f"{client.name} activated successfully.")
            return info
        except Exception as exc:
            self.emit_error(str(exc))
            raise

    def activate_server(self, key_file_path: str) -> ActivationInfo:
        try:
            info = self.service.activate_server(key_file_path)
            self.server_activation_info = info
            self.emit_success("Server activated successfully.")
            return info
        except Exception as exc:
            self.emit_error(str(exc))
            raise
