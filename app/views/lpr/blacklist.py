from __future__ import annotations

from typing import Optional

from app.store.auth import AuthStore
from app.store.home.lpr.list_store import LprRegistryStore
from app.store.home.user.department_store import DepartmentStore as CameraDepartmentStore
from app.views.lpr._list_crud import LprRegistryPage


class BlacklistPage(LprRegistryPage):
    def __init__(
        self,
        auth_store: Optional[AuthStore] = None,
        camera_source_store: Optional[CameraDepartmentStore] = None,
        registry_store: Optional[LprRegistryStore] = None,
        parent=None,
    ) -> None:
        super().__init__(
            current_path="/lpr/blacklist",
            page_title="LPR Blacklist",
            resource="lpr_blacklists",
            view_permission="view_lpr_blacklist",
            entity_label="Blacklist entry",
            allowed_fields=["plate_no", "color", "region", "type", "note", "user_id", "camera_ids"],
            auth_store=auth_store,
            camera_source_store=camera_source_store,
            registry_store=registry_store,
            parent=parent,
        )
