from __future__ import annotations
from typing import Any,Dict
from app.services.home.devices.camera_service import CameraService
from app.store._init_ import BaseStore
from app.store.home.user.department_store import DepartmentStore



class CameraStore(BaseStore):
    def __init__(self, service: CameraService, department_store: DepartmentStore) -> None:
        super().__init__()
        self.service = service
        self.department_store = department_store

    def add_new_camera(self, payload: Dict[str, Any]) -> None:
        self.service.add_camera(payload)
        self.department_store.get_camera_for_user(None)
        self.emit_success("Camera added successfully.")

    def update_camera(self, payload: Dict[str, Any]) -> None:
        self.service.update_camera(payload)
        self.department_store.get_camera_for_user(None)
        self.emit_success("Camera updated successfully.")

    def delete_camera(self, camera_id: int) -> None:
        self.service.delete_camera(camera_id)
        self.department_store.get_camera_for_user(None)
        self.emit_success("Camera deleted successfully.")

    def update_camera_roi(self, camera_id: int, roi: str) -> None:
        self.service.update_camera_roi(camera_id, roi)
        self.department_store.get_camera_for_user(None)
        self.emit_success("ROI updated successfully.")

    def update_camera_countline(self, camera_id: int, countline: str) -> None:
        self.service.update_camera_countline(camera_id, countline)
        self.department_store.get_camera_for_user(None)
        self.emit_success("Count Line updated successfully.")

    def get_camera_frame(self, camera_id: int) -> str:
        frame = self.service.get_camera_frame(camera_id)
        self.emit_success("Camera frame loaded successfully.")
        return frame

