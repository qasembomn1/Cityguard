from __future__ import annotations

from typing import List, Optional

from app.models.logs import ActivityLogEntry
from app.services.home.logs.activity_log_service import ActivityLogService
from app.store._init_ import BaseStore


class ActivityLogStore(BaseStore):
    def __init__(self, service: ActivityLogService) -> None:
        super().__init__()
        self.service = service
        self.logs: List[ActivityLogEntry] = []
        self.last_entity_id: Optional[int] = None

    def load_logs(
        self,
        entity_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        action: Optional[str] = None,
    ) -> List[ActivityLogEntry]:
        try:
            self.last_entity_id = entity_id
            self.logs = self.service.list_logs(
                entity_id=entity_id,
                start_date=start_date,
                end_date=end_date,
                action=action,
            )
            self.changed.emit()
            return list(self.logs)
        except Exception as exc:
            self.logs = []
            self.emit_error(str(exc))
            return []
