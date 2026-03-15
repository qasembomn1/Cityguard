from __future__ import annotations

from typing import Any, Dict, List

from app.models.lpr.repeated import LprRepeatedPayload, LprRepeatedResult
from app.services.home.lpr.repeated_service import LprRepeatedService
from app.store._init_ import BaseStore


class LprRepeatedStore(BaseStore):
    def __init__(self, service: LprRepeatedService) -> None:
        super().__init__()
        self.service = service
        self.results: List[LprRepeatedResult] = []
        self.loading = False

    def clear(self) -> None:
        self.results = []
        self.loading = False
        self.changed.emit()

    def search(self, payload: Dict[str, Any] | LprRepeatedPayload) -> List[LprRepeatedResult]:
        self.loading = True
        self.changed.emit()
        try:
            request = payload if isinstance(payload, LprRepeatedPayload) else LprRepeatedPayload(**dict(payload or {}))
            self.results = self.service.search(request)
            return list(self.results)
        except Exception as exc:
            self.results = []
            self.emit_error(str(exc))
            return []
        finally:
            self.loading = False
            self.changed.emit()
