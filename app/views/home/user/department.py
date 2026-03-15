from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models.department import DepartmentResponse
from app.services.auth.auth_service import AuthService
from app.services.home.devices.camera_service import CameraService
from app.services.home.user.department_service import DepartmentService
from app.store.auth import AuthStore
from app.store.home.user.department_store import DepartmentCrudStore, DepartmentStore as CameraDepartmentStore
from app.ui.multiselect import PrimeMultiSelect
from app.ui.table import PrimeDataTable, PrimeTableColumn
from app.views.home.user._shared import USER_MANAGEMENT_SIDEBAR_STYLES, UserManagementSidebar


_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


class DepartmentDialog(QDialog):
    submitted = Signal(dict, bool)

    def __init__(
        self,
        camera_options: List[dict],
        department: Optional[DepartmentResponse] = None,
        cameras_enabled: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.department = department
        self.is_edit_mode = department is not None
        self._camera_options = list(camera_options)
        self._cameras_enabled = cameras_enabled

        self.setWindowTitle("Department")
        self.resize(520, 280)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setSpacing(12)

        self.name_edit = QLineEdit()
        self.camera_select = PrimeMultiSelect(
            options=self._camera_options,
            placeholder="Select Cameras",
        )
        self.camera_select.setEnabled(cameras_enabled)

        form.addRow("Name *", self.name_edit)
        form.addRow("Cameras", self.camera_select)
        root.addLayout(form)

        helper = QLabel(
            "Camera assignment requires camera view permission."
            if not cameras_enabled
            else "Assign one or more cameras to this department."
        )
        helper.setObjectName("departmentDialogHint")
        helper.setWordWrap(True)
        root.addWidget(helper)

        controls = QHBoxLayout()
        controls.addStretch(1)

        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self._reset)
        controls.addWidget(reset_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        controls.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._submit)
        controls.addWidget(save_btn)
        root.addLayout(controls)

        self._apply_style()
        if self.department is not None:
            self._fill(self.department)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #171a1f;
                color: #f1f5f9;
            }
            QLineEdit {
                background: #232831;
                border: 1px solid #3a424f;
                border-radius: 8px;
                color: #f8fafc;
                padding: 6px 8px;
                min-height: 24px;
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
            QLabel#departmentDialogHint {
                color: #93a1b6;
                font-size: 12px;
            }
            """
        )

    def _fill(self, department: DepartmentResponse) -> None:
        self.name_edit.setText(department.name)
        self.camera_select.set_options(self._camera_options)
        self.camera_select.set_value(department.camera_ids)

    def _reset(self) -> None:
        if self.department is None:
            self.name_edit.clear()
            self.camera_select.set_value([])
            return
        self._fill(self.department)

    def _submit(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing", "Department name is required.")
            return

        payload = {
            "name": name,
            "camera_ids": [int(item) for item in self.camera_select.value()],
        }
        self.submitted.emit(payload, self.is_edit_mode)
        self.accept()


class DepartmentPage(QWidget):
    navigate = Signal(str)

    def __init__(
        self,
        auth_store: Optional[AuthStore] = None,
        camera_source_store: Optional[CameraDepartmentStore] = None,
        department_store: Optional[DepartmentCrudStore] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.auth_store = auth_store or AuthStore(AuthService())
        self.camera_source_store = camera_source_store or CameraDepartmentStore(CameraService())
        self.department_store = department_store or DepartmentCrudStore(DepartmentService())

        self.auth_store.changed.connect(self.refresh)
        self.auth_store.error.connect(self._show_error)
        self.camera_source_store.changed.connect(self.refresh)
        self.camera_source_store.error.connect(self._show_error)
        self.department_store.changed.connect(self.refresh)
        self.department_store.error.connect(self._show_error)
        self.department_store.success.connect(self._show_info)

        self._build_ui()
        self._apply_style()

        self.auth_store.load()
        self.department_store.load()
        if self._can_view_cameras():
            self.camera_source_store.get_camera_for_user(None, silent=True)

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        self.sidebar = UserManagementSidebar("/user/department", self)
        self.sidebar.navigate.connect(self.navigate.emit)
        root.addWidget(self.sidebar)

        main = QFrame()
        main.setObjectName("userMainPanel")
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(18, 14, 18, 18)
        main_layout.setSpacing(14)
        root.addWidget(main, 1)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        main_layout.addLayout(toolbar)

        self.new_btn = QPushButton("+ New")
        self.new_btn.setObjectName("departmentNewBtn")
        self.new_btn.clicked.connect(self.open_create_dialog)
        toolbar.addWidget(self.new_btn)

        toolbar.addStretch(1)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("departmentSearchInput")
        self.search_edit.setPlaceholderText("Search departments...")
        self.search_edit.setMaximumWidth(320)
        self.search_edit.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_edit)

        self.table = PrimeDataTable(page_size=10, row_height=62, show_footer=True)
        self.table.set_columns(
            [
                PrimeTableColumn("id", "ID", width=90, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                PrimeTableColumn("name", "Name", width=220),
                PrimeTableColumn("cameras", "Cameras", stretch=True, sortable=False, searchable=True),
                PrimeTableColumn("actions", "Actions", width=140, sortable=False, searchable=False),
            ]
        )
        self.table.table.horizontalHeader().setStretchLastSection(False)
        self.table.set_cell_widget_factory("cameras", self._camera_cell_widget)
        self.table.set_cell_widget_factory("actions", self._action_widget)
        main_layout.addWidget(self.table, 1)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            USER_MANAGEMENT_SIDEBAR_STYLES
            + """
            QWidget {
                color: #f5f7fb;
            }
            QPushButton#departmentNewBtn {
                background: #3b82f6;
                border: none;
                border-radius: 10px;
                color: white;
                font-size: 14px;
                font-weight: 700;
                padding: 9px 18px;
            }
            QPushButton#departmentNewBtn:hover {
                background: #2f6ce3;
            }
            QLineEdit#departmentSearchInput {
                background: #2b2e34;
                border: 1px solid #3a3e46;
                border-radius: 10px;
                color: #eef2f8;
                padding: 8px 12px;
            }
            QLineEdit#departmentSearchInput:focus {
                border-color: #4e7cff;
            }
            QToolButton#departmentIconBtn {
                background: #2b3340;
                border: 1px solid #425062;
                border-radius: 8px;
                color: #f8fafc;
                min-width: 32px;
                max-width: 32px;
                min-height: 32px;
                max-height: 32px;
            }
            QToolButton#departmentIconBtn:hover {
                background: #35507f;
                border-color: #4d76bb;
            }
            QToolButton#departmentDeleteBtn {
                background: #412326;
                border: 1px solid #7f3b45;
                border-radius: 8px;
                color: #fecaca;
                min-width: 32px;
                max-width: 32px;
                min-height: 32px;
                max-height: 32px;
            }
            QToolButton#departmentDeleteBtn:hover {
                background: #5a2a31;
                border-color: #b14f5b;
            }
            QLabel#departmentEmptyHint {
                color: #8e98a8;
                font-size: 12px;
                font-style: italic;
            }
            QLabel#departmentChip {
                background: #22324e;
                color: #dbeafe;
                border: 1px solid #35507f;
                border-radius: 12px;
                padding: 3px 9px;
                font-size: 11px;
                font-weight: 700;
            }
            """
        )

    def _can_view_cameras(self) -> bool:
        return self.auth_store.has_permission("view_camera")

    def _camera_options(self) -> List[dict]:
        cameras = sorted(self.camera_source_store.cameras, key=lambda item: (item.name or "").lower())
        return [
            {"label": cam.name or f"Camera #{cam.id}", "value": cam.id}
            for cam in cameras
            if cam.id > 0
        ]

    def _department_rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for item in self.department_store.departments:
            camera_names = [camera.name for camera in item.cameras if camera.name]
            rows.append(
                {
                    "id": item.id,
                    "name": item.name,
                    "cameras": ", ".join(camera_names) if camera_names else "No cameras assigned",
                    "_department": item,
                }
            )
        return rows

    def refresh(self) -> None:
        self.table.set_rows(self._department_rows())
        self.new_btn.setEnabled(True)

    def _on_search_changed(self, text: str) -> None:
        self.table.set_filter_text(text)

    def open_create_dialog(self) -> None:
        self._open_dialog(None)

    def _open_dialog(self, department: Optional[DepartmentResponse]) -> None:
        dialog = DepartmentDialog(
            camera_options=self._camera_options(),
            department=department,
            cameras_enabled=self._can_view_cameras(),
            parent=self,
        )
        dialog.submitted.connect(lambda payload, is_edit, dep=department: self._submit_department(dep, payload, is_edit))
        dialog.exec()

    def _submit_department(self, department: Optional[DepartmentResponse], payload: Dict[str, Any], is_edit: bool) -> None:
        if is_edit and department is not None:
            self.department_store.update_department(department.id, payload)
        else:
            self.department_store.create_department(payload)

    def _camera_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        department = row.get("_department")
        if not isinstance(department, DepartmentResponse) or not department.cameras:
            empty = QLabel("No cameras assigned")
            empty.setObjectName("departmentEmptyHint")
            layout.addWidget(empty)
            layout.addStretch(1)
            return wrapper

        visible = department.cameras[:3]
        for camera in visible:
            chip = QLabel(camera.name or f"Camera #{camera.id}")
            chip.setObjectName("departmentChip")
            layout.addWidget(chip)
        extra = len(department.cameras) - len(visible)
        if extra > 0:
            more = QLabel(f"+{extra} more")
            more.setObjectName("departmentChip")
            layout.addWidget(more)
        layout.addStretch(1)
        return wrapper

    def _action_widget(self, row: Dict[str, Any]) -> QWidget:
        department = row.get("_department")
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        edit_btn = QToolButton()
        edit_btn.setObjectName("departmentIconBtn")
        edit_btn.setToolTip("Edit department")
        edit_icon = QIcon(_icon_path("edit.svg"))
        if not edit_icon.isNull():
            edit_btn.setIcon(edit_icon)
        else:
            edit_btn.setText("E")
        edit_btn.clicked.connect(lambda: self._open_dialog(department))
        layout.addWidget(edit_btn)

        delete_btn = QToolButton()
        delete_btn.setObjectName("departmentDeleteBtn")
        delete_btn.setToolTip("Delete department")
        delete_icon = QIcon(_icon_path("trash.svg"))
        if not delete_icon.isNull():
            delete_btn.setIcon(delete_icon)
        else:
            delete_btn.setText("D")
        delete_btn.clicked.connect(lambda: self._confirm_delete(department))
        layout.addWidget(delete_btn)
        return wrapper

    def _confirm_delete(self, department: Any) -> None:
        if not isinstance(department, DepartmentResponse):
            return
        result = QMessageBox.question(
            self,
            "Delete Record",
            f"Are you sure to delete '{department.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self.department_store.delete_department(department.id)

    def _show_info(self, text: str) -> None:
        QMessageBox.information(self, "Info", text)

    def _show_error(self, text: str) -> None:
        QMessageBox.critical(self, "Error", text)


class MainWindow(QMainWindow):
    navigate = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Department Management")
        self.resize(1440, 900)
        page = DepartmentPage()
        page.navigate.connect(self.navigate.emit)
        self.setCentralWidget(page)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
