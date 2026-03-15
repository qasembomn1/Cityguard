from __future__ import annotations

from typing import Any, Dict, List

from app.models.lpr.search import LprSearchPayload, LprSearchResult
from app.services.home.lpr.search_service import LprSearchService
from app.store._init_ import BaseStore


class LprSearchStore(BaseStore):
    def __init__(self, service: LprSearchService) -> None:
        super().__init__()
        self.service = service
        self.results: List[LprSearchResult] = []
        self.loading = False

    def clear(self) -> None:
        self.results = []
        self.changed.emit()

    def search(self, payload: Dict[str, Any]) -> List[LprSearchResult]:
        self.loading = True
        self.changed.emit()
        try:
            request = LprSearchPayload(**payload)
            self.results = self.service.search_lpr(request)
            return list(self.results)
        except Exception as exc:
            self.results = []
            self.emit_error(str(exc))
            return []
        finally:
            self.loading = False
            self.changed.emit()
