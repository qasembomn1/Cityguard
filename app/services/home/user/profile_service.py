from __future__ import annotations

import os
from typing import Any, Dict, Iterable, Tuple

from app.api.api_service import ApiService
from app.models.profile import PasswordChangePayload, ProfileResponse, ProfileUpdatePayload


class ProfileService:
    def __init__(self, api: ApiService | None = None) -> None:
        self.api = api or ApiService(os.getenv("Base_URL"))

    def _request_with_fallback(
        self,
        attempts: Iterable[tuple[str, str]],
        data: Dict[str, Any] | None = None,
    ) -> Any:
        last_exc: Exception | None = None
        for method, path in attempts:
            try:
                return self.api.request(method, path, data=data, auth=True)
            except Exception as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No profile API attempts configured.")

    def get_profile(self) -> ProfileResponse:
        payload = self._request_with_fallback(
            (
                ("GET", "/api/v1/auth/profile/"),
                ("GET", "/api/v1/auth/profile"),
            )
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Profile API response did not contain a valid object.")
        return ProfileResponse.from_dict(payload)

    def update_profile(
        self,
        payload: Dict[str, Any] | ProfileUpdatePayload,
    ) -> Tuple[ProfileResponse, str]:
        data = payload.to_dict() if isinstance(payload, ProfileUpdatePayload) else dict(payload or {})
        response = self._request_with_fallback(
            (
                ("PATCH", "/api/v1/auth/profile/update"),
                ("PATCH", "/api/v1/auth/profile/update/"),
            ),
            data=data,
        )
        updated_profile = self.get_profile()
        if isinstance(response, str) and response.strip():
            return updated_profile, response.strip()
        if isinstance(response, dict):
            message = str(response.get("message") or response.get("detail") or "").strip()
            if message:
                return updated_profile, message
        return updated_profile, "Profile updated successfully."

    def change_password(
        self,
        payload: Dict[str, Any] | PasswordChangePayload,
    ) -> str:
        data = payload.to_dict() if isinstance(payload, PasswordChangePayload) else dict(payload or {})
        response = self._request_with_fallback(
            (
                ("POST", "/api/v1/auth/change_password/"),
                ("POST", "/api/v1/auth/change_password"),
            ),
            data=data,
        )
        if isinstance(response, str) and response.strip():
            return response.strip()
        if isinstance(response, dict):
            message = str(response.get("message") or response.get("detail") or "").strip()
            if message:
                return message
        return "Password changed successfully."
