from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List

from app.api.api_service import ApiService
from app.models.department import DepartmentPayload, DepartmentResponse
from app.utils.list import extract_dict_list


class DepartmentService:
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
        raise RuntimeError("No department API attempts configured.")

    def _extract_items(self, payload: Any) -> List[Dict[str, Any]]:
        items = extract_dict_list(payload, keys=("items", "data", "results", "departments"))
        if items:
            return items
        if isinstance(payload, dict):
            for key in ("data", "result", "payload"):
                nested = payload.get(key)
                nested_items = extract_dict_list(nested, keys=("items", "data", "results", "departments"))
                if nested_items:
                    return nested_items
            if "id" in payload and "name" in payload:
                return [payload]
        elif isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def list_departments(self) -> List[DepartmentResponse]:
        payload = self._request_with_fallback(
            (
                ("GET", "/api/v1/departments/"),
                ("GET", "/api/v1/departments"),
            )
        )
        return [
            DepartmentResponse.from_dict(item)
            for item in self._extract_items(payload)
            if isinstance(item, dict)
        ]

    def create_department(self, payload: Dict[str, Any] | DepartmentPayload) -> str:
        data = payload.to_dict() if isinstance(payload, DepartmentPayload) else dict(payload or {})
        response = self._request_with_fallback(
            (
                ("POST", "/api/v1/departments/create"),
                ("POST", "/api/v1/departments/create/"),
            ),
            data=data,
        )
        if isinstance(response, str) and response.strip():
            return response.strip()
        if isinstance(response, dict):
            message = str(response.get("message") or response.get("detail") or "").strip()
            if message:
                return message
        return "Department created successfully."

    def update_department(self, department_id: int, payload: Dict[str, Any] | DepartmentPayload) -> str:
        data = payload.to_dict() if isinstance(payload, DepartmentPayload) else dict(payload or {})
        response = self._request_with_fallback(
            (
                ("PATCH", f"/api/v1/departments/update/{department_id}"),
                ("PATCH", f"/api/v1/departments/update/{department_id}/"),
            ),
            data=data,
        )
        if isinstance(response, str) and response.strip():
            return response.strip()
        if isinstance(response, dict):
            message = str(response.get("message") or response.get("detail") or "").strip()
            if message:
                return message
        return "Department updated successfully."

    def delete_department(self, department_id: int) -> str:
        response = self._request_with_fallback(
            (
                ("DELETE", f"/api/v1/departments/delete/{department_id}"),
                ("DELETE", f"/api/v1/departments/delete/{department_id}/"),
            )
        )
        if isinstance(response, str) and response.strip():
            return response.strip()
        if isinstance(response, dict):
            message = str(response.get("message") or response.get("detail") or "").strip()
            if message:
                return message
        return "Department deleted successfully."
