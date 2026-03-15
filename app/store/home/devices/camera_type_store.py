from __future__ import annotations

from typing import Any, Dict, List

from app.models.camera import CameraType
from app.services.home.devices.camera_type_service import CameraTypeService
from app.store._init_ import BaseStore


class CameraTypeStore(BaseStore):
    def __init__(self, service: CameraTypeService) -> None:
        super().__init__()
        self.service = service
        self.camera_types: List[CameraType] = []

    def load(self) -> List[CameraType]:
        try:
            self.camera_types = self.service.get_all_camera_types()
            self.changed.emit()
        except Exception as exc:
            self.emit_error(str(exc))
        return list(self.camera_types)

    def create_camera_type(self, payload: Dict[str, Any]) -> bool:
        try:
            message = self.service.create_camera_type(payload)
            self.camera_types = self.service.get_all_camera_types()
            self.emit_success(message)
            return True
        except Exception as exc:
            self.emit_error(str(exc))
            return False

    def update_camera_type(self, camera_type_id: int, payload: Dict[str, Any]) -> bool:
        try:
            message = self.service.update_camera_type(camera_type_id, payload)
            self.camera_types = self.service.get_all_camera_types()
            self.emit_success(message)
            return True
        except Exception as exc:
            self.emit_error(str(exc))
            return False

    def delete_camera_type(self, camera_type_id: int) -> bool:
        try:
            message = self.service.delete_camera_type(camera_type_id)
            self.camera_types = [item for item in self.camera_types if item.id != camera_type_id]
            self.emit_success(message)
            return True
        except Exception as exc:
            self.emit_error(str(exc))
            return False
