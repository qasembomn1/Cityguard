from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List

from app.api.api_service import ApiService
from app.models.lpr.report import LprReportPayload, LprReportRow
from app.utils.list import extract_dict_list


class LprReportService:
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
        raise RuntimeError("No LPR report API attempts configured.")

    def _extract_items(self, payload: Any) -> List[Dict[str, Any]]:
        keys = ("items", "data", "results", "records", "report", "rows", "result")
        items = extract_dict_list(payload, keys=keys)
        if items:
            return items
        if isinstance(payload, dict):
            for key in ("data", "result", "payload"):
                nested = payload.get(key)
                nested_items = extract_dict_list(nested, keys=keys)
                if nested_items:
                    return nested_items
            if any(key in payload for key in ("cam_name", "camera_name", "total1", "total_records")):
                return [payload]
        elif isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def fetch_report(self, payload: Dict[str, Any] | LprReportPayload) -> List[LprReportRow]:
        data = payload.to_dict() if isinstance(payload, LprReportPayload) else dict(payload or {})
        response = self._request_with_fallback(
            (
                ("POST", "/api/v1/report/lpr"),
                ("POST", "/api/v1/report/lpr/"),
            ),
            data=data,
        )
        return [
            LprReportRow.from_dict(item)
            for item in self._extract_items(response)
            if isinstance(item, dict)
        ]
