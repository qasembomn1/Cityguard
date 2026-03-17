from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QDateTime, QSize, Qt, Signal,QRectF
from PySide6.QtGui import QIcon,QPainterPath,QPainter,QColor
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from app.constants._init_ import Constants
from app.models.logs import ActivityLogEntry
from app.models.user import UserResponse
from app.services.home.devices.camera_service import CameraService
from app.services.home.devices.client_service import ClientService
from app.services.home.logs.activity_log_service import ActivityLogService
from app.services.home.user.user_service import UserService
from app.store.home.logs.activity_log_store import ActivityLogStore
from app.ui.button import PrimeButton
from app.ui.select import PrimeSelect
from app.ui.table import PrimeDataTable, PrimeTableColumn
from app.ui.toast import PrimeToastHost
from app.views.home.user._shared import USER_MANAGEMENT_SIDEBAR_STYLES


_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


LOG_NAV_ITEMS = [
    ("User\nLogs", "user_management.svg", "/log/user"),
    ("Client\nLogs", "devices.svg", "/log/client"),
    ("Camera\nLogs", "live_view.svg", "/log/camera"),
]


LOG_PAGE_CONFIG = {
    "/log/user": {
        "resource": "user_log",
        "entity_key": "user",
        "title": "User Logs",
        "entity_label": "User",
        "entity_icon": "user_management.svg",
    },
    "/log/client": {
        "resource": "client_log",
        "entity_key": "client",
        "title": "Client Logs",
        "entity_label": "Client",
        "entity_icon": "devices.svg",
    },
    "/log/camera": {
        "resource": "camera_log",
        "entity_key": "camera",
        "title": "Camera Logs",
        "entity_label": "Camera",
        "entity_icon": "live_view.svg",
    },
}


class OptionalDateTimeField(QWidget):
    def __init__(self, placeholder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._null_value = QDateTime.fromString("2000-01-01 00:00", "yyyy-MM-dd HH:mm")

        self.edit = QDateTimeEdit()
        self.edit.setCalendarPopup(True)
        self.edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.edit.setMinimumDateTime(self._null_value)
        self.edit.setSpecialValueText(placeholder)
        self.edit.setDateTime(self._null_value)
        layout.addWidget(self.edit, 1)

        self.clear_btn = QToolButton()
        self.clear_btn.setObjectName("logsDateClear")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setToolTip("Clear value")
        self.clear_btn.setIcon(QIcon(_icon_path("close.svg")))
        self.clear_btn.setIconSize(QSize(14, 14))
        self.clear_btn.clicked.connect(lambda: self.edit.setDateTime(self._null_value))
        layout.addWidget(self.clear_btn)

    def value(self) -> Optional[str]:
        current = self.edit.dateTime()
        if current <= self._null_value:
            return None
        return current.toString("yyyy-MM-dd HH:mm:ss")

    def clear(self) -> None:
        self.edit.setDateTime(self._null_value)


class ActivityLogsSidebar(QFrame):
    navigate = Signal(str)

    def __init__(self, current_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("userSideNav")
        self.setFixedWidth(96)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        for label, icon_name, path in LOG_NAV_ITEMS:
            btn = QToolButton()
            btn.setText(label)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setFixedSize(72, 72)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setObjectName("userSideBtnActive" if path == current_path else "userSideBtn")
            btn.setToolTip(label.replace("\n", " "))
            icon_file = _icon_path(icon_name)
            if os.path.isfile(icon_file):
                btn.setIcon(QIcon(icon_file))
                btn.setIconSize(QSize(22, 22))
            btn.clicked.connect(lambda _checked=False, p=path: self.navigate.emit(p))
            layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch(1)


class ActivityLogsPage(QWidget):
    navigate = Signal(str)

    def __init__(self, current_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        config = LOG_PAGE_CONFIG[current_path]
        self._current_path = current_path
        self._resource = config["resource"]
        self._entity_key = config["entity_key"]
        self._entity_label = config["entity_label"]
        self._title = config["title"]
        self._entity_icon = config["entity_icon"]

        self.toast = PrimeToastHost(self)
        self.log_store = ActivityLogStore(ActivityLogService(self._resource, self._entity_key))
        self.log_store.changed.connect(self.refresh)
        self.log_store.error.connect(self._show_error)

        self.user_service = UserService()
        self.client_service = ClientService()
        self.camera_service = CameraService()
        self._entity_options: List[Dict[str, Any]] = []
        self._filter_visible = False

        self._build_ui()
        self._apply_style()
        self._load_filter_options()
        self.load_logs()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        self.sidebar = ActivityLogsSidebar(self._current_path, self)
        self.sidebar.navigate.connect(self.navigate.emit)
        root.addWidget(self.sidebar)

        main = QFrame()
        main.setObjectName("logsMainPanel")
        root.addWidget(main, 1)

        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(18, 14, 18, 18)
        main_layout.setSpacing(14)

        hero = QFrame()
        hero.setObjectName("logsHero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(18, 18, 18, 18)
        hero_layout.setSpacing(14)
        main_layout.addWidget(hero)

        icon_wrap = QFrame()
        icon_wrap.setObjectName("logsHeroIconWrap")
        icon_wrap.setFixedSize(56, 56)
        icon_layout = QVBoxLayout(icon_wrap)
        icon_layout.setContentsMargins(14, 14, 14, 14)
        icon_layout.setSpacing(0)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(QIcon(_icon_path(self._entity_icon)).pixmap(28, 28))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_layout.addWidget(icon_lbl)
        hero_layout.addWidget(icon_wrap, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(4)
        hero_layout.addLayout(text_col, 1)

        title = QLabel(self._title)
        title.setObjectName("logsHeroTitle")
        text_col.addWidget(title)

        subtitle = QLabel(f"Browse and filter {self._entity_label.lower()} activity records with server-side search.")
        subtitle.setObjectName("logsHeroSubtitle")
        subtitle.setWordWrap(True)
        text_col.addWidget(subtitle)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        main_layout.addLayout(toolbar)

        self.refresh_btn = PrimeButton("Reload", variant="secondary", size="sm")
        self.refresh_btn.clicked.connect(lambda: self.load_logs(notify=True))
        toolbar.addWidget(self.refresh_btn)

        toolbar.addStretch(1)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("logsSearchInput")
        self.search_edit.setPlaceholderText(f"Search {self._entity_label.lower()} logs...")
        self.search_edit.setMaximumWidth(320)
        self.search_edit.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_edit)

        self.filter_btn = PrimeButton("Filters", variant="info", size="sm")
        self.filter_btn.clicked.connect(self._toggle_filter_panel)
        toolbar.addWidget(self.filter_btn)

        content = QHBoxLayout()
        content.setSpacing(14)
        main_layout.addLayout(content, 1)

        table_wrap = QFrame()
        table_wrap.setObjectName("logsTableWrap")
        table_layout = QVBoxLayout(table_wrap)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)
        content.addWidget(table_wrap, 1)

        self.table = PrimeDataTable(page_size=10, row_height=74, show_footer=True)
        self.table.set_columns(
            [
                PrimeTableColumn("subject", self._entity_label, width=250),
                PrimeTableColumn("action", "Action", width=190),
                PrimeTableColumn("detail", "Details", stretch=True),
                PrimeTableColumn("created_at", "Time", width=170),
            ]
        )
        self.table.set_cell_widget_factory("subject", self._subject_cell_widget)
        self.table.set_cell_widget_factory("action", self._action_cell_widget)
        table_layout.addWidget(self.table)

        self.filter_panel = QFrame()
        self.filter_panel.setObjectName("logsFilterPanel")
        self.filter_panel.setFixedWidth(340)
        self.filter_panel.hide()
        content.addWidget(self.filter_panel)

        panel_layout = QVBoxLayout(self.filter_panel)
        panel_layout.setContentsMargins(18, 18, 18, 18)
        panel_layout.setSpacing(12)

        filter_title = QLabel("Filters")
        filter_title.setObjectName("logsPanelTitle")
        panel_layout.addWidget(filter_title)

        filter_subtitle = QLabel(f"Filter {self._entity_label.lower()} logs by source, action, and date range.")
        filter_subtitle.setObjectName("logsPanelSubtitle")
        filter_subtitle.setWordWrap(True)
        panel_layout.addWidget(filter_subtitle)

        self.entity_select = PrimeSelect(placeholder=f"Select {self._entity_label}")
        panel_layout.addWidget(self._field_block(self._entity_label, self.entity_select))

        self.action_edit = QLineEdit()
        self.action_edit.setObjectName("logsTextInput")
        self.action_edit.setPlaceholderText("Enter action")
        panel_layout.addWidget(self._field_block("Action", self.action_edit))

        self.start_edit = OptionalDateTimeField("Start date")
        panel_layout.addWidget(self._field_block("Start Date", self.start_edit))

        self.end_edit = OptionalDateTimeField("End date")
        panel_layout.addWidget(self._field_block("End Date", self.end_edit))

        actions = QHBoxLayout()
        actions.setSpacing(8)
        panel_layout.addLayout(actions)

        self.reset_btn = PrimeButton("Reset", variant="secondary", size="sm")
        self.reset_btn.clicked.connect(self.reset_filters)
        actions.addWidget(self.reset_btn)

        self.apply_btn = PrimeButton("Search", variant="primary", size="sm")
        self.apply_btn.clicked.connect(self.apply_filters)
        actions.addWidget(self.apply_btn)

        panel_layout.addStretch(1)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            USER_MANAGEMENT_SIDEBAR_STYLES
            + """
            QWidget {
                color: #f5f7fb;
            }
            QFrame#logsMainPanel {
                background: #1f2024;
                border: 1px solid #2e3138;
                border-radius: 12px;
            }
            QFrame#logsHero {
                background: #181d25;
                border: 1px solid #2a3646;
                border-radius: 16px;
            }
            QFrame#logsHeroIconWrap {
                background: rgba(59, 130, 246, 0.14);
                border: 1px solid rgba(96, 165, 250, 0.28);
                border-radius: 16px;
            }
            QLabel#logsHeroTitle {
                color: #f8fafc;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#logsHeroSubtitle {
                color: #9aacbf;
                font-size: 13px;
            }
            QLineEdit#logsSearchInput,
            QLineEdit#logsTextInput,
            QDateTimeEdit {
                background: #2b2e34;
                border: 1px solid #3a3e46;
                border-radius: 10px;
                color: #eef2f8;
                padding: 8px 12px;
                min-height: 24px;
            }
            QLineEdit#logsSearchInput:focus,
            QLineEdit#logsTextInput:focus,
            QDateTimeEdit:focus {
                border-color: #4e7cff;
            }
            QFrame#logsFilterPanel {
                background: #171b21;
                border: 1px solid #2b3340;
                border-radius: 14px;
            }
            QLabel#logsPanelTitle {
                color: #f8fafc;
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#logsPanelSubtitle {
                color: #93a1b6;
                font-size: 12px;
            }
            QLabel#logsFieldLabel {
                color: #d8e1ee;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#logsPrimary {
                color: #f8fafc;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#logsSecondary {
                color: #93a1b6;
                font-size: 11px;
            }
            QLabel#logsActionDefault,
            QLabel#logsActionOnline,
            QLabel#logsActionOffline,
            QLabel#logsActionWarning {
                padding: 5px 10px;
                border-radius: 12px;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#logsActionDefault {
                background: #20344f;
                color: #dbeafe;
                border: 1px solid #35507f;
            }
            QLabel#logsActionOnline {
                background: #123126;
                color: #86efac;
                border: 1px solid #1f7a4f;
            }
            QLabel#logsActionOffline {
                background: #3f2025;
                color: #fecaca;
                border: 1px solid #8a3945;
            }
            QLabel#logsActionWarning {
                background: #3a2b11;
                color: #fcd34d;
                border: 1px solid #a16207;
            }
            QToolButton#logsDateClear {
                background: #2b2e34;
                border: 1px solid #3a3e46;
                border-radius: 10px;
                color: #eef2f8;
                min-width: 38px;
                max-width: 38px;
                min-height: 38px;
                max-height: 38px;
            }
            QToolButton#logsDateClear:hover {
                background: #353942;
            }
            """
        )

    def _field_block(self, label_text: str, field: QWidget) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label = QLabel(label_text)
        label.setObjectName("logsFieldLabel")
        layout.addWidget(label)
        layout.addWidget(field)
        return wrapper

    def _load_filter_options(self) -> None:
        try:
            if self._entity_key == "user":
                items = sorted(
                    self.user_service.list_users(),
                    key=lambda item: ((item.fullname or item.username or "").lower(), item.id),
                )
                self._entity_options = [
                    {"label": item.fullname or item.username or f"User #{item.id}", "value": item.id}
                    for item in items
                    if isinstance(item, UserResponse) and item.id > 0
                ]
            elif self._entity_key == "client":
                items = sorted(
                    self.client_service.get_all_clients(),
                    key=lambda item: ((item.name or "").lower(), item.id),
                )
                self._entity_options = [
                    {"label": item.name or f"Client #{item.id}", "value": item.id}
                    for item in items
                    if item.id > 0
                ]
            else:
                items = sorted(
                    self.camera_service.list_cameras(),
                    key=lambda item: ((item.name or "").lower(), item.id),
                )
                self._entity_options = [
                    {"label": item.name or f"Camera #{item.id}", "value": item.id}
                    for item in items
                    if item.id > 0
                ]
            self.entity_select.set_options(self._entity_options)
        except Exception as exc:
            self._show_error(str(exc))

    def _rows(self) -> List[Dict[str, Any]]:
        return [
            {
                "subject": item.subject.display_name,
                "action": item.action,
                "detail": item.detail or "-",
                "created_at": item.created_at_text,
                "_log": item,
            }
            for item in self.log_store.logs
        ]

    def refresh(self) -> None:
        self.table.set_rows(self._rows())

    def _on_search_changed(self, text: str) -> None:
        self.table.set_filter_text(text)

    def _toggle_filter_panel(self) -> None:
        self._set_filter_visible(not self._filter_visible)

    def _set_filter_visible(self, visible: bool) -> None:
        self._filter_visible = visible
        self.filter_panel.setVisible(visible)
        self.filter_btn.setText("Hide Filters" if visible else "Filters")

    def _current_filters(self) -> Dict[str, Any]:
        entity_value = self.entity_select.value()
        return {
            "entity_id": int(entity_value) if entity_value not in (None, "") else None,
            "action": self.action_edit.text().strip() or None,
            "start_date": self.start_edit.value(),
            "end_date": self.end_edit.value(),
        }

    def load_logs(self, notify: bool = False) -> None:
        filters = self._current_filters()
        rows = self.log_store.load_logs(
            entity_id=filters["entity_id"],
            start_date=filters["start_date"],
            end_date=filters["end_date"],
            action=filters["action"],
        )
        if notify:
            self.toast.success("Logs", f"Loaded {len(rows)} records.")

    def apply_filters(self) -> None:
        self.load_logs()
        self._set_filter_visible(False)

    def reset_filters(self) -> None:
        self.entity_select.clear()
        self.action_edit.clear()
        self.start_edit.clear()
        self.end_edit.clear()
        self.load_logs()
        self._set_filter_visible(False)

    def _show_error(self, text: str) -> None:
        self.toast.error("Logs", text)

    def _subject_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        item = row.get("_log")
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        if not isinstance(item, ActivityLogEntry):
            primary = QLabel("Unknown")
            primary.setObjectName("logsPrimary")
            layout.addWidget(primary)
            return wrapper

        primary = QLabel(item.subject.display_name)
        primary.setObjectName("logsPrimary")
        layout.addWidget(primary)

        secondary_text = item.subject.subtitle or (f"{self._entity_label} #{item.subject.id}" if item.subject.id > 0 else "")
        secondary = QLabel(secondary_text)
        secondary.setObjectName("logsSecondary")
        secondary.setWordWrap(True)
        layout.addWidget(secondary)
        return wrapper

    def _action_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        item = row.get("_log")
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        label = QLabel()
        action_text = item.action if isinstance(item, ActivityLogEntry) else str(row.get("action") or "")
        normalized = action_text.strip().lower()
        if "online" in normalized:
            label.setObjectName("logsActionOnline")
        elif "offline" in normalized:
            label.setObjectName("logsActionOffline")
        elif "bad" in normalized or "warn" in normalized or "fail" in normalized:
            label.setObjectName("logsActionWarning")
        else:
            label.setObjectName("logsActionDefault")
        label.setText(action_text or "-")
        layout.addWidget(label, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)
        return wrapper
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        p.fillPath(path, QColor(Constants.DARK_BG))   # dark bg — cards float above it
        super().paintEvent(event)



class ActivityLogsWindow(QMainWindow):
    navigate = Signal(str)

    def __init__(self, current_path: str) -> None:
        super().__init__()
        page = ActivityLogsPage(current_path)
        page.navigate.connect(self.navigate.emit)
        self.setWindowTitle(LOG_PAGE_CONFIG[current_path]["title"])
        self.setCentralWidget(page)
