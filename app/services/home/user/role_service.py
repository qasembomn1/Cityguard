from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List

from app.api.api_service import ApiService
from app.models.role import PermissionResponse, RolePayload, RoleResponse
from app.utils.list import extract_dict_list


class RoleService:
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
        raise RuntimeError("No role API attempts configured.")

    def _extract_items(self, payload: Any, keys: tuple[str, ...]) -> List[Dict[str, Any]]:
        items = extract_dict_list(payload, keys=keys)
        if items:
            return items
        if isinstance(payload, dict):
            for key in ("data", "result", "payload"):
                nested = payload.get(key)
                nested_items = extract_dict_list(nested, keys=keys)
                if nested_items:
                    return nested_items
            if "id" in payload and ("name" in payload or "permission" in payload):
                return [payload]
        elif isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def list_roles(self) -> List[RoleResponse]:
        payload = self._request_with_fallback(
            (
                ("GET", "/api/v1/roles/"),
                ("GET", "/api/v1/roles"),
            )
        )
        return [
            RoleResponse.from_dict(item)
            for item in self._extract_items(payload, ("items", "data", "results", "roles"))
            if isinstance(item, dict)
        ]

    def list_permissions(self) -> List[PermissionResponse]:
        payload = self._request_with_fallback(
            (
                ("GET", "/api/v1/roles/permissions"),
                ("GET", "/api/v1/roles/permissions/"),
            )
        )
        return [
            PermissionResponse.from_dict(item)
            for item in self._extract_items(payload, ("items", "data", "results", "permissions"))
            if isinstance(item, dict)
        ]

    def create_role(self, payload: Dict[str, Any] | RolePayload) -> str:
        data = payload.to_dict() if isinstance(payload, RolePayload) else dict(payload or {})
        response = self._request_with_fallback(
            (
                ("POST", "/api/v1/roles/create"),
                ("POST", "/api/v1/roles/create/"),
            ),
            data=data,
        )
        if isinstance(response, str) and response.strip():
            return response.strip()
        if isinstance(response, dict):
            message = str(response.get("message") or response.get("detail") or "").strip()
            if message:
                return message
        return "Role created successfully."

    def update_role(self, role_id: int, payload: Dict[str, Any] | RolePayload) -> str:
        data = payload.to_dict() if isinstance(payload, RolePayload) else dict(payload or {})
        response = self._request_with_fallback(
            (
                ("PATCH", f"/api/v1/roles/update/{role_id}"),
                ("PATCH", f"/api/v1/roles/update/{role_id}/"),
            ),
            data=data,
        )
        if isinstance(response, str) and response.strip():
            return response.strip()
        if isinstance(response, dict):
            message = str(response.get("message") or response.get("detail") or "").strip()
            if message:
                return message
        return "Role updated successfully."

    def delete_role(self, role_id: int) -> str:
        response = self._request_with_fallback(
            (
                ("DELETE", f"/api/v1/roles/delete/{role_id}"),
                ("DELETE", f"/api/v1/roles/delete/{role_id}/"),
            )
        )
        if isinstance(response, str) and response.strip():
            return response.strip()
        if isinstance(response, dict):
            message = str(response.get("message") or response.get("detail") or "").strip()
            if message:
                return message
        return "Role deleted successfully."
