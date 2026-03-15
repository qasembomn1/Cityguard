from __future__ import annotations

from typing import Any, Dict, Optional

from app.models.profile import PasswordChangePayload, ProfileResponse, ProfileUpdatePayload
from app.services.home.user.profile_service import ProfileService
from app.store._init_ import BaseStore


class ProfileStore(BaseStore):
    def __init__(self, service: ProfileService) -> None:
        super().__init__()
        self.service = service
        self.profile: Optional[ProfileResponse] = None
        self.last_action: str = ""

    def load(self) -> Optional[ProfileResponse]:
        try:
            self.last_action = "load"
            self.profile = self.service.get_profile()
            self.changed.emit()
            return self.profile
        except Exception as exc:
            self.emit_error(str(exc))
            return None

    def update_profile(self, payload: Dict[str, Any]) -> Optional[ProfileResponse]:
        try:
            self.last_action = "profile"
            current = self.profile or self.service.get_profile()
            merged = current.to_update_payload().to_dict()
            for key in ("fullname", "email", "phone", "area", "role_id", "department_id"):
                if key in payload and payload[key] is not None:
                    merged[key] = payload[key]
            updated, message = self.service.update_profile(ProfileUpdatePayload(**merged))
            self.profile = updated
            self.emit_success(message)
            return updated
        except Exception as exc:
            self.emit_error(str(exc))
            return None

    def change_password(self, old_password: str, new_password: str) -> bool:
        try:
            self.last_action = "password"
            message = self.service.change_password(
                PasswordChangePayload(
                    old_password=old_password,
                    new_password=new_password,
                )
            )
            self.emit_success(message)
            return True
        except Exception as exc:
            self.emit_error(str(exc))
            return False
