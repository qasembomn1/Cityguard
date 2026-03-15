from __future__ import annotations

from typing import Any, Dict, List

from app.models.client import Client
from app.services.home.devices.client_service import ClientService
from app.store._init_ import BaseStore


class ClientStore(BaseStore):
    def __init__(self, service: ClientService) -> None:
        super().__init__()
        self.service = service
        self.clients: List[Client] = []

    def load(self) -> None:
        try:
            self.clients = self.service.get_all_clients()
            self.changed.emit()
        except Exception as exc:
            self.emit_error(str(exc))

    def add_client(self, payload: Dict[str, Any]) -> None:
        try:
            self.service.add_client(payload)
            self.clients = self.service.get_all_clients()
            self.emit_success("Client added successfully.")
        except Exception as exc:
            self.emit_error(str(exc))

    def update_client(self, client_id: int, payload: Dict[str, Any]) -> None:
        try:
            self.service.update_client(client_id, payload)
            self.clients = self.service.get_all_clients()
            self.emit_success("Client updated successfully.")
        except Exception as exc:
            self.emit_error(str(exc))

    def delete_client(self, client_id: int) -> None:
        try:
            self.service.delete_client(client_id)
            self.clients = [item for item in self.clients if item.id != client_id]
            self.emit_success("Client deleted successfully.")
        except Exception as exc:
            self.emit_error(str(exc))
