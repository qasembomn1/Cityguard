from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.screen import ScreenResponse
from app.services.home.stream.screen_service import ScreenService
from app.store._init_ import BaseStore


class ScreenStore(BaseStore):
    def __init__(self, service: ScreenService) -> None:
        super().__init__()
        self.service = service
        self.screens: List[ScreenResponse] = []

    def load(self) -> List[ScreenResponse]:
        try:
            self.screens = self.service.list_screens()
            self.changed.emit()
            return list(self.screens)
        except Exception as exc:
            self.emit_error(str(exc))
            raise

    def get_screen(self, screen_id: int) -> Optional[ScreenResponse]:
        for item in self.screens:
            if item.id == screen_id:
                return item
        return None

    def create_screen(self, payload: Dict[str, Any]) -> ScreenResponse:
        try:
            screen = self.service.create_screen(payload)
            self.screens = self.service.list_screens()
            self.emit_success("Screen created successfully.")
            return screen
        except Exception as exc:
            self.emit_error(str(exc))
            raise

    def update_screen(self, payload: Dict[str, Any]) -> ScreenResponse:
        try:
            screen = self.service.update_screen(payload)
            self.screens = self.service.list_screens()
            self.emit_success("Screen updated successfully.")
            return screen
        except Exception as exc:
            self.emit_error(str(exc))
            raise

    def add_camera_to_screen(self, screen_id: int, payload: Dict[str, Any]) -> ScreenResponse:
        try:
            screen = self.service.add_camera_to_screen(screen_id, payload)
            self.screens = self.service.list_screens()
            self.emit_success("Screen cameras updated successfully.")
            return screen
        except Exception as exc:
            self.emit_error(str(exc))
            raise

    def delete_screen(self, screen_id: int) -> None:
        try:
            self.service.delete_screen(screen_id)
            self.screens = [item for item in self.screens if item.id != screen_id]
            self.emit_success("Screen deleted successfully.")
        except Exception as exc:
            self.emit_error(str(exc))
            raise

