from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List

from app.models.face.blacklist import FaceBlacklistEntry, FaceBlacklistPayload, FaceBlacklistTemplate
from app.services.home.face_whitelist_service import FaceWhitelistService, LowSimilarityError


class FaceBlacklistService(FaceWhitelistService):
    collection_label = "blacklist"

    def _collection_path(self) -> str:
        return "/api/v1/face_blacklists"

    def _resolve_image_url(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        lowered = text.lower()
        if lowered.startswith(("http://", "https://", "data:image/")):
            return text
        if text.startswith("/"):
            return f"{self.api.base_url}{text}"
        if text.startswith("api/"):
            return f"{self.api.base_url}/{text}"
        encoded = urllib.parse.quote(text)
        return f"{self.api.base_url}/api/v1/face_blacklists/image/{encoded}"

    def list_entries(self) -> List[FaceBlacklistEntry]:
        payload = self._request_with_fallback(
            (
                ("GET", f"{self._collection_path()}/"),
                ("GET", self._collection_path()),
            )
        )
        entries: List[FaceBlacklistEntry] = []
        for item in self._extract_items(payload):
            entries.append(FaceBlacklistEntry.from_dict(self._normalize_entry(item)))
        return entries

    def create_entry(
        self,
        payload: Dict[str, Any] | FaceBlacklistPayload,
        image_path: str | None = None,
    ) -> tuple[str, str]:
        data = self._payload_to_dict(payload)
        paths = (f"{self._collection_path()}/create", f"{self._collection_path()}/create/")

        if image_path:
            image_fields = self._image_request_fields(image_path)
            data.update(image_fields)
            response = self._request_with_fallback((("POST", path) for path in paths), data=data)
            return (
                self._extract_message(response, "Blacklist person created successfully."),
                self._extract_person_id(response),
            )

        response = self._request_with_fallback((("POST", path) for path in paths), data=data)
        return (
            self._extract_message(response, "Blacklist person created successfully."),
            self._extract_person_id(response),
        )

    def update_entry(self, person_id: str, payload: Dict[str, Any] | FaceBlacklistPayload) -> str:
        data = self._payload_to_dict(payload)
        response = self._request_with_fallback(
            (
                ("PATCH", f"{self._collection_path()}/update/{person_id}"),
                ("PATCH", f"{self._collection_path()}/update/{person_id}/"),
            ),
            data=data,
        )
        return self._extract_message(response, "Blacklist person updated successfully.")

    def delete_entry(self, person_id: str) -> str:
        response = self._request_with_fallback(
            (
                ("DELETE", f"{self._collection_path()}/delete/{person_id}"),
                ("DELETE", f"{self._collection_path()}/delete/{person_id}/"),
            )
        )
        return self._extract_message(response, "Blacklist person deleted successfully.")

    def list_templates(self, person_id: str) -> List[FaceBlacklistTemplate]:
        payload = self._request_with_fallback(
            (
                ("GET", f"{self._collection_path()}/templates/{person_id}"),
                ("GET", f"{self._collection_path()}/templates/{person_id}/"),
            )
        )
        templates: List[FaceBlacklistTemplate] = []
        for item in self._extract_templates(payload):
            templates.append(FaceBlacklistTemplate.from_dict(self._normalize_template(item)))
        return templates

    def add_image(self, person_id: str, image_path: str) -> str:
        paths = (
            f"{self._collection_path()}/add_image/{person_id}",
            f"{self._collection_path()}/add_image/{person_id}/",
        )
        image_fields = self._image_request_fields(image_path)
        response = self._request_with_fallback((("POST", path) for path in paths), data=image_fields)
        return self._extract_message(response, "Face image added successfully.")

    def delete_template_image(self, person_id: str, template_id: str) -> str:
        response = self._request_with_fallback(
            (
                ("DELETE", f"{self._collection_path()}/delete_image/{person_id}/{template_id}"),
                ("DELETE", f"{self._collection_path()}/delete_image/{person_id}/{template_id}/"),
            )
        )
        return self._extract_message(response, "Template image deleted successfully.")
