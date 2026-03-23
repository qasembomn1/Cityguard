from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QSize, Qt, Signal,QRectF
from PySide6.QtGui import QIcon,QPainterPath,QPainter,QColor
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models.role import PermissionResponse, RoleResponse
from app.services.home.user.role_service import RoleService
from app.store.home.user.role_store import RoleStore
from app.ui.button import PrimeButton
from app.ui.checkbox import PrimeCheckBox
from app.ui.confirm_dialog import PrimeConfirmDialog
from app.ui.dialog import PrimeDialog
from app.ui.input import PrimeInput
from app.ui.table import PrimeDataTable, PrimeTableColumn
from app.ui.toast import show_toast_message
from app.views.home.user._shared import USER_MANAGEMENT_SIDEBAR_STYLES, UserManagementSidebar
from app.constants._init_ import Constants

_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


class RoleDialog(PrimeDialog):
    submitted = Signal(dict, bool)

    def __init__(
        self,
        permissions: List[PermissionResponse],
        role: Optional[RoleResponse] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        title = "Edit Role" if role is not None else "Add Role"
        super().__init__(
            title=title,
            parent=parent,
            width=860,
            height=640,
            ok_text="Save",
            cancel_text="Cancel",
        )
        self.role = role
        self.is_edit_mode = role is not None
        self.permissions = list(permissions)
        self._permission_checks: Dict[int, PrimeCheckBox] = {}

        # ── form content ──
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(12)

        name_label = QLabel("Role Name *")
        name_label.setStyleSheet("color: #d8e1ee; font-size: 12px; font-weight: 700;")
        container_layout.addWidget(name_label)

        self.name_edit = PrimeInput(placeholder_text="Role Name")
        container_layout.addWidget(self.name_edit)

        perm_label = QLabel("Permissions")
        perm_label.setStyleSheet("color: #d8e1ee; font-size: 12px; font-weight: 700;")
        container_layout.addWidget(perm_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")

        content = QWidget()
        self.permission_grid = QGridLayout(content)
        self.permission_grid.setContentsMargins(0, 0, 0, 0)
        self.permission_grid.setHorizontalSpacing(12)
        self.permission_grid.setVerticalSpacing(12)
        scroll.setWidget(content)
        container_layout.addWidget(scroll, 1)

        self.set_content(container, fill_height=True)

        self._build_permission_cards()

        # ── footer: add Reset before Cancel ──
        reset_btn = PrimeButton("Reset", variant="secondary", mode="outline", size="sm", width=80)
        reset_btn.clicked.connect(self._reset)
        self.footer_widget.layout().insertWidget(1, reset_btn)

        # ── redirect ok → _submit ──
        self.ok_button.clicked.disconnect()
        self.ok_button.clicked.connect(self._submit)

        self._reset()

    def _build_permission_cards(self) -> None:
        while self.permission_grid.count():
            item = self.permission_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._permission_checks.clear()

        for index, permission in enumerate(self.permissions):
            card = QFrame()
            card.setStyleSheet(
                "QFrame { background: #11161f; border-radius: 12px; }"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(8)

            label = QLabel(permission.display_name)
            label.setWordWrap(True)
            label.setStyleSheet("background: transparent; border: none; color: #f8fafc; font-size: 12px; font-weight: 700;")
            card_layout.addWidget(label)

            check = PrimeCheckBox("Enabled")
            self._permission_checks[permission.id] = check
            card_layout.addWidget(check)

            row = index // 4
            col = index % 4
            self.permission_grid.addWidget(card, row, col)

    def _selected_permission_ids(self) -> List[int]:
        return [pid for pid, check in self._permission_checks.items() if check.isChecked()]

    def _reset(self) -> None:
        if self.role is None:
            self.name_edit.clear()
            for check in self._permission_checks.values():
                check.setChecked(False)
        else:
            self.name_edit.setText(self.role.name)
            selected = set(self.role.permission_ids)
            for pid, check in self._permission_checks.items():
                check.setChecked(pid in selected)

    def _submit(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            show_toast_message(self, "warn", "Missing", "Role name is required.")
            return

        payload = {
            "name": name,
            "permission_ids": self._selected_permission_ids(),
        }
        self.submitted.emit(payload, self.is_edit_mode)
        self.accept()


class RolePage(QWidget):
    navigate = Signal(str)

    def __init__(
        self,
        role_store: Optional[RoleStore] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.role_store = role_store or RoleStore(RoleService())

        self.role_store.changed.connect(self.refresh)
        self.role_store.error.connect(self._show_error)
        self.role_store.success.connect(self._show_info)

        self._build_ui()
        self._apply_style()

        self.role_store.load_roles()
        self.role_store.load_permissions()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        self.sidebar = UserManagementSidebar("/user/roles", self)
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

        self.new_btn = PrimeButton("+ New", variant="primary", mode="filled", size="sm", width=90)
        self.new_btn.clicked.connect(self.open_create_dialog)
        toolbar.addWidget(self.new_btn)

        toolbar.addStretch(1)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("roleSearchInput")
        self.search_edit.setPlaceholderText("Search roles...")
        self.search_edit.setMaximumWidth(320)
        self.search_edit.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_edit)

        self.table = PrimeDataTable(page_size=10, row_height=62, show_footer=True)
        self.table.set_columns(
            [
                PrimeTableColumn("id", "ID", width=90, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                PrimeTableColumn("name", "Role Name", width=220),
                PrimeTableColumn("permissions", "Permissions", stretch=True, sortable=False, searchable=True),
                PrimeTableColumn("actions", "Actions", width=140, sortable=False, searchable=False),
            ]
        )
        self.table.table.horizontalHeader().setStretchLastSection(False)
        self.table.set_cell_widget_factory("permissions", self._permissions_cell_widget)
        self.table.set_cell_widget_factory("actions", self._action_widget)
        main_layout.addWidget(self.table, 1)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            USER_MANAGEMENT_SIDEBAR_STYLES
            + """
            QWidget {
                color: #f5f7fb;
            }

            QLineEdit#roleSearchInput {
                background: #2b2e34;
                border: 1px solid #3a3e46;
                border-radius: 10px;
                color: #eef2f8;
                padding: 8px 12px;
            }
            QLineEdit#roleSearchInput:focus {
                border-color: #4e7cff;
            }
            QToolButton#roleIconBtn {
                background: #2b3340;
                border: 1px solid #425062;
                border-radius: 8px;
                color: #f8fafc;
                min-width: 32px;
                max-width: 32px;
                min-height: 32px;
                max-height: 32px;
            }
            QToolButton#roleIconBtn:hover {
                background: #35507f;
                border-color: #4d76bb;
            }
            QToolButton#roleDeleteBtn {
                background: #412326;
                border: 1px solid #7f3b45;
                border-radius: 8px;
                color: #fecaca;
                min-width: 32px;
                max-width: 32px;
                min-height: 32px;
                max-height: 32px;
            }
            QToolButton#roleDeleteBtn:hover {
                background: #5a2a31;
                border-color: #b14f5b;
            }
            QLabel#roleEmptyHint {
                color: #8e98a8;
                font-size: 12px;
                font-style: italic;
            }
            QLabel#roleChip {
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

    def _role_rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for item in self.role_store.roles:
            permission_names = [permission.display_name for permission in item.permissions]
            rows.append(
                {
                    "id": item.id,
                    "name": item.name,
                    "permissions": ", ".join(permission_names) if permission_names else "No permissions",
                    "_role": item,
                }
            )
        return rows

    def refresh(self) -> None:
        self.table.set_rows(self._role_rows())

    def _on_search_changed(self, text: str) -> None:
        self.table.set_filter_text(text)

    def open_create_dialog(self) -> None:
        self._open_dialog(None)

    def _open_dialog(self, role: Optional[RoleResponse]) -> None:
        dialog = RoleDialog(self.role_store.permissions, role=role, parent=self)
        dialog.submitted.connect(lambda payload, is_edit, current=role: self._submit_role(current, payload, is_edit))
        dialog.exec()

    def _submit_role(self, role: Optional[RoleResponse], payload: Dict[str, Any], is_edit: bool) -> None:
        if is_edit and role is not None:
            self.role_store.update_role(role.id, payload)
        else:
            self.role_store.create_role(payload)

    def _permissions_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        role = row.get("_role")
        if not isinstance(role, RoleResponse) or not role.permissions:
            empty = QLabel("No permissions")
            empty.setObjectName("roleEmptyHint")
            layout.addWidget(empty)
            layout.addStretch(1)
            return wrapper

        visible = role.permissions[:3]
        for permission in visible:
            chip = QLabel(permission.display_name)
            chip.setObjectName("roleChip")
            layout.addWidget(chip)
        extra = len(role.permissions) - len(visible)
        if extra > 0:
            more = QLabel(f"+{extra} more")
            more.setObjectName("roleChip")
            layout.addWidget(more)
        layout.addStretch(1)
        return wrapper

    def _action_button(self, icon_name: str, tooltip: str, bg: str, border: str, size: int = 34) -> QToolButton:
        btn = QToolButton()
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(size, size)
        btn.setToolTip(tooltip)
        btn.setStyleSheet(
            f"""
            QToolButton {{
                background: {bg};
                border: 1px solid {border};
                border-radius: {size // 2}px;
            }}
            QToolButton:hover {{
                border-color: #f8fafc;
            }}
            QToolButton:disabled {{
                background: #2b2d33;
                border-color: #3b3f47;
            }}
            """
        )
        icon_file = _icon_path(icon_name)
        if os.path.isfile(icon_file):
            icon_px = max(12, size - 16)
            btn.setIcon(QIcon(icon_file))
            btn.setIconSize(QSize(icon_px, icon_px))
        return btn

    def _action_widget(self, row: Dict[str, Any]) -> QWidget:
        role = row.get("_role")
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if not isinstance(role, RoleResponse):
            return wrapper

        edit_btn = self._action_button("edit.svg", "Edit role", "#3578f6", "#4e8cff")
        edit_btn.clicked.connect(lambda: self._open_dialog(role))
        layout.addWidget(edit_btn)

        delete_btn = self._action_button("trash.svg", "Delete role", "#ef4444", "#ff6464")
        delete_btn.clicked.connect(lambda: self._confirm_delete(role))
        layout.addWidget(delete_btn)
        return wrapper

    def _confirm_delete(self, role: Any) -> None:
        if not isinstance(role, RoleResponse):
            return
        confirmed = PrimeConfirmDialog.ask(
            parent=self,
            title="Delete Role",
            message=f"Are you sure you want to delete '{role.name}'? This action cannot be undone.",
            ok_text="Delete",
            cancel_text="Cancel",
        )
        if not confirmed:
            return
        self.role_store.delete_role(role.id)

    def _show_info(self, text: str) -> None:
        show_toast_message(self, "info", "Info", text)

    def _show_error(self, text: str) -> None:
        show_toast_message(self, "error", "Error", text)
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        p.fillPath(path, QColor(Constants.DARK_BG))   # dark bg — cards float above it
        super().paintEvent(event)
