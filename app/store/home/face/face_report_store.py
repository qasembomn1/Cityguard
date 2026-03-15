from __future__ import annotations

from typing import Any, Dict, List

from app.models.face.report import FaceReportPayload, FaceReportResult, FaceReportRow
from app.services.home.face_report_service import FaceReportService
from app.store._init_ import BaseStore


class FaceReportStore(BaseStore):
    def __init__(self, service: FaceReportService) -> None:
        super().__init__()
        self.service = service
        self.rows: List[FaceReportRow] = []
        self.message = ""
        self.loading = False

    def clear(self) -> None:
        self.rows = []
        self.message = ""
        self.loading = False
        self.changed.emit()

    def search(self, payload: Dict[str, Any] | FaceReportPayload) -> FaceReportResult:
        self.loading = True
        self.changed.emit()
        try:
            request = payload if isinstance(payload, FaceReportPayload) else FaceReportPayload(**dict(payload or {}))
            result = self.service.fetch_report(request)
            self.rows = list(result.rows)
            self.message = result.message
            return result
        except Exception as exc:
            self.rows = []
            self.message = ""
            self.emit_error(str(exc))
            return FaceReportResult()
        finally:
            self.loading = False
            self.changed.emit()
