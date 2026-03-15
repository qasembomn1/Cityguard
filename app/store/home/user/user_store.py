from __future__ import annotations

from typing import Any, Dict, List

from app.models.user import UserPayload, UserResponse
from app.services.home.user.user_service import UserService
from app.store._init_ import BaseStore


class UserStore(BaseStore):
    def __init__(self, service: UserService) -> None:
        super().__init__()
        self.service = service
        self.users: List[UserResponse] = []

    def load(self) -> List[UserResponse]:
        try:
            self.users = self.service.list_users()
            self.changed.emit()
            return list(self.users)
        except Exception as exc:
            self.emit_error(str(exc))
            return []

    def create_user(self, payload: Dict[str, Any]) -> None:
        try:
            message = self.service.create_user(UserPayload(**payload))
            self.users = self.service.list_users()
            self.emit_success(message)
        except Exception as exc:
            self.emit_error(str(exc))

    def update_user(self, user_id: int, payload: Dict[str, Any]) -> None:
        try:
            message = self.service.update_user(user_id, UserPayload(**payload))
            self.users = self.service.list_users()
            self.emit_success(message)
        except Exception as exc:
            self.emit_error(str(exc))

    def delete_user(self, user_id: int) -> None:
        try:
            message = self.service.delete_user(user_id)
            self.users = [item for item in self.users if item.id != user_id]
            self.emit_success(message)
        except Exception as exc:
            self.emit_error(str(exc))
