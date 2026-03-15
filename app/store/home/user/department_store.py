from app.store._init_ import BaseStore
from app.services.home.devices.camera_service import CameraService
from app.models.camera import Camera
from app.models.department import DepartmentPayload, DepartmentResponse
from app.services.home.user.department_service import DepartmentService
from typing import Optional,List, Dict, Any
class DepartmentStore(BaseStore):
    def __init__(self, service: CameraService) -> None:
        super().__init__()
        self.service = service
        self.cameras: List[Camera] = []

    def get_camera_for_user(self, department_id: Optional[int], silent: bool = False) -> None:
        try:
            self.cameras = self.service.list_cameras(department_id)
            self.changed.emit()
        except Exception as exc:
            if not silent:
                self.emit_error(str(exc))


class DepartmentCrudStore(BaseStore):
    def __init__(self, service: DepartmentService) -> None:
        super().__init__()
        self.service = service
        self.departments: List[DepartmentResponse] = []

    def load(self) -> List[DepartmentResponse]:
        try:
            self.departments = self.service.list_departments()
            self.changed.emit()
            return list(self.departments)
        except Exception as exc:
            self.emit_error(str(exc))
            return []

    def create_department(self, payload: Dict[str, Any]) -> None:
        try:
            message = self.service.create_department(DepartmentPayload(**payload))
            self.departments = self.service.list_departments()
            self.emit_success(message)
        except Exception as exc:
            self.emit_error(str(exc))

    def update_department(self, department_id: int, payload: Dict[str, Any]) -> None:
        try:
            message = self.service.update_department(department_id, DepartmentPayload(**payload))
            self.departments = self.service.list_departments()
            self.emit_success(message)
        except Exception as exc:
            self.emit_error(str(exc))

    def delete_department(self, department_id: int) -> None:
        try:
            message = self.service.delete_department(department_id)
            self.departments = [item for item in self.departments if item.id != department_id]
            self.emit_success(message)
        except Exception as exc:
            self.emit_error(str(exc))
