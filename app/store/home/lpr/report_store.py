from __future__ import annotations

from typing import Any, Dict, List

from app.models.lpr.report import LprReportPayload, LprReportRow
from app.services.home.lpr.report_service import LprReportService
from app.store._init_ import BaseStore


class LprReportStore(BaseStore):
    def __init__(self, service: LprReportService) -> None:
        super().__init__()
        self.service = service
        self.rows: List[LprReportRow] = []
        self.loading = False

    def clear(self) -> None:
        self.rows = []
        self.loading = False
        self.changed.emit()

    def search(self, payload: Dict[str, Any] | LprReportPayload) -> List[LprReportRow]:
        self.loading = True
        self.changed.emit()
        try:
            request = payload if isinstance(payload, LprReportPayload) else LprReportPayload(**dict(payload or {}))
            self.rows = self.service.fetch_report(request)
            return list(self.rows)
        except Exception as exc:
            self.rows = []
            self.emit_error(str(exc))
            return []
        finally:
            self.loading = False
            self.changed.emit()
