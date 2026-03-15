from __future__ import annotations

from app.services.home.face_blacklist_service import FaceBlacklistService
from app.store.home.face.face_blacklist_store import FaceBlacklistStore
from app.views.face.whitelist import FaceRegistryPage


class BlacklistPage(FaceRegistryPage):
    current_path = "/face/blacklist"
    toast_title = "Face Blacklist"
    registry_title_text = "Face Blacklist Registry"
    registry_hint_text = "Manage blocked face identities, review image templates, and map them to cameras."
    form_title_text = "Face Blacklist"
    form_create_hint_text = "Create a blacklist person and assign one or more cameras."
    form_edit_hint_text = "Update blacklist person details. Use the image actions in the table to manage templates."
    manage_permission = "view_face_blacklist"
    manage_error_text = "You don't have permission to manage the face blacklist."
    service_cls = FaceBlacklistService
    store_cls = FaceBlacklistStore
