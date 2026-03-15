from __future__ import annotations

import os
from typing import Any, List

from app.api.api_service import ApiService
from app.models.access_control import AccessControl, AccessControlType
from app.utils.list import extract_dict_list

class AccessControlService:
    def __init__(self, api: ApiService | None = None) -> None:
        self.api = api or ApiService(os.getenv("Base_URL"))

    def _as_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def get_access_controls(self) -> List[AccessControl]:
        try:
            payload = self.api.get("/api/v1/access_controls/", auth=True)
        except Exception:
            return []

        items = extract_dict_list(payload, keys=("items", "data", "results", "access_controls"))
        result: List[AccessControl] = []
        for raw in items:
            ac_type_raw = raw.get("ac_type")
            if not isinstance(ac_type_raw, dict):
                ac_type_raw = raw.get("access_control_type")
            num_relay = 0
            if isinstance(ac_type_raw, dict):
                num_relay = self._as_int(ac_type_raw.get("num_of_relay") or ac_type_raw.get("relay_count"), 0)
            if not num_relay:
                num_relay = self._as_int(raw.get("num_of_relay"), 0)

            result.append(
                AccessControl(
                    id=self._as_int(raw.get("id"), 0),
                    name=str(raw.get("name") or raw.get("title") or "Access Control"),
                    ac_type=AccessControlType(num_of_relay=max(0, num_relay)),
                )
            )
        return result

