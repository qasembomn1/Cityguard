from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.face.whitelist import FaceWhitelistEntry, FaceWhitelistPayload, FaceWhitelistTemplate
from app.services.home.face_whitelist_service import FaceWhitelistService
from app.store._init_ import BaseStore


class FaceWhitelistStore(BaseStore):
    def __init__(self, service: FaceWhitelistService) -> None:
        super().__init__()
        self.service = service
        self.entries: List[FaceWhitelistEntry] = []
        self.templates_by_person: Dict[str, List[FaceWhitelistTemplate]] = {}

    def load(self) -> List[FaceWhitelistEntry]:
        try:
            self.entries = self.service.list_entries()
            self.changed.emit()
        except Exception as exc:
            self.emit_error(str(exc))
        return list(self.entries)

    def create_entry(
        self,
        payload: Dict[str, Any] | FaceWhitelistPayload,
        image_path: Optional[str] = None,
    ) -> Optional[FaceWhitelistEntry]:
        try:
            message, person_id = self.service.create_entry(payload, image_path=image_path)
            self.entries = self.service.list_entries()
            self.emit_success(message)
            if person_id:
                return self.find_entry(person_id)
            if self.entries:
                return self.entries[-1]
        except Exception as exc:
            self.emit_error(str(exc))
        return None

    def update_entry(self, person_id: str, payload: Dict[str, Any] | FaceWhitelistPayload) -> bool:
        try:
            message = self.service.update_entry(person_id, payload)
            self.entries = self.service.list_entries()
            self.emit_success(message)
            return True
        except Exception as exc:
            self.emit_error(str(exc))
            return False

    def delete_entry(self, person_id: str) -> bool:
        try:
            message = self.service.delete_entry(person_id)
            self.entries = [item for item in self.entries if item.identifier != person_id]
            self.templates_by_person.pop(person_id, None)
            self.emit_success(message)
            return True
        except Exception as exc:
            self.emit_error(str(exc))
            return False

    def load_templates(self, person_id: str) -> List[FaceWhitelistTemplate]:
        try:
            templates = self.service.list_templates(person_id)
            self.templates_by_person[person_id] = templates
            self.changed.emit()
            return list(templates)
        except Exception as exc:
            self.emit_error(str(exc))
            return list(self.templates_by_person.get(person_id, []))

    def add_image(self, person_id: str, image_path: str) -> bool:
        try:
            message = self.service.add_image(person_id, image_path)
            self.templates_by_person[person_id] = self.service.list_templates(person_id)
            self.entries = self.service.list_entries()
            self.emit_success(message)
            return True
        except Exception as exc:
            self.emit_error(str(exc))
            return False

    def delete_template_image(self, person_id: str, template_id: str) -> bool:
        try:
            message = self.service.delete_template_image(person_id, template_id)
            current = self.templates_by_person.get(person_id, [])
            self.templates_by_person[person_id] = [
                item for item in current if item.template_id != template_id
            ]
            self.entries = self.service.list_entries()
            self.emit_success(message)
            return True
        except Exception as exc:
            self.emit_error(str(exc))
            return False

    def templates_for(self, person_id: str) -> List[FaceWhitelistTemplate]:
        return list(self.templates_by_person.get(person_id, []))

    def find_entry(self, person_id: str) -> Optional[FaceWhitelistEntry]:
        for item in self.entries:
            if item.identifier == person_id:
                return item
        return None