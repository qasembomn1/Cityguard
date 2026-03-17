from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal,QRectF
from PySide6.QtGui import QIcon,QColor,QPainter,QPainterPath
from app.constants._init_ import Constants
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
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
from app.models.role import RoleResponse
from app.models.user import UserResponse
from app.services.home.user.department_service import DepartmentService
from app.services.home.user.role_service import RoleService
from app.services.home.user.user_service import UserService
from app.store.home.user.department_store import DepartmentCrudStore
from app.store.home.user.role_store import RoleStore
from app.store.home.user.user_store import UserStore
from app.ui.select import PrimeSelect
from app.ui.table import PrimeDataTable, PrimeTableColumn
from app.views.home.user._shared import USER_MANAGEMENT_SIDEBAR_STYLES, UserManagementSidebar


_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


class UserDialog(QDialog):
    submitted = Signal(dict, bool)

    def __init__(
        self,
        role_options: List[dict],
        department_options: List[dict],
        user: Optional[UserResponse] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.user = user
        self.is_edit_mode = user is not None
        self._role_options = list(role_options)
        self._department_options = list(department_options)

        self.setWindowTitle("User")
        self.resize(720, 440)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        root.addLayout(grid)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Enter username")
        grid.addWidget(self._field_block("Username *", self.username_edit), 0, 0)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Enter password")
        grid.addWidget(self._field_block("Password *", self.password_edit), 0, 1)

        self.fullname_edit = QLineEdit()
        self.fullname_edit.setPlaceholderText("Enter full name")
        grid.addWidget(self._field_block("Full Name *", self.fullname_edit), 1, 0)

        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("Enter email")
        grid.addWidget(self._field_block("Email *", self.email_edit), 1, 1)

        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText("Enter phone number")
        grid.addWidget(self._field_block("Phone *", self.phone_edit), 2, 0)

        self.area_edit = QLineEdit()
        self.area_edit.setPlaceholderText("Enter area")
        grid.addWidget(self._field_block("Area *", self.area_edit), 2, 1)

        self.role_select = PrimeSelect(self._role_options, placeholder="Select Role")
        grid.addWidget(self._field_block("Role *", self.role_select), 3, 0)

        self.department_select = PrimeSelect(
            self._department_options,
            placeholder="Select Department",
        )
        grid.addWidget(self._field_block("Department *", self.department_select), 3, 1)

        self.password_hint = QLabel()
        self.password_hint.setObjectName("usersDialogHint")
        self.password_hint.setWordWrap(True)
        root.addWidget(self.password_hint)

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
        self._reset()

    def _field_block(self, label_text: str, field: QWidget) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label = QLabel(label_text)
        label.setObjectName("usersDialogLabel")
        layout.addWidget(label)
        layout.addWidget(field)
        return wrapper

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
                padding: 8px 10px;
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
            QLabel#usersDialogLabel {
                color: #d8e1ee;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#usersDialogHint {
                color: #8ea0bc;
                font-size: 12px;
            }
            """
        )

    def _fill(self, user: UserResponse) -> None:
        self.username_edit.setText(user.username)
        self.password_edit.clear()
        self.fullname_edit.setText(user.fullname)
        self.email_edit.setText(user.email)
        self.phone_edit.setText(user.phone)
        self.area_edit.setText(user.area)
        self.role_select.set_options(self._role_options)
        self.role_select.set_value(user.role_id)
        self.department_select.set_options(self._department_options)
        self.department_select.set_value(user.department_id)

    def _reset(self) -> None:
        self.role_select.set_options(self._role_options)
        self.department_select.set_options(self._department_options)

        if self.user is None:
            self.username_edit.clear()
            self.password_edit.clear()
            self.fullname_edit.clear()
            self.email_edit.clear()
            self.phone_edit.clear()
            self.area_edit.clear()
            self.role_select.clear()
            self.department_select.clear()
        else:
            self._fill(self.user)

        self.password_hint.setText(
            "Password is required for new users."
            if not self.is_edit_mode
            else "Leave password empty to reuse the current password if the API provided it."
        )

    def _submit(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        fullname = self.fullname_edit.text().strip()
        email = self.email_edit.text().strip()
        phone = self.phone_edit.text().strip()
        area = self.area_edit.text().strip()
        role_id = self.role_select.value()
        department_id = self.department_select.value()

        if not username or not fullname or not email or not phone or not area:
            QMessageBox.warning(self, "Missing", "All text fields are required.")
            return
        if not role_id or not department_id:
            QMessageBox.warning(self, "Missing", "Role and department are required.")
            return
        if not self.is_edit_mode and not password.strip():
            QMessageBox.warning(self, "Missing", "Password is required for new users.")
            return
        if self.is_edit_mode and not password.strip():
            password = self.user.password if self.user is not None else ""
            if not password.strip():
                QMessageBox.warning(
                    self,
                    "Missing",
                    "Password is required for updates because this API does not accept a missing password field.",
                )
                return

        payload = {
            "username": username,
            "password": password,
            "fullname": fullname,
            "email": email,
            "phone": phone,
            "area": area,
            "role_id": int(role_id),
            "department_id": int(department_id),
        }
        self.submitted.emit(payload, self.is_edit_mode)
        self.accept()


class UsersPage(QWidget):
    navigate = Signal(str)

    def __init__(
        self,
        user_store: Optional[UserStore] = None,
        role_store: Optional[RoleStore] = None,
        department_store: Optional[DepartmentCrudStore] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.user_store = user_store or UserStore(UserService())
        self.role_store = role_store or RoleStore(RoleService())
        self.department_store = department_store or DepartmentCrudStore(DepartmentService())

        self.user_store.changed.connect(self.refresh)
        self.user_store.error.connect(self._show_error)
        self.user_store.success.connect(self._show_info)
        self.role_store.changed.connect(self.refresh)
        self.role_store.error.connect(self._show_error)
        self.department_store.changed.connect(self.refresh)
        self.department_store.error.connect(self._show_error)

        self._build_ui()
        self._apply_style()

        self.role_store.load_roles()
        self.department_store.load()
        self.user_store.load()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        self.sidebar = UserManagementSidebar("/user/users", self)
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
        self.new_btn.setObjectName("usersNewBtn")
        self.new_btn.clicked.connect(self.open_create_dialog)
        toolbar.addWidget(self.new_btn)

        toolbar.addStretch(1)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("usersSearchInput")
        self.search_edit.setPlaceholderText("Search users...")
        self.search_edit.setMaximumWidth(320)
        self.search_edit.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_edit)

        self.table = PrimeDataTable(page_size=10, row_height=74, show_footer=True)
        self.table.set_columns(
            [
                PrimeTableColumn(
                    "id",
                    "ID",
                    width=90,
                    alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                ),
                PrimeTableColumn("user", "User", width=260),
                PrimeTableColumn("contact", "Contact", stretch=True),
                PrimeTableColumn("role", "Role", width=170),
                PrimeTableColumn("department", "Department", width=190),
                PrimeTableColumn("actions", "Actions", width=140, sortable=False, searchable=False),
            ]
        )
        self.table.table.horizontalHeader().setStretchLastSection(False)
        self.table.set_cell_widget_factory("user", self._user_cell_widget)
        self.table.set_cell_widget_factory("contact", self._contact_cell_widget)
        self.table.set_cell_widget_factory("role", self._role_cell_widget)
        self.table.set_cell_widget_factory("department", self._department_cell_widget)
        self.table.set_cell_widget_factory("actions", self._action_widget)
        main_layout.addWidget(self.table, 1)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            USER_MANAGEMENT_SIDEBAR_STYLES
            + """
            QWidget {
                color: #f5f7fb;
            }
            QPushButton#usersNewBtn {
                background: #3b82f6;
                border: none;
                border-radius: 10px;
                color: white;
                font-size: 14px;
                font-weight: 700;
                padding: 9px 18px;
            }
            QPushButton#usersNewBtn:hover {
                background: #2f6ce3;
            }
            QLineEdit#usersSearchInput {
                background: #2b2e34;
                border: 1px solid #3a3e46;
                border-radius: 10px;
                color: #eef2f8;
                padding: 8px 12px;
            }
            QLineEdit#usersSearchInput:focus {
                border-color: #4e7cff;
            }
            QToolButton#usersIconBtn {
                background: #2b3340;
                border: 1px solid #425062;
                border-radius: 8px;
                color: #f8fafc;
                min-width: 32px;
                max-width: 32px;
                min-height: 32px;
                max-height: 32px;
            }
            QToolButton#usersIconBtn:hover {
                background: #35507f;
                border-color: #4d76bb;
            }
            QToolButton#usersDeleteBtn {
                background: #412326;
                border: 1px solid #7f3b45;
                border-radius: 8px;
                color: #fecaca;
                min-width: 32px;
                max-width: 32px;
                min-height: 32px;
                max-height: 32px;
            }
            QToolButton#usersDeleteBtn:hover {
                background: #5a2a31;
                border-color: #b14f5b;
            }
            QLabel#usersPrimary {
                color: #f8fafc;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#usersSecondary {
                color: #93a1b6;
                font-size: 11px;
            }
            QLabel#usersChip {
                background: #22324e;
                color: #dbeafe;
                border: 1px solid #35507f;
                border-radius: 12px;
                padding: 3px 9px;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#usersMuted {
                color: #8e98a8;
                font-size: 12px;
                font-style: italic;
            }
            """
        )

    def _role_lookup(self) -> Dict[int, str]:
        return {
            item.id: item.name
            for item in self.role_store.roles
            if isinstance(item, RoleResponse) and item.id > 0
        }

    def _department_lookup(self) -> Dict[int, str]:
        return {
            item.id: item.name
            for item in self.department_store.departments
            if isinstance(item, DepartmentResponse) and item.id > 0
        }

    def _role_options(self) -> List[dict]:
        roles = sorted(self.role_store.roles, key=lambda item: (item.name or "").lower())
        return [
            {"label": role.name or f"Role #{role.id}", "value": role.id}
            for role in roles
            if role.id > 0
        ]

    def _department_options(self) -> List[dict]:
        departments = sorted(
            self.department_store.departments,
            key=lambda item: (item.name or "").lower(),
        )
        return [
            {"label": department.name or f"Department #{department.id}", "value": department.id}
            for department in departments
            if department.id > 0
        ]

    def _user_rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        role_lookup = self._role_lookup()
        department_lookup = self._department_lookup()
        for item in self.user_store.users:
            contact_parts = [part for part in (item.email, item.phone, item.area) if part]
            rows.append(
                {
                    "id": item.id,
                    "user": " ".join(part for part in (item.fullname, item.username) if part).strip(),
                    "contact": " | ".join(contact_parts),
                    "role": item.role_name or role_lookup.get(item.role_id, "Unassigned"),
                    "department": item.department_name or department_lookup.get(item.department_id, "Unassigned"),
                    "_user": item,
                }
            )
        return rows

    def refresh(self) -> None:
        self.table.set_rows(self._user_rows())

    def _on_search_changed(self, text: str) -> None:
        self.table.set_filter_text(text)

    def open_create_dialog(self) -> None:
        self._open_dialog(None)

    def _open_dialog(self, user: Optional[UserResponse]) -> None:
        dialog = UserDialog(
            role_options=self._role_options(),
            department_options=self._department_options(),
            user=user,
            parent=self,
        )
        dialog.submitted.connect(lambda payload, is_edit, current=user: self._submit_user(current, payload, is_edit))
        dialog.exec()

    def _submit_user(self, user: Optional[UserResponse], payload: Dict[str, Any], is_edit: bool) -> None:
        if is_edit and user is not None:
            self.user_store.update_user(user.id, payload)
        else:
            self.user_store.create_user(payload)

    def _user_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        user = row.get("_user")
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        if not isinstance(user, UserResponse):
            empty = QLabel("Unknown user")
            empty.setObjectName("usersMuted")
            layout.addWidget(empty)
            return wrapper

        primary = QLabel(user.fullname or user.username or "Unnamed User")
        primary.setObjectName("usersPrimary")
        layout.addWidget(primary)

        secondary = QLabel(f"@{user.username}" if user.username else "No username")
        secondary.setObjectName("usersSecondary")
        layout.addWidget(secondary)
        return wrapper

    def _contact_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        user = row.get("_user")
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        if not isinstance(user, UserResponse):
            empty = QLabel("No contact info")
            empty.setObjectName("usersMuted")
            layout.addWidget(empty)
            return wrapper

        primary = QLabel(user.email or "No email")
        primary.setObjectName("usersPrimary")
        layout.addWidget(primary)

        details = [part for part in (user.phone, user.area) if part]
        secondary = QLabel(" | ".join(details) if details else "No phone or area")
        secondary.setObjectName("usersSecondary")
        layout.addWidget(secondary)
        return wrapper

    def _badge_widget(self, text: str, empty_text: str) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        label = QLabel(text or empty_text)
        label.setObjectName("usersChip" if text else "usersMuted")
        layout.addWidget(label)
        layout.addStretch(1)
        return wrapper

    def _role_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        return self._badge_widget(str(row.get("role") or ""), "Unassigned")

    def _department_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        return self._badge_widget(str(row.get("department") or ""), "Unassigned")

    def _action_widget(self, row: Dict[str, Any]) -> QWidget:
        user = row.get("_user")
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        edit_btn = QToolButton()
        edit_btn.setObjectName("usersIconBtn")
        edit_btn.setToolTip("Edit user")
        edit_icon = QIcon(_icon_path("edit.svg"))
        if not edit_icon.isNull():
            edit_btn.setIcon(edit_icon)
        else:
            edit_btn.setText("E")
        edit_btn.clicked.connect(lambda: self._open_dialog(user))
        layout.addWidget(edit_btn)

        delete_btn = QToolButton()
        delete_btn.setObjectName("usersDeleteBtn")
        delete_btn.setToolTip("Delete user")
        delete_icon = QIcon(_icon_path("trash.svg"))
        if not delete_icon.isNull():
            delete_btn.setIcon(delete_icon)
        else:
            delete_btn.setText("D")
        delete_btn.clicked.connect(lambda: self._confirm_delete(user))
        layout.addWidget(delete_btn)
        return wrapper

    def _confirm_delete(self, user: Any) -> None:
        if not isinstance(user, UserResponse):
            return
        display_name = user.fullname or user.username or f"User #{user.id}"
        result = QMessageBox.question(
            self,
            "Delete Record",
            f"Are you sure to delete '{display_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self.user_store.delete_user(user.id)

    def _show_info(self, text: str) -> None:
        QMessageBox.information(self, "Info", text)

    def _show_error(self, text: str) -> None:
        QMessageBox.critical(self, "Error", text)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        p.fillPath(path, QColor(Constants.DARK_BG))   # dark bg — cards float above it
        super().paintEvent(event)

