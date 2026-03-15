from __future__ import annotations

from typing import Any, Dict, List

from app.models.lpr.list_entry import LprListEntry, LprListPayload
from app.services.home.lpr.list_service import LprRegistryService
from app.store._init_ import BaseStore


class LprRegistryStore(BaseStore):
    def __init__(self, service: LprRegistryService) -> None:
        super().__init__()
        self.service = service
        self.entries: List[LprListEntry] = []

    def load(self) -> List[LprListEntry]:
        try:
            self.entries = self.service.list_entries()
            self.changed.emit()
        except Exception as exc:
            self.emit_error(str(exc))
        return list(self.entries)

    def create_entry(self, payload: Dict[str, Any] | LprListPayload) -> bool:
        try:
            message = self.service.create_entry(payload)
            self.entries = self.service.list_entries()
            self.emit_success(message)
            return True
        except Exception as exc:
            self.emit_error(str(exc))
            return False

    def update_entry(self, entry_id: int, payload: Dict[str, Any] | LprListPayload) -> bool:
        try:
            message = self.service.update_entry(entry_id, payload)
            self.entries = self.service.list_entries()
            self.emit_success(message)
            return True
        except Exception as exc:
            self.emit_error(str(exc))
            return False

    def delete_entry(self, entry_id: int) -> bool:
        try:
            message = self.service.delete_entry(entry_id)
            self.entries = [item for item in self.entries if item.id != entry_id]
            self.emit_success(message)
            return True
        except Exception as exc:
            self.emit_error(str(exc))
            return False
