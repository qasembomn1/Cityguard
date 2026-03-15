from __future__ import annotations

import os
from typing import Any, Dict, Iterable

from app.api.api_service import ApiService
from app.models.face.report import FaceReportPayload, FaceReportResult, extract_face_report_result


class FaceReportService:
    def __init__(self, endpoint: str, api: ApiService | None = None) -> None:
        self.endpoint = endpoint
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
        raise RuntimeError("No face report API attempts configured.")

    def _attempts(self) -> tuple[tuple[str, str], tuple[str, str]]:
        path = self.endpoint if self.endpoint.startswith("/") else f"/{self.endpoint}"
        normalized = path.rstrip("/")
        return (("POST", normalized), ("POST", f"{normalized}/"))

    def fetch_report(self, payload: Dict[str, Any] | FaceReportPayload) -> FaceReportResult:
        data = payload.to_dict() if isinstance(payload, FaceReportPayload) else dict(payload or {})
        response = self._request_with_fallback(self._attempts(), data=data)
        return extract_face_report_result(response)
