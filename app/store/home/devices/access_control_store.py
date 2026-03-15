from app.store._init_ import BaseStore
from typing import List

from app.models.access_control import AccessControl
from app.services.home.devices.access_control_service import AccessControlService

class AccessControlStore(BaseStore):
    def __init__(self, service: AccessControlService) -> None:
        super().__init__()
        self.service = service
        self.access_controls: List[AccessControl] = []

    def load(self) -> None:
        self.access_controls = self.service.get_access_controls()
        self.changed.emit()
