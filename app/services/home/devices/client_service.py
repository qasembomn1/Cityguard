from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional

from app.api.api_service import ApiService
from app.models.client import Client
from app.utils.list import extract_dict_list


class ClientService:
    def __init__(self, api: ApiService | None = None) -> None:
        self.api = api or ApiService(os.getenv("Base_URL"))
        self._items: List[Client] = []

    def _as_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _as_bool(self, value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "no", "n", "off", ""}:
                return False
        return default

    def _normalize_type(self, raw: Dict[str, Any]) -> str:
        client_type = str(raw.get("type") or raw.get("client_type") or "").strip().lower()
        if client_type not in {"process", "record"}:
            return "process"
        return client_type

    def _normalize_client(self, raw: Dict[str, Any], fallback_id: int) -> Client:
        return Client(
            id=self._as_int(raw.get("id") or raw.get("client_id"), fallback_id),
            name=str(raw.get("name") or raw.get("host_name") or f"Client {fallback_id}").strip(),
            ip=str(raw.get("ip") or raw.get("client_ip") or raw.get("server_ip") or "").strip(),
            port=self._as_int(raw.get("port") or raw.get("client_port"), 0),
            save_path=str(raw.get("save_path") or raw.get("record_path") or "").strip(),
            type=self._normalize_type(raw),
            is_local=self._as_bool(raw.get("is_local"), True),
        )

    def _request_with_fallback(
        self,
        attempts: Iterable[tuple[str, str]],
        data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        last_exc: Exception | None = None
        for method, path in attempts:
            try:
                return self.api.request(method, path, data=data, auth=True)
            except Exception as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No API attempts configured.")

    def _extract_items(self, payload: Any) -> List[Dict[str, Any]]:
        items = extract_dict_list(payload, keys=("items", "data", "results", "clients"))
        if items:
            return items
        if isinstance(payload, dict):
            for key in ("data", "result", "payload"):
                nested = payload.get(key)
                nested_items = extract_dict_list(nested, keys=("items", "data", "results", "clients"))
                if nested_items:
                    return nested_items
            if "id" in payload and any(key in payload for key in ("name", "host_name", "ip", "client_ip", "server_ip")):
                return [payload]
        elif isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def _refresh_cache(self) -> List[Client]:
        self._items = self.get_all_clients()
        return list(self._items)

    def _find_cached(self, client_id: int) -> Optional[Client]:
        for item in self._items:
            if item.id == client_id:
                return item
        return None

    def get_all_clients(self) -> List[Client]:
        payload = self._request_with_fallback(
            (
                ("GET", "/api/v1/clients/"),
                ("GET", "/api/v1/clients"),
            )
        )
        items = self._extract_items(payload)
        clients: List[Client] = []
        for idx, raw in enumerate(items, start=1):
            clients.append(self._normalize_client(raw, idx))
        self._items = clients
        return clients

    def add_client(self, payload: Dict[str, Any]) -> Client:
        response = self._request_with_fallback(
            (
                ("POST", "/api/v1/clients/create"),
                ("POST", "/api/v1/clients/"),
                ("POST", "/api/v1/clients"),
            ),
            data=payload,
        )

        clients = self._refresh_cache()
        if isinstance(response, dict):
            response_id = self._as_int(response.get("id"), 0)
            if response_id:
                found = self._find_cached(response_id)
                if found is not None:
                    return found
                return self._normalize_client(response, response_id)

        if clients:
            return clients[-1]
        raise RuntimeError("Client created but API did not return refreshed list.")

    def update_client(self, client_id: int, payload: Dict[str, Any]) -> Client:
        self._request_with_fallback(
            (
                ("PATCH", f"/api/v1/clients/update/{client_id}"),
                ("PATCH", f"/api/v1/clients/{client_id}"),
                ("PATCH", f"/api/v1/clients/{client_id}/"),
                ("PUT", f"/api/v1/clients/{client_id}"),
                ("PUT", f"/api/v1/clients/{client_id}/"),
            ),
            data=payload,
        )

        self._refresh_cache()
        found = self._find_cached(client_id)
        if found is not None:
            return found
        raise RuntimeError(f"Client {client_id} updated but not found in refreshed list.")

    def delete_client(self, client_id: int) -> None:
        self._request_with_fallback(
            (
                ("DELETE", f"/api/v1/clients/delete/{client_id}"),
                ("DELETE", f"/api/v1/clients/{client_id}"),
                ("DELETE", f"/api/v1/clients/{client_id}/"),
            )
        )
        self._items = [item for item in self._items if item.id != client_id]
