from __future__ import annotations

from typing import List, Optional

from app.models.logs import UserLogResponse
from app.services.home.user.user_log_service import UserLogService
from app.store._init_ import BaseStore


class UserLogStore(BaseStore):
    def __init__(self, service: UserLogService) -> None:
        super().__init__()
        self.service = service
        self.logs: List[UserLogResponse] = []
        self.last_user_id: Optional[int] = None

    def load_for_user(
        self,
        user_id: Optional[int],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        action: Optional[str] = None,
    ) -> List[UserLogResponse]:
        try:
            self.last_user_id = user_id
            self.logs = self.service.list_user_logs(
                user_id=user_id,
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
