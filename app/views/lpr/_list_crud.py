from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models.lpr.list_entry import LprListEntry
from app.services.auth.auth_service import AuthService
from app.services.home.devices.camera_service import CameraService
from app.services.home.lpr.list_service import LprRegistryService
from app.store.auth import AuthStore
from app.store.home.lpr.list_store import LprRegistryStore
from app.store.home.user.department_store import DepartmentStore as CameraDepartmentStore
from app.ui.multiselect import PrimeMultiSelect
from app.ui.table import PrimeDataTable, PrimeTableColumn
from app.utils.digits import normalize_ascii_digits
from app.views.watchlist_shared import WATCHLIST_SIDEBAR_STYLES, WatchlistSidebar


_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


def _normalize_line_edit_digits(field: QLineEdit, text: str) -> None:
    normalized = normalize_ascii_digits(text)
    if normalized == text:
        return
    cursor = field.cursorPosition()
    field.blockSignals(True)
    field.setText(normalized)
    field.blockSignals(False)
    field.setCursorPosition(min(cursor, len(normalized)))


def _bind_ascii_digit_input(field: QLineEdit) -> None:
    field.setInputMethodHints(field.inputMethodHints() | Qt.InputMethodHint.ImhPreferLatin)
    field.textEdited.connect(lambda text, edit=field: _normalize_line_edit_digits(edit, text))


class LprRegistryDialog(QDialog):
    submitted = Signal(dict, bool)

    def __init__(
        self,
        page_title: str,
        camera_options: List[dict],
        allowed_fields: List[str],
        current_user_id: int = 0,
        entry: Optional[LprListEntry] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.page_title = page_title
        self.entry = entry
        self.current_user_id = int(current_user_id or 0)
        self.is_edit_mode = entry is not None
        self._camera_options = list(camera_options)
        self._allowed_fields = set(allowed_fields)

        self.setWindowTitle(page_title)
        self.resize(980, 620)
        self.setMinimumSize(920, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        title = QLabel(page_title)
        title.setObjectName("lprDialogTitle")
        root.addWidget(title)

        forms = QHBoxLayout()
        forms.setSpacing(16)
        root.addLayout(forms)

        left_form = QFormLayout()
        left_form.setContentsMargins(0, 0, 0, 0)
        left_form.setSpacing(10)
        forms.addLayout(left_form, 1)

        right_form = QFormLayout()
        right_form.setContentsMargins(0, 0, 0, 0)
        right_form.setSpacing(10)
        forms.addLayout(right_form, 1)

        self.plate_no_edit = QLineEdit()
        self.color_edit = QLineEdit()
        self.region_edit = QLineEdit()
        self.type_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.apart_name_edit = QLineEdit()
        self.phone_edit = QLineEdit()
        self.car_model_edit = QLineEdit()
        self.car_type_edit = QLineEdit()
        _bind_ascii_digit_input(self.plate_no_edit)
        _bind_ascii_digit_input(self.phone_edit)
        self.camera_select = PrimeMultiSelect(
            options=self._camera_options,
            placeholder="Select Cameras",
        )
        self.note_edit = QTextEdit()
        self.note_edit.setMinimumHeight(120)

        if "plate_no" in self._allowed_fields:
            left_form.addRow("Plate Number *", self.plate_no_edit)
        if "color" in self._allowed_fields:
            left_form.addRow("Color", self.color_edit)
        if "region" in self._allowed_fields:
            left_form.addRow("Region", self.region_edit)
        if "type" in self._allowed_fields:
            left_form.addRow("Plate Type", self.type_edit)
        if "name" in self._allowed_fields:
            left_form.addRow("Owner Name", self.name_edit)

        if "apart_name" in self._allowed_fields:
            right_form.addRow("Apartment Name", self.apart_name_edit)
        if "phone" in self._allowed_fields:
            right_form.addRow("Phone", self.phone_edit)
        if "car_model" in self._allowed_fields:
            right_form.addRow("Car Model", self.car_model_edit)
        if "car_type" in self._allowed_fields:
            right_form.addRow("Car Type", self.car_type_edit)
        if "camera_ids" in self._allowed_fields:
            right_form.addRow("Cameras", self.camera_select)

        if "note" in self._allowed_fields:
            root.addWidget(QLabel("Note"))
            root.addWidget(self.note_edit)

        controls = QHBoxLayout()
        controls.addStretch(1)

        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self._reset)
        controls.addWidget(reset_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        controls.addWidget(cancel_btn)

        save_btn = QPushButton("Update" if self.is_edit_mode else "Create")
        save_btn.clicked.connect(self._submit)
        controls.addWidget(save_btn)
        root.addLayout(controls)

        self.setStyleSheet(
            """
            QDialog {
                background: #171a1f;
                color: #f1f5f9;
            }
            QLabel {
                color: #dbe4f3;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#lprDialogTitle {
                color: #f8fafc;
                font-size: 20px;
                font-weight: 700;
            }
            QLineEdit, QTextEdit {
                background: #232831;
                border: 1px solid #3a424f;
                border-radius: 8px;
                color: #f8fafc;
                padding: 8px 10px;
            }
            QPushButton {
                background: #2b3340;
                border: 1px solid #425062;
                border-radius: 8px;
                color: #f8fafc;
                padding: 7px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #35507f;
                border-color: #4d76bb;
            }
            """
        )

        self._reset()

    def _fill(self, entry: LprListEntry) -> None:
        self.plate_no_edit.setText(entry.plate_no)
        self.color_edit.setText(entry.color)
        self.region_edit.setText(entry.region)
        self.type_edit.setText(entry.type)
        self.name_edit.setText(entry.name)
        self.apart_name_edit.setText(entry.apart_name)
        self.phone_edit.setText(entry.phone)
        self.car_model_edit.setText(entry.car_model)
        self.car_type_edit.setText(entry.car_type)
        self.camera_select.set_options(self._camera_options)
        self.camera_select.set_value(entry.camera_ids)
        self.note_edit.setPlainText(entry.note)

    def _reset(self) -> None:
        self.camera_select.set_options(self._camera_options)
        if self.entry is None:
            self.plate_no_edit.clear()
            self.color_edit.clear()
            self.region_edit.clear()
            self.type_edit.clear()
            self.name_edit.clear()
            self.apart_name_edit.clear()
            self.phone_edit.clear()
            self.car_model_edit.clear()
            self.car_type_edit.clear()
            self.camera_select.set_value([])
            self.note_edit.clear()
            return
        self._fill(self.entry)

    def _payload(self) -> Dict[str, Any]:
        payload = {
            "plate_no": normalize_ascii_digits(self.plate_no_edit.text()).strip(),
            "color": self.color_edit.text().strip(),
            "region": self.region_edit.text().strip(),
            "type": self.type_edit.text().strip(),
            "note": self.note_edit.toPlainText().strip(),
            "name": self.name_edit.text().strip(),
            "apart_name": self.apart_name_edit.text().strip(),
            "phone": normalize_ascii_digits(self.phone_edit.text()).strip(),
            "car_model": self.car_model_edit.text().strip(),
            "car_type": self.car_type_edit.text().strip(),
            "user_id": int(
                (self.entry.user_id if self.entry is not None and self.entry.user_id > 0 else self.current_user_id)
                or 0
            ),
            "camera_ids": [int(item) for item in self.camera_select.value()],
        }
        payload = {
            key: value
            for key, value in payload.items()
            if key in self._allowed_fields
        }
        if self.entry is not None:
            payload["id"] = int(self.entry.id)
        return payload

    def _submit(self) -> None:
        if not self.plate_no_edit.text().strip():
            QMessageBox.warning(self, "Missing", "Plate number is required.")
            return
        self.submitted.emit(self._payload(), self.is_edit_mode)


class LprRegistryPage(QWidget):
    navigate = Signal(str)

    def __init__(
        self,
        current_path: str,
        page_title: str,
        resource: str,
        view_permission: str,
        entity_label: str,
        allowed_fields: Optional[List[str]] = None,
        auth_store: Optional[AuthStore] = None,
        camera_source_store: Optional[CameraDepartmentStore] = None,
        registry_store: Optional[LprRegistryStore] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.current_path = current_path
        self.page_title = page_title
        self.resource = resource
        self.view_permission = view_permission
        self.entity_label = entity_label
        self.allowed_fields = list(allowed_fields or [])

        self.auth_store = auth_store or AuthStore(AuthService())
        self.camera_source_store = camera_source_store or CameraDepartmentStore(CameraService())
        self.registry_store = registry_store or LprRegistryStore(
            LprRegistryService(resource=resource, entity_label=entity_label)
        )

        self.auth_store.changed.connect(self.refresh)
        self.auth_store.error.connect(self._show_error)
        self.camera_source_store.changed.connect(self.refresh)
        self.camera_source_store.error.connect(self._show_error)
        self.registry_store.changed.connect(self.refresh)
        self.registry_store.error.connect(self._show_error)
        self.registry_store.success.connect(self._show_info)

        self._build_ui()
        self._apply_style()

        self.auth_store.load()
        self.camera_source_store.get_camera_for_user(None, silent=True)
        self.registry_store.load()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        self.sidebar = WatchlistSidebar(self.current_path, self)
        self.sidebar.navigate.connect(self.navigate.emit)
        root.addWidget(self.sidebar)

        panel = QFrame()
        panel.setObjectName("lprListPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 18)
        panel_layout.setSpacing(14)
        root.addWidget(panel, 1)

        title_row = QVBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(2)
        panel_layout.addLayout(title_row)

        title = QLabel(self.page_title)
        title.setObjectName("lprPageTitle")
        title_row.addWidget(title)

        subtitle = QLabel("Manage plate list entries and assign them to one or more cameras.")
        subtitle.setObjectName("lprPageSubtitle")
        title_row.addWidget(subtitle)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        panel_layout.addLayout(toolbar)

        self.new_btn = QPushButton("+ New")
        self.new_btn.setObjectName("lprNewBtn")
        self.new_btn.clicked.connect(self.open_create_dialog)
        toolbar.addWidget(self.new_btn)

        toolbar.addStretch(1)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("lprSearchInput")
        self.search_edit.setPlaceholderText("Search by plate, owner, phone, camera...")
        self.search_edit.setMaximumWidth(340)
        self.search_edit.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_edit)

        self.table = PrimeDataTable(page_size=12, row_height=58, show_footer=True)
        self.table.set_columns(self._table_columns())
        self.table.set_cell_widget_factory("actions", self._action_widget)
        panel_layout.addWidget(self.table, 1)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            WATCHLIST_SIDEBAR_STYLES
            + """
            QWidget {
                color: #f5f7fb;
            }
            QFrame#lprListPanel {
                background: #1f2024;
                border: 1px solid #2e3138;
                border-radius: 12px;
            }
            QLabel#lprPageTitle {
                color: #f8fafc;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#lprPageSubtitle {
                color: #8fa0b8;
                font-size: 13px;
            }
            QPushButton#lprNewBtn {
                background: #3b82f6;
                border: none;
                border-radius: 10px;
                color: white;
                font-size: 14px;
                font-weight: 700;
                padding: 9px 18px;
            }
            QPushButton#lprNewBtn:hover {
                background: #2f6ce3;
            }
            QLineEdit#lprSearchInput {
                background: #2b2e34;
                border: 1px solid #3a3e46;
                border-radius: 10px;
                color: #f5f7fb;
                padding: 9px 12px;
                font-size: 14px;
                min-height: 24px;
            }
            """
        )

    def showEvent(self, event) -> None:  # type: ignore[override]
        self.camera_source_store.get_camera_for_user(None, silent=True)
        self.registry_store.load()
        super().showEvent(event)

    def _camera_options(self) -> List[dict]:
        options: List[dict] = []
        for camera in self.camera_source_store.cameras:
            label = camera.name
            if camera.camera_ip:
                label = f"{camera.name} ({camera.camera_ip})"
            options.append({"label": label, "value": camera.id})
        return options

    def _table_columns(self) -> List[PrimeTableColumn]:
        columns = [PrimeTableColumn("plate_no", "Plate Number", width=150)]
        if "name" in self.allowed_fields:
            columns.append(PrimeTableColumn("name", "Owner", width=150))
        if "phone" in self.allowed_fields:
            columns.append(PrimeTableColumn("phone", "Phone", width=130))
        if "region" in self.allowed_fields:
            columns.append(PrimeTableColumn("region", "Region", width=120))
        if "color" in self.allowed_fields:
            columns.append(PrimeTableColumn("color", "Color", width=110))
        if "type" in self.allowed_fields:
            columns.append(PrimeTableColumn("type", "Plate Type", width=110))
        if "car_model" in self.allowed_fields:
            columns.append(PrimeTableColumn("car_model", "Car Model", width=140))
        if "car_type" in self.allowed_fields:
            columns.append(PrimeTableColumn("car_type", "Car Type", width=120))
        if "camera_ids" in self.allowed_fields:
            columns.append(PrimeTableColumn("cameras", "Cameras", width=220))
        if "note" in self.allowed_fields:
            columns.append(PrimeTableColumn("note", "Note", stretch=True))
        columns.append(PrimeTableColumn("actions", "Actions", width=140, sortable=False, searchable=False))
        return columns

    def _camera_name_by_id(self, camera_id: int) -> str:
        for camera in self.camera_source_store.cameras:
            if camera.id == camera_id:
                return camera.name or f"Camera #{camera_id}"
        return f"Camera #{camera_id}"

    def _camera_text(self, entry: LprListEntry) -> str:
        names: List[str] = []
        for camera in entry.cameras:
            name = camera.name.strip()
            if name.startswith("Camera #") or not name:
                name = self._camera_name_by_id(camera.id)
            names.append(name)
        if not names and entry.camera_ids:
            names = [self._camera_name_by_id(camera_id) for camera_id in entry.camera_ids]
        return ", ".join(names) if names else "No cameras"

    def _rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for entry in self.registry_store.entries:
            rows.append(
                {
                    "plate_no": entry.plate_no,
                    "name": entry.name or "Unset",
                    "phone": entry.phone or "Unset",
                    "region": entry.region or "Unset",
                    "color": entry.color or "Unset",
                    "type": entry.type or "Unset",
                    "car_model": entry.car_model or "Unset",
                    "car_type": entry.car_type or "Unset",
                    "cameras": self._camera_text(entry),
                    "note": entry.note or "",
                    "_entry": entry,
                }
            )
        return rows

    def refresh(self) -> None:
        self.new_btn.setEnabled(self.auth_store.has_permission(self.view_permission))
        self.table.set_rows(self._rows())
        self.table.set_filter_text(self.search_edit.text())

    def _on_search_changed(self, text: str) -> None:
        self.table.set_filter_text(text)

    def _action_button(self, svg_icon: str, bg: str, border: str) -> QToolButton:
        btn = QToolButton()
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(32, 32)
        btn.setStyleSheet(
            f"""
            QToolButton {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 16px;
            }}
            QToolButton:hover {{
                border-color: #f8fafc;
            }}
            """
        )
        icon_file = _icon_path(svg_icon)
        if os.path.isfile(icon_file):
            btn.setIcon(QIcon(icon_file))
            btn.setIconSize(QSize(18, 18))
        return btn

    def _action_widget(self, row: Dict[str, Any]) -> QWidget:
        entry = row.get("_entry")
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        if not isinstance(entry, LprListEntry):
            return box

        edit_btn = self._action_button("edit.svg", "#35507f", "#4d76bb")
        edit_btn.setToolTip("Edit Entry")
        edit_btn.clicked.connect(lambda: self.open_edit_dialog(entry))
        layout.addWidget(edit_btn)

        delete_btn = self._action_button("trash.svg", "#8b2f3f", "#bb4d62")
        delete_btn.setToolTip("Delete Entry")
        delete_btn.clicked.connect(lambda: self.handle_delete(entry))
        layout.addWidget(delete_btn)
        return box

    def open_create_dialog(self) -> None:
        self._open_dialog()

    def open_edit_dialog(self, entry: LprListEntry) -> None:
        self._open_dialog(entry)

    def _open_dialog(self, entry: Optional[LprListEntry] = None) -> None:
        dialog = LprRegistryDialog(
            page_title=self.page_title,
            camera_options=self._camera_options(),
            allowed_fields=self.allowed_fields,
            current_user_id=self.auth_store.current_user.id if self.auth_store.current_user else 0,
            entry=entry,
            parent=self,
        )
        dialog.submitted.connect(
            lambda payload, is_edit_mode, current_dialog=dialog: self._handle_submit(
                current_dialog,
                payload,
                is_edit_mode,
            )
        )
        dialog.exec()

    def _handle_submit(
        self,
        dialog: LprRegistryDialog,
        payload: Dict[str, Any],
        is_edit_mode: bool,
    ) -> None:
        if is_edit_mode:
            entry_id = int(payload.get("id") or 0)
            if not entry_id:
                self._show_error("Entry id is missing.")
                return
            success = self.registry_store.update_entry(entry_id, payload)
        else:
            success = self.registry_store.create_entry(payload)

        if success:
            dialog.accept()

    def handle_delete(self, entry: LprListEntry) -> None:
        result = QMessageBox.question(
            self,
            "Delete Entry",
            f"Are you sure you want to delete '{entry.plate_no}'?",
        )
        if result == QMessageBox.Yes:
            self.registry_store.delete_entry(entry.id)

    def _show_error(self, text: str) -> None:
        QMessageBox.critical(self, self.page_title, text)

    def _show_info(self, text: str) -> None:
        QMessageBox.information(self, self.page_title, text)
