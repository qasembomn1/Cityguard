from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List

from app.api.api_service import ApiService
from app.models.user import UserPayload, UserResponse
from app.utils.list import extract_dict_list


class UserService:
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
        raise RuntimeError("No user API attempts configured.")

    def _extract_items(self, payload: Any) -> List[Dict[str, Any]]:
        items = extract_dict_list(payload, keys=("items", "data", "results", "users"))
        if items:
            return items
        if isinstance(payload, dict):
            for key in ("data", "result", "payload"):
                nested = payload.get(key)
                nested_items = extract_dict_list(nested, keys=("items", "data", "results", "users"))
                if nested_items:
                    return nested_items
            if "id" in payload and "username" in payload:
                return [payload]
        elif isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def list_users(self) -> List[UserResponse]:
        payload = self._request_with_fallback(
            (
                ("GET", "/api/v1/users/"),
                ("GET", "/api/v1/users"),
            )
        )
        return [
            UserResponse.from_dict(item)
            for item in self._extract_items(payload)
            if isinstance(item, dict)
        ]

    def create_user(self, payload: Dict[str, Any] | UserPayload) -> str:
        data = payload.to_dict(include_password=True) if isinstance(payload, UserPayload) else dict(payload or {})
        response = self._request_with_fallback(
            (
                ("POST", "/api/v1/users/create"),
                ("POST", "/api/v1/users/create/"),
            ),
            data=data,
        )
        if isinstance(response, str) and response.strip():
            return response.strip()
        if isinstance(response, dict):
            message = str(response.get("message") or response.get("detail") or "").strip()
            if message:
                return message
        return "User created successfully."

    def update_user(self, user_id: int, payload: Dict[str, Any] | UserPayload) -> str:
        if isinstance(payload, UserPayload):
            data = payload.to_dict(include_password=True)
        else:
            data = dict(payload or {})

        response = self._request_with_fallback(
            (
                ("PATCH", f"/api/v1/users/update/{user_id}"),
                ("PATCH", f"/api/v1/users/update/{user_id}/"),
            ),
            data=data,
        )
        if isinstance(response, str) and response.strip():
            return response.strip()
        if isinstance(response, dict):
            message = str(response.get("message") or response.get("detail") or "").strip()
            if message:
                return message
        return "User updated successfully."

    def delete_user(self, user_id: int) -> str:
        response = self._request_with_fallback(
            (
                ("DELETE", f"/api/v1/users/delete/{user_id}"),
                ("DELETE", f"/api/v1/users/delete/{user_id}/"),
            )
        )
        if isinstance(response, str) and response.strip():
            return response.strip()
        if isinstance(response, dict):
            message = str(response.get("message") or response.get("detail") or "").strip()
            if message:
                return message
        return "User deleted successfully."
