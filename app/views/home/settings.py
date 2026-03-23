from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from PySide6.QtCore import QDate, Qt, QTimer, Signal,QRectF
from PySide6.QtGui import QIcon,QColor,QPainter,QPainterPath
from app.constants._init_ import Constants
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models.settings import AlarmSetting, RecordSetting, RepeatedSetting
from app.services.home.settings_service import SettingsService
from app.store.home.setting.settings_store import SettingsStore
from app.ui.button import PrimeButton
from app.ui.confirm_dialog import PrimeConfirmDialog
from app.ui.toast import PrimeToastHost
from app.widgets.svg_widget import SvgWidget


_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../resources/icons")
)
_NULL_DATE = QDate(2000, 1, 1)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


class OptionalDateField(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.edit = QDateEdit()
        self.edit.setCalendarPopup(True)
        self.edit.setDisplayFormat("yyyy-MM-dd")
        self.edit.setMinimumDate(_NULL_DATE)
        self.edit.setSpecialValueText("Not set")
        self.edit.setDate(_NULL_DATE)
        self.edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.edit, 1)

        self.clear_btn = QToolButton()
        self.clear_btn.setObjectName("settingsDateClear")
        self.clear_btn.setText("Clear")
        self.clear_btn.clicked.connect(lambda: self.edit.setDate(_NULL_DATE))
        layout.addWidget(self.clear_btn)

    def value(self) -> str | None:
        value = self.edit.date()
        if value <= _NULL_DATE:
            return None
        return value.toString("yyyy-MM-dd")

    def set_value(self, value: str | None) -> None:
        text = str(value or "").strip()
        if not text:
            self.edit.setDate(_NULL_DATE)
            return
        qdate = QDate.fromString(text[:10], "yyyy-MM-dd")
        self.edit.setDate(qdate if qdate.isValid() else _NULL_DATE)


class SettingsPage(QWidget):
    navigate = Signal(str)

    _TAB_DEFS = (
        ("overview", "Overview", "settings.svg"),
        ("record", "Record", "report.svg"),
        ("alarm", "Alarm", "notification.svg"),
        ("repeated", "Repeated", "calendar.svg"),
        ("server", "Server", "monitor.svg"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.toast = PrimeToastHost(self)
        self.store = SettingsStore(SettingsService())
        self._nav_buttons: dict[str, QToolButton] = {}
        self._card_values: dict[str, QLabel] = {}
        self._last_sync_label: QLabel | None = None

        self._init_fields()
        self._build_ui()
        self._apply_style()
        self._set_active_tab("overview")
        QTimer.singleShot(0, self.reload_all_settings)

    def _init_fields(self) -> None:
        self.record_valid_space = self._make_spinbox(0, 999_999_999)
        self.record_quality = self._make_combo(
            (
                ("Good", "good"),
                ("Normal", "normal"),
                ("Bad", "bad"),
            )
        )
        self.record_is_record = self._make_bool_combo()
        self.record_is_remove = self._make_bool_combo()
        self.record_save_path = self._make_line_edit("Enter save path")
        self.record_fps_delay = self._make_spinbox(0, 999_999)
        self.record_backup_last_date = OptionalDateField()

        self.record_media_server_ip = self._make_line_edit("Enter media server IP")
        self.record_media_server_port = self._make_spinbox(0, 999_999)
        self.record_server_public_ip = self._make_line_edit("Enter server public IP")
        self.record_server_public_port = self._make_spinbox(0, 999_999)
        self.record_db_limit_days = self._make_spinbox(0, 99_999)
        self.record_backup_days = self._make_spinbox(0, 99_999)
        self.record_backup_path = self._make_line_edit("Enter backup path")

        self.alarm_blacklist_date = OptionalDateField()
        self.alarm_repeated_date = OptionalDateField()
        self.alarm_blacklist_alarm = self._make_bool_combo()

        self.repeated_cars = self._make_spinbox(0, 99_999)
        self.repeated_in_time = self._make_spinbox(0, 99_999)

        self.server_interface_select = QComboBox()
        self.server_interface_select.addItem("Select interface", "")
        self.server_interface_select.currentIndexChanged.connect(self._on_server_interface_changed)
        self.server_ip_address = self._make_line_edit("192.168.1.10")
        self.server_subnet_mask = self._make_line_edit("255.255.255.0")
        self.server_gateway = self._make_line_edit("192.168.1.1")
        self.server_prefix_length = self._make_line_edit("24")
        self.server_dns = self._make_line_edit("8.8.8.8, 1.1.1.1")

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)

        sidebar = QFrame()
        sidebar.setObjectName("settingsSidebar")
        sidebar.setFixedWidth(230)
        root.addWidget(sidebar)

        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(18, 18, 18, 18)
        side_layout.setSpacing(14)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)
        icon = SvgWidget(_icon_path("settings.svg"))
        icon.setFixedSize(26, 26)
        header_row.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)

        title = QLabel("Settings")
        title.setObjectName("settingsSidebarTitle")
        header_row.addWidget(title, 1)
        side_layout.addLayout(header_row)

        subtitle = QLabel("Manage record, alarm, repeated-detection, and server network behavior.")
        subtitle.setObjectName("settingsSidebarSubtitle")
        subtitle.setWordWrap(True)
        side_layout.addWidget(subtitle)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for tab_id, label, icon_name in self._TAB_DEFS:
            btn = QToolButton()
            btn.setObjectName("settingsNavButton")
            btn.setText(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setFixedHeight(46)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setIcon(QIcon(_icon_path(icon_name)))
            btn.setIconSize(icon.size())
            btn.clicked.connect(lambda checked=False, value=tab_id: self._set_active_tab(value))
            self._nav_group.addButton(btn)
            side_layout.addWidget(btn)
            self._nav_buttons[tab_id] = btn

        side_layout.addStretch(1)

        self._reload_all_btn = PrimeButton("Reload All", variant="info", size="sm")
        self._reload_all_btn.clicked.connect(lambda: self.reload_all_settings(notify=True))
        side_layout.addWidget(self._reload_all_btn)

        main = QFrame()
        main.setObjectName("settingsMain")
        root.addWidget(main, 1)

        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._stack = QStackedWidget()
        main_layout.addWidget(self._stack, 1)

        self._stack.addWidget(self._wrap_page(self._build_overview_tab()))
        self._stack.addWidget(self._wrap_page(self._build_record_tab()))
        self._stack.addWidget(self._wrap_page(self._build_alarm_tab()))
        self._stack.addWidget(self._wrap_page(self._build_repeated_tab()))
        self._stack.addWidget(self._wrap_page(self._build_server_tab()))

    def _apply_style(self) -> None:
        self.setStyleSheet(
            f"""
            QWidget {{
                color: #e5ebf5;
                font-size: 13px;
            }}
            QFrame#settingsSidebar {{
                background: #161a20;
                border: 1px solid #2b3340;
                border-radius: 18px;
            }}
            QLabel#settingsSidebarTitle {{
                color: #f8fafc;
                font-size: 20px;
                font-weight: 700;
            }}
            QLabel#settingsSidebarSubtitle {{
                color: #8fa0b8;
                font-size: 12px;
                line-height: 1.45em;
            }}
            QToolButton#settingsNavButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 12px;
                color: #a7b3c8;
                font-size: 13px;
                font-weight: 600;
                min-height: 46px;
                padding: 0 14px;
                text-align: left;
            }}
            QToolButton#settingsNavButton:hover {{
                background: rgba(59, 130, 246, 0.08);
                border-color: rgba(59, 130, 246, 0.22);
                color: #f8fbff;
            }}
            QToolButton#settingsNavButton:checked {{
                background: rgba(59, 130, 246, 0.16);
                border-color: rgba(96, 165, 250, 0.44);
                color: white;
            }}
            QFrame#settingsMain {{
                background: #11151b;
                border: 1px solid #232b38;
                border-radius: 20px;
            }}
            QScrollArea#settingsScroll {{
                background: transparent;
                border: none;
            }}
            QScrollArea#settingsScroll > QWidget > QWidget {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 8px 2px 8px 2px;
            }}
            QScrollBar::handle:vertical {{
                background: #334155;
                border-radius: 5px;
                min-height: 24px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QFrame#settingsHero {{
                background: #161d28;
                border: 1px solid #2d3748;
                border-radius: 18px;
            }}
            QLabel#settingsHeroTitle {{
                color: #f8fafc;
                font-size: 24px;
                font-weight: 700;
            }}
            QLabel#settingsHeroSubtitle {{
                color: #9fb0c7;
                font-size: 13px;
                line-height: 1.45em;
            }}
            QLabel#settingsHeroKicker {{
                color: #60a5fa;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
            }}
            QFrame#settingsPanel, QFrame#settingsMetricCard, QFrame#settingsActionCard {{
                background: #171d27;
                border: 1px solid #283241;
                border-radius: 16px;
            }}
            QLabel#settingsPanelTitle {{
                color: #f8fafc;
                font-size: 17px;
                font-weight: 700;
            }}
            QLabel#settingsPanelSubtitle {{
                color: #8fa0b8;
                font-size: 12px;
            }}
            QLabel#settingsFieldLabel {{
                color: #d9e2ef;
                font-size: 12px;
                font-weight: 700;
            }}
            QLabel#settingsFieldHint {{
                color: #7f8da5;
                font-size: 11px;
            }}
            QLabel#settingsMetricTitle {{
                color: #9fb0c7;
                font-size: 12px;
                font-weight: 600;
            }}
            QLabel#settingsMetricValue {{
                color: #f8fafc;
                font-size: 20px;
                font-weight: 700;
            }}
            QLabel#settingsMetricHint {{
                color: #7f8da5;
                font-size: 11px;
            }}
            QLabel#settingsNoteTitle {{
                color: #f8fafc;
                font-size: 14px;
                font-weight: 700;
            }}
            QLabel#settingsNoteBody {{
                color: #9fb0c7;
                font-size: 12px;
                line-height: 1.45em;
            }}
            QLineEdit, QSpinBox, QComboBox, QDateEdit {{
                background: #202734;
                border: 1px solid #324050;
                border-radius: 10px;
                color: #f8fafc;
                min-height: 38px;
                padding: 0 12px;
            }}
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QDateEdit:focus {{
                border-color: #60a5fa;
            }}
            QComboBox::drop-down, QDateEdit::drop-down {{
                border: none;
                width: 26px;
            }}
            QComboBox QAbstractItemView {{
                background: #111827;
                color: #f8fafc;
                selection-background-color: #1d4ed8;
                border: 1px solid #283241;
            }}
            QToolButton#settingsDateClear {{
                background: #202734;
                border: 1px solid #324050;
                border-radius: 10px;
                color: #cbd5e1;
                min-height: 38px;
                padding: 0 12px;
                font-weight: 600;
            }}
            QToolButton#settingsDateClear:hover {{
                background: #2b3443;
                color: white;
            }}
            """
        )

    def _build_overview_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        layout.addWidget(
            self._hero_card(
                "Settings Overview",
                "Tune system behavior from one place. This page mirrors the control-center layout while staying bound to the available settings APIs.",
                "Control Center",
                "settings.svg",
                "#3b82f6",
            )
        )

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(14)
        metrics.setVerticalSpacing(14)
        layout.addLayout(metrics)

        metrics.addWidget(
            self._metric_card(
                "Record Quality",
                "Current capture quality profile.",
                "#2563eb",
                "record_quality",
            ),
            0,
            0,
        )
        metrics.addWidget(
            self._metric_card(
                "Repeated Trigger",
                "How repeated vehicles are detected.",
                "#7c3aed",
                "repeated_rule",
            ),
            0,
            1,
        )
        metrics.addWidget(
            self._metric_card(
                "Blacklist Alarm",
                "Whether blacklist alerts are active.",
                "#f97316",
                "alarm_status",
            ),
            1,
            0,
        )
        metrics.addWidget(
            self._metric_card(
                "Backup Path",
                "Configured record backup destination.",
                "#14b8a6",
                "backup_path",
            ),
            1,
            1,
        )

        action_card = QFrame()
        action_card.setObjectName("settingsActionCard")
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(18, 18, 18, 18)
        action_layout.setSpacing(12)
        layout.addWidget(action_card)

        action_title = QLabel("Quick Actions")
        action_title.setObjectName("settingsPanelTitle")
        action_layout.addWidget(action_title)

        action_subtitle = QLabel("Jump directly to a section and save changes without leaving the page.")
        action_subtitle.setObjectName("settingsPanelSubtitle")
        action_subtitle.setWordWrap(True)
        action_layout.addWidget(action_subtitle)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        action_layout.addLayout(button_row)

        for label, variant, tab_id in (
            ("Open Record", "danger", "record"),
            ("Open Alarm", "warning", "alarm"),
            ("Open Repeated", "help", "repeated"),
            ("Open Server", "info", "server"),
        ):
            btn = PrimeButton(label, variant=variant, size="sm")
            btn.clicked.connect(lambda checked=False, value=tab_id: self._set_active_tab(value))
            button_row.addWidget(btn)
        button_row.addStretch(1)

        self._last_sync_label = QLabel("Last sync: waiting for data")
        self._last_sync_label.setObjectName("settingsPanelSubtitle")
        action_layout.addWidget(self._last_sync_label)

        layout.addStretch(1)
        return page

    def _build_record_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        layout.addWidget(
            self._hero_card(
                "Record Settings",
                "Configure storage, retention, media publishing, and backup behavior for the recorder pipeline.",
                "Recorder",
                "report.svg",
                "#ef4444",
            )
        )

        controls = QHBoxLayout()
        controls.addStretch(1)
        self._record_reset_btn = PrimeButton("Reset", variant="secondary", size="sm")
        self._record_reset_btn.clicked.connect(lambda: self._load_record_setting(notify=True))
        controls.addWidget(self._record_reset_btn)
        self._record_save_btn = PrimeButton("Save Settings", variant="danger", size="sm")
        self._record_save_btn.clicked.connect(self.save_record_setting)
        controls.addWidget(self._record_save_btn)
        layout.addLayout(controls)

        columns = QHBoxLayout()
        columns.setSpacing(14)
        layout.addLayout(columns)

        left_panel = self._form_panel(
            "Capture and Retention",
            "Set capture quality, recording behavior, and local storage policies.",
        )
        left_grid = QGridLayout()
        left_grid.setHorizontalSpacing(12)
        left_grid.setVerticalSpacing(12)
        left_panel.layout().addLayout(left_grid)
        self._add_field(left_grid, 0, "Valid Space (MB)", self.record_valid_space, "Minimum free space before cleanup.")
        self._add_field(left_grid, 1, "Picture Quality", self.record_quality, "Default quality for recorded images.")
        self._add_field(left_grid, 2, "Record Video", self.record_is_record, "Enable or disable video recording.")
        self._add_field(left_grid, 3, "Delete Old Images", self.record_is_remove, "Automatically remove older captures.")
        self._add_field(left_grid, 4, "Save Path", self.record_save_path, "Folder used by the recorder service.")
        self._add_field(left_grid, 5, "FPS Delay (ms)", self.record_fps_delay, "Delay between processed frames.")
        self._add_field(left_grid, 6, "Last Backup Date", self.record_backup_last_date, "Optional date marker for the last backup.")
        columns.addWidget(left_panel, 1)

        right_panel = self._form_panel(
            "Publishing and Backup",
            "Control external media endpoints and backup rotation limits.",
        )
        right_grid = QGridLayout()
        right_grid.setHorizontalSpacing(12)
        right_grid.setVerticalSpacing(12)
        right_panel.layout().addLayout(right_grid)
        self._add_field(right_grid, 0, "Media Server IP", self.record_media_server_ip, "Destination IP for media streaming.")
        self._add_field(right_grid, 1, "Media Server Port", self.record_media_server_port, "Destination port for media streaming.")
        self._add_field(right_grid, 2, "Server Public IP", self.record_server_public_ip, "Public-facing address used by clients.")
        self._add_field(right_grid, 3, "Server Public Port", self.record_server_public_port, "Public-facing port used by clients.")
        self._add_field(right_grid, 4, "Database Limit Days", self.record_db_limit_days, "Maximum age of retained database data.")
        self._add_field(right_grid, 5, "Backup Days", self.record_backup_days, "How many days of backups to keep.")
        self._add_field(right_grid, 6, "Backup Path", self.record_backup_path, "Folder used to store backup files.")
        columns.addWidget(right_panel, 1)

        layout.addWidget(
            self._note_card(
                "Save behavior",
                "Changes are sent to `/api/v1/settings/record_setting/update`, then the page reloads the current record settings from the server so the UI stays synchronized.",
            )
        )
        layout.addStretch(1)
        return page

    def _build_alarm_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        layout.addWidget(
            self._hero_card(
                "Alarm Settings",
                "Control the blacklist alarm switch and the dates used for alarm and repeated notifications.",
                "Alerts",
                "notification.svg",
                "#f97316",
            )
        )

        controls = QHBoxLayout()
        controls.addStretch(1)
        self._alarm_reset_btn = PrimeButton("Reset", variant="secondary", size="sm")
        self._alarm_reset_btn.clicked.connect(lambda: self._load_alarm_setting(notify=True))
        controls.addWidget(self._alarm_reset_btn)
        self._alarm_save_btn = PrimeButton("Save Settings", variant="warning", size="sm")
        self._alarm_save_btn.clicked.connect(self.save_alarm_setting)
        controls.addWidget(self._alarm_save_btn)
        layout.addLayout(controls)

        panel = self._form_panel(
            "Notification Rules",
            "These values are read from and written back to the alarm settings API.",
        )
        panel_grid = QGridLayout()
        panel_grid.setHorizontalSpacing(12)
        panel_grid.setVerticalSpacing(12)
        panel.layout().addLayout(panel_grid)
        self._add_field(panel_grid, 0, "Blacklist Date", self.alarm_blacklist_date, "Date used for blacklist alarm scheduling.")
        self._add_field(panel_grid, 1, "Repeated Date", self.alarm_repeated_date, "Date used for repeated-car alarm scheduling.")
        self._add_field(panel_grid, 2, "Blacklist Alarm", self.alarm_blacklist_alarm, "Enable or disable blacklist alarm output.")
        layout.addWidget(panel)

        layout.addWidget(
            self._note_card(
                "Alarm scope",
                "The current desktop app exposes the alarm settings backend only for these three fields, so this section stays focused on the server-backed values instead of showing disconnected controls.",
            )
        )
        layout.addStretch(1)
        return page

    def _build_repeated_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        layout.addWidget(
            self._hero_card(
                "Repeated Settings",
                "Set the threshold that marks a vehicle as repeated and the time window used to evaluate it.",
                "Repeated Detection",
                "calendar.svg",
                "#8b5cf6",
            )
        )

        controls = QHBoxLayout()
        controls.addStretch(1)
        self._repeated_reset_btn = PrimeButton("Reset", variant="secondary", size="sm")
        self._repeated_reset_btn.clicked.connect(lambda: self._load_repeated_setting(notify=True))
        controls.addWidget(self._repeated_reset_btn)
        self._repeated_save_btn = PrimeButton("Save Settings", variant="help", size="sm")
        self._repeated_save_btn.clicked.connect(self.save_repeated_setting)
        controls.addWidget(self._repeated_save_btn)
        layout.addLayout(controls)

        panel = self._form_panel(
            "Repeated Vehicle Rules",
            "These thresholds drive the repeated-car detection endpoint behavior.",
        )
        panel_grid = QGridLayout()
        panel_grid.setHorizontalSpacing(12)
        panel_grid.setVerticalSpacing(12)
        panel.layout().addLayout(panel_grid)
        self._add_field(panel_grid, 0, "Number of Repeated Cars", self.repeated_cars, "Vehicle count required before a match is considered repeated.")
        self._add_field(panel_grid, 1, "In Time (minutes)", self.repeated_in_time, "Time window used for repeated detection.")
        layout.addWidget(panel)

        layout.addWidget(
            self._note_card(
                "Detection rule",
                "If you lower these thresholds too far, repeated detections become noisy. Keep the values aligned with the traffic density on your deployment.",
            )
        )
        layout.addStretch(1)
        return page

    def _build_server_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        layout.addWidget(
            self._hero_card(
                "Server Settings",
                "Inspect network interfaces, view assigned IPs, and call the server power-management endpoints from the same settings workspace.",
                "Server Control",
                "monitor.svg",
                "#06b6d4",
            )
        )

        controls = QHBoxLayout()
        controls.addStretch(1)
        self._server_refresh_interfaces_btn = PrimeButton("Refresh Interfaces", variant="info", size="sm")
        self._server_refresh_interfaces_btn.clicked.connect(lambda: self._load_network_interfaces(notify=True))
        controls.addWidget(self._server_refresh_interfaces_btn)
        self._server_clear_form_btn = PrimeButton("Clear Form", variant="light", size="sm")
        self._server_clear_form_btn.clicked.connect(self._clear_server_form)
        controls.addWidget(self._server_clear_form_btn)
        layout.addLayout(controls)

        network_panel = self._form_panel(
            "Network Write Actions",
            "Select an interface from the server response, then send the common network fields needed by the write endpoints.",
        )
        network_grid = QGridLayout()
        network_grid.setHorizontalSpacing(12)
        network_grid.setVerticalSpacing(12)
        network_panel.layout().addLayout(network_grid)
        network_grid.addWidget(
            self._field_block("Interface", self.server_interface_select, "Loaded from `/server_settings/network/interfaces`."),
            0,
            0,
        )
        network_grid.addWidget(
            self._field_block("IP Address", self.server_ip_address, "Primary address for static/add/remove IP actions."),
            0,
            1,
        )
        network_grid.addWidget(
            self._field_block("Subnet Mask", self.server_subnet_mask, "Example: `255.255.255.0`."),
            1,
            0,
        )
        network_grid.addWidget(
            self._field_block("Gateway", self.server_gateway, "Optional default gateway."),
            1,
            1,
        )
        network_grid.addWidget(
            self._field_block("Prefix Length", self.server_prefix_length, "Example: `24` if the API uses CIDR length."),
            2,
            0,
        )
        network_grid.addWidget(
            self._field_block("DNS", self.server_dns, "Comma-separated DNS servers or a single value."),
            2,
            1,
        )

        network_actions = QHBoxLayout()
        network_actions.setSpacing(10)
        network_panel.layout().addLayout(network_actions)
        self._server_set_static_btn = PrimeButton("Set Static IP", variant="warning", size="sm")
        self._server_set_static_btn.clicked.connect(self._set_static_ip)
        network_actions.addWidget(self._server_set_static_btn)
        self._server_add_ip_btn = PrimeButton("Add IP", variant="success", size="sm")
        self._server_add_ip_btn.clicked.connect(self._add_network_ip)
        network_actions.addWidget(self._server_add_ip_btn)
        self._server_remove_ip_btn = PrimeButton("Remove IP", variant="danger", size="sm")
        self._server_remove_ip_btn.clicked.connect(self._remove_network_ip)
        network_actions.addWidget(self._server_remove_ip_btn)
        network_actions.addStretch(1)
        layout.addWidget(network_panel)

        system_panel = self._form_panel(
            "System Actions",
            "These buttons call the server reboot and shutdown endpoints directly. Confirmation is required before power actions are sent.",
        )
        system_actions = QHBoxLayout()
        system_actions.setSpacing(10)
        system_panel.layout().addLayout(system_actions)
        self._server_reboot_btn = PrimeButton("Reboot Computer", variant="warning", size="sm")
        self._server_reboot_btn.clicked.connect(self._reboot_system)
        system_actions.addWidget(self._server_reboot_btn)
        self._server_shutdown_btn = PrimeButton("Shutdown Computer", variant="danger", size="sm")
        self._server_shutdown_btn.clicked.connect(self._shutdown_system)
        system_actions.addWidget(self._server_shutdown_btn)
        self._server_cancel_shutdown_btn = PrimeButton("Cancel Shutdown", variant="secondary", size="sm")
        self._server_cancel_shutdown_btn.clicked.connect(self._cancel_shutdown)
        system_actions.addWidget(self._server_cancel_shutdown_btn)
        system_actions.addStretch(1)
        layout.addWidget(system_panel)
        
        return page

    def _wrap_page(self, page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _make_line_edit(self, placeholder: str) -> QLineEdit:
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        return field

    def _make_spinbox(self, minimum: int, maximum: int) -> QSpinBox:
        field = QSpinBox()
        field.setRange(minimum, maximum)
        field.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        return field

    def _make_combo(self, options: tuple[tuple[str, object], ...]) -> QComboBox:
        field = QComboBox()
        for label, value in options:
            field.addItem(label, value)
        return field

    def _make_bool_combo(self) -> QComboBox:
        return self._make_combo((("Yes", True), ("No", False)))

    def _set_combo_value(self, field: QComboBox, value: object) -> None:
        index = field.findData(value)
        field.setCurrentIndex(index if index >= 0 else 0)

    def _hero_card(
        self,
        title_text: str,
        subtitle_text: str,
        kicker_text: str,
        icon_name: str,
        accent: str,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("settingsHero")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)

        badge = QFrame()
        badge.setFixedSize(64, 64)
        badge.setStyleSheet(
            f"background: {accent}20; border: 1px solid {accent}55; border-radius: 18px;"
        )
        badge_layout = QVBoxLayout(badge)
        badge_layout.setContentsMargins(14, 14, 14, 14)
        badge_layout.setSpacing(0)
        badge_icon = SvgWidget(_icon_path(icon_name))
        badge_layout.addWidget(badge_icon, 1, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(4)
        layout.addLayout(text_col, 1)

        kicker = QLabel(kicker_text)
        kicker.setObjectName("settingsHeroKicker")
        text_col.addWidget(kicker)

        title = QLabel(title_text)
        title.setObjectName("settingsHeroTitle")
        text_col.addWidget(title)

        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("settingsHeroSubtitle")
        subtitle.setWordWrap(True)
        text_col.addWidget(subtitle)

        return card

    def _metric_card(self, title_text: str, hint_text: str, accent: str, key: str) -> QFrame:
        card = QFrame()
        card.setObjectName("settingsMetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        stripe = QFrame()
        stripe.setFixedHeight(4)
        stripe.setStyleSheet(f"background: {accent}; border-radius: 2px;")
        layout.addWidget(stripe)

        title = QLabel(title_text)
        title.setObjectName("settingsMetricTitle")
        layout.addWidget(title)

        value = QLabel("--")
        value.setObjectName("settingsMetricValue")
        value.setWordWrap(True)
        layout.addWidget(value)
        self._card_values[key] = value

        hint = QLabel(hint_text)
        hint.setObjectName("settingsMetricHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        return card

    def _form_panel(self, title_text: str, subtitle_text: str) -> QFrame:
        panel = QFrame()
        panel.setObjectName("settingsPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel(title_text)
        title.setObjectName("settingsPanelTitle")
        layout.addWidget(title)

        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("settingsPanelSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        return panel

    def _field_block(self, label_text: str, field: QWidget, hint_text: str) -> QWidget:
        block = QWidget()
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label = QLabel(label_text)
        label.setObjectName("settingsFieldLabel")
        layout.addWidget(label)
        layout.addWidget(field)

        hint = QLabel(hint_text)
        hint.setObjectName("settingsFieldHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return block

    def _add_field(self, grid: QGridLayout, row: int, label_text: str, field: QWidget, hint_text: str) -> None:
        grid.addWidget(self._field_block(label_text, field, hint_text), row, 0)

    def _note_card(self, title_text: str, body_text: str) -> QFrame:
        card = QFrame()
        card.setObjectName("settingsActionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        title = QLabel(title_text)
        title.setObjectName("settingsNoteTitle")
        layout.addWidget(title)

        body = QLabel(body_text)
        body.setObjectName("settingsNoteBody")
        body.setWordWrap(True)
        layout.addWidget(body)
        return card

    def _interface_options_from_value(self, value: Any) -> list[tuple[str, str]]:
        options: list[tuple[str, str]] = []
        seen: set[str] = set()

        def add_option(label: Any, raw_value: Any) -> None:
            text_value = str(raw_value or "").strip()
            if not text_value or text_value in seen:
                return
            seen.add(text_value)
            text_label = str(label or text_value).strip() or text_value
            options.append((text_label, text_value))

        def visit(item: Any) -> None:
            if isinstance(item, dict):
                candidate_label = (
                    item.get("label")
                    or item.get("name")
                    or item.get("interface")
                    or item.get("interface_name")
                    or item.get("device")
                    or item.get("id")
                )
                candidate_value = (
                    item.get("interface")
                    or item.get("interface_name")
                    or item.get("name")
                    or item.get("device")
                    or item.get("id")
                )
                if candidate_value not in (None, ""):
                    add_option(candidate_label, candidate_value)
                for key in ("interfaces", "items", "data", "result", "payload"):
                    nested = item.get(key)
                    if isinstance(nested, (list, tuple, dict)):
                        visit(nested)
            elif isinstance(item, (list, tuple)):
                for entry in item:
                    visit(entry)
            elif isinstance(item, str):
                add_option(item, item)

        visit(value)
        return options

    def _on_server_interface_changed(self, _index: int) -> None:
        self._sync_server_form_from_selected_interface()
        self._fill_record_media_server_ip_from_current_server()

    def _dns_text_from_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            for key in ("dns", "servers", "nameservers", "items", "values", "data", "result", "payload"):
                nested = value.get(key)
                text = self._dns_text_from_value(nested)
                if text:
                    return text
            return ""
        if isinstance(value, (list, tuple, set)):
            parts: list[str] = []
            for item in value:
                text = self._dns_text_from_value(item)
                if text:
                    if "," in text:
                        parts.extend([chunk.strip() for chunk in text.split(",") if chunk.strip()])
                    else:
                        parts.append(text)
            deduped: list[str] = []
            seen: set[str] = set()
            for entry in parts:
                if entry in seen:
                    continue
                seen.add(entry)
                deduped.append(entry)
            return ", ".join(deduped)
        return str(value).strip()

    def _network_snapshot_from_item(
        self,
        item: dict[str, Any],
        inherited_interface: str = "",
    ) -> dict[str, str]:
        interface_name = str(
            item.get("interface")
            or item.get("interface_name")
            or item.get("device")
            or item.get("name")
            or inherited_interface
            or ""
        ).strip()

        ipv4_value = item.get("ipv4")
        ipv4 = ipv4_value if isinstance(ipv4_value, dict) else {}

        ip_address = str(
            item.get("ip_address")
            or item.get("ip")
            or item.get("address")
            or item.get("local_ip")
            or item.get("server_ip")
            or ipv4.get("ip_address")
            or ipv4.get("ip")
            or ipv4.get("address")
            or ""
        ).strip()
        subnet_mask = str(
            item.get("subnet_mask")
            or item.get("netmask")
            or item.get("mask")
            or ipv4.get("subnet_mask")
            or ipv4.get("netmask")
            or ipv4.get("mask")
            or ""
        ).strip()
        gateway = str(
            item.get("gateway")
            or item.get("default_gateway")
            or ipv4.get("gateway")
            or ""
        ).strip()
        prefix_length = str(
            item.get("prefix_length")
            or item.get("prefix")
            or item.get("cidr")
            or ipv4.get("prefix_length")
            or ipv4.get("prefix")
            or ""
        ).strip()
        dns = self._dns_text_from_value(
            item.get("dns")
            or item.get("dns_servers")
            or item.get("nameservers")
            or item.get("name_servers")
            or ipv4.get("dns")
            or item.get("resolv")
        )
        state = str(
            item.get("state")
            or item.get("status")
            or item.get("operstate")
            or item.get("link_state")
            or item.get("carrier")
            or ipv4.get("state")
            or ""
        ).strip()
        return {
            "interface": interface_name,
            "ip_address": ip_address,
            "subnet_mask": subnet_mask,
            "gateway": gateway,
            "prefix_length": prefix_length,
            "dns": dns,
            "state": state,
        }

    def _network_snapshots_from_value(
        self,
        value: Any,
        inherited_interface: str = "",
    ) -> list[dict[str, str]]:
        snapshots: list[dict[str, str]] = []
        seen_keys: set[str] = set()

        def add_snapshot(snapshot: dict[str, str]) -> None:
            has_data = any(
                snapshot.get(key, "")
                for key in ("interface", "ip_address", "subnet_mask", "gateway", "prefix_length", "dns", "state")
            )
            if not has_data:
                return
            key = "|".join(
                snapshot.get(part, "")
                for part in ("interface", "ip_address", "subnet_mask", "gateway", "prefix_length", "dns", "state")
            )
            if key in seen_keys:
                return
            seen_keys.add(key)
            snapshots.append(snapshot)

        def visit(node: Any, parent_interface: str = "") -> None:
            if isinstance(node, dict):
                snapshot = self._network_snapshot_from_item(node, parent_interface)
                add_snapshot(snapshot)
                next_interface = snapshot.get("interface", "") or parent_interface
                for key, nested in node.items():
                    inferred = next_interface
                    if not inferred and isinstance(key, str):
                        candidate = key.strip()
                        if candidate and " " not in candidate and "/" not in candidate:
                            inferred = candidate
                    if isinstance(nested, (dict, list, tuple)):
                        visit(nested, inferred)
                return
            if isinstance(node, (list, tuple)):
                for entry in node:
                    visit(entry, parent_interface)

        visit(value, inherited_interface)
        return snapshots

    def _snapshot_score(self, snapshot: dict[str, str]) -> int:
        return sum(
            1
            for key in ("ip_address", "subnet_mask", "gateway", "prefix_length", "dns", "state")
            if snapshot.get(key, "").strip()
        )

    def _snapshot_is_active(self, snapshot: dict[str, str]) -> bool:
        state = str(snapshot.get("state", "")).strip().lower()
        if not state:
            return False
        active_markers = ("up", "active", "connected", "running", "online", "yes", "true")
        return any(marker in state for marker in active_markers)

    def _preferred_interface_name(self) -> str:
        snapshots = self._merged_network_snapshots()
        for snapshot in snapshots:
            interface_name = str(snapshot.get("interface", "")).strip()
            if interface_name and self._snapshot_is_active(snapshot):
                return interface_name
        for snapshot in snapshots:
            interface_name = str(snapshot.get("interface", "")).strip()
            if interface_name and str(snapshot.get("ip_address", "")).strip():
                return interface_name
        return ""

    def _interfaces_with_detected_ip(self) -> set[str]:
        result: set[str] = set()
        for snapshot in self._network_snapshots_from_value(self.store.network_ips):
            interface_name = str(snapshot.get("interface", "")).strip()
            if not interface_name:
                continue
            ip_address = str(snapshot.get("ip_address", "")).strip()
            if ip_address:
                result.add(interface_name)
        return result

    def _validate_interface_for_network_write(self, interface_name: str) -> None:
        allowed = self._interfaces_with_detected_ip()
        if not allowed:
            return
        if interface_name in allowed:
            return
        preferred = self._preferred_interface_name()
        if preferred and preferred in allowed:
            raise ValueError(
                f"Interface '{interface_name}' is not active. Select '{preferred}' or another active interface."
            )
        raise ValueError(f"Interface '{interface_name}' is not active. Select an active interface.")

    def _merged_network_snapshots(self) -> list[dict[str, str]]:
        merged: list[dict[str, str]] = []
        by_interface: dict[str, dict[str, str]] = {}
        for source in (self.store.network_ips, self.store.network_interfaces):
            for snapshot in self._network_snapshots_from_value(source):
                interface_name = snapshot.get("interface", "").strip()
                if not interface_name:
                    merged.append(snapshot)
                    continue
                existing = by_interface.get(interface_name)
                if existing is None or self._snapshot_score(snapshot) > self._snapshot_score(existing):
                    by_interface[interface_name] = snapshot
        merged.extend(by_interface.values())
        return merged

    def _snapshot_for_selected_interface(self) -> dict[str, str] | None:
        interface_name = str(self.server_interface_select.currentData() or "").strip()
        if not interface_name:
            return None
        needle = interface_name.lower()
        for snapshot in self._merged_network_snapshots():
            if str(snapshot.get("interface", "")).strip().lower() == needle:
                return snapshot
        return None

    def _current_server_ip_from_network(self) -> str:
        selected = self._snapshot_for_selected_interface()
        if selected is not None:
            value = str(selected.get("ip_address", "")).strip()
            if value:
                return value
        for snapshot in self._merged_network_snapshots():
            value = str(snapshot.get("ip_address", "")).strip()
            if value:
                return value
        return ""

    def _fill_record_media_server_ip_from_current_server(self) -> None:
        if self.record_media_server_ip.text().strip():
            return
        current_ip = self._current_server_ip_from_network()
        if current_ip:
            self.record_media_server_ip.setText(current_ip)

    def _sync_server_form_from_selected_interface(self) -> None:
        snapshot = self._snapshot_for_selected_interface()
        if snapshot is None:
            return
        self.server_ip_address.setText(snapshot.get("ip_address", ""))
        self.server_subnet_mask.setText(snapshot.get("subnet_mask", ""))
        self.server_gateway.setText(snapshot.get("gateway", ""))
        self.server_prefix_length.setText(snapshot.get("prefix_length", ""))
        self.server_dns.setText(snapshot.get("dns", ""))

    def _refresh_server_interface_options(self) -> None:
        current_value = str(self.server_interface_select.currentData() or "").strip()
        options = self._interface_options_from_value(self.store.network_interfaces)
        for label, value in self._interface_options_from_value(self.store.network_ips):
            if any(existing_value == value for _existing_label, existing_value in options):
                continue
            options.append((label, value))
        snapshots_by_interface = {
            str(snapshot.get("interface", "")).strip(): snapshot
            for snapshot in self._merged_network_snapshots()
            if str(snapshot.get("interface", "")).strip()
        }
        self.server_interface_select.blockSignals(True)
        self.server_interface_select.clear()
        self.server_interface_select.addItem("Select interface", "")
        for label, value in options:
            display_label = str(label)
            snapshot = snapshots_by_interface.get(str(value).strip())
            if snapshot is not None:
                ip_text = str(snapshot.get("ip_address", "")).strip()
                state_text = str(snapshot.get("state", "")).strip()
                extras = [part for part in (ip_text, state_text) if part]
                if extras:
                    display_label = f"{display_label} ({' | '.join(extras)})"
            self.server_interface_select.addItem(display_label, value)
        selected_index = self.server_interface_select.findData(current_value)
        preferred_interface = self._preferred_interface_name()
        if preferred_interface:
            current_has_snapshot = bool(current_value and current_value in snapshots_by_interface)
            if selected_index < 0 or not current_has_snapshot:
                preferred_index = self.server_interface_select.findData(preferred_interface)
                if preferred_index >= 0:
                    selected_index = preferred_index
        self.server_interface_select.setCurrentIndex(selected_index if selected_index >= 0 else 0)
        self.server_interface_select.blockSignals(False)
        self._sync_server_form_from_selected_interface()

    def _clear_server_form(self) -> None:
        self.server_interface_select.setCurrentIndex(0)
        self.server_ip_address.clear()
        self.server_subnet_mask.clear()
        self.server_gateway.clear()
        self.server_prefix_length.clear()
        self.server_dns.clear()

    def _server_network_payload(self, require_interface_name: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        interface_name = str(self.server_interface_select.currentData() or "").strip()
        if interface_name:
            if require_interface_name:
                self._validate_interface_for_network_write(interface_name)
            payload["interface_name"] = interface_name
            payload["interface"] = interface_name
        elif require_interface_name:
            raise ValueError("Interface name required.")

        ip_address = self.server_ip_address.text().strip()
        if ip_address:
            payload["ip_address"] = ip_address

        subnet_mask = self.server_subnet_mask.text().strip()
        if subnet_mask:
            payload["subnet_mask"] = subnet_mask

        gateway = self.server_gateway.text().strip()
        if gateway:
            payload["gateway"] = gateway

        prefix_length = self.server_prefix_length.text().strip()
        if prefix_length:
            payload["prefix_length"] = int(prefix_length) if prefix_length.isdigit() else prefix_length

        dns_text = self.server_dns.text().strip()
        if dns_text:
            dns_values = [item.strip() for item in dns_text.split(",") if item.strip()]
            payload["dns"] = dns_values if len(dns_values) != 1 else dns_values[0]

        if not payload:
            raise ValueError("Select an interface or fill the network fields.")
        return payload

    def _server_set_static_ip_payload(self) -> dict[str, Any]:
        interface_name = str(self.server_interface_select.currentData() or "").strip()
        if not interface_name:
            raise ValueError("Interface name required.")
        self._validate_interface_for_network_write(interface_name)

        ip_address = self.server_ip_address.text().strip()
        subnet_mask = self.server_subnet_mask.text().strip()
        gateway = self.server_gateway.text().strip()
        dns_text = self.server_dns.text().strip()
        dns_servers = [item.strip() for item in dns_text.split(",") if item.strip()] if dns_text else []

        if not ip_address:
            raise ValueError("IP address required.")
        if not subnet_mask:
            raise ValueError("Subnet mask required.")

        return {
            "interface_name": interface_name,
            "interface": interface_name,
            "ip_address": ip_address,
            "subnet_mask": subnet_mask,
            "gateway": gateway,
            "dns_servers": dns_servers,
        }

    def _confirm_server_action(self, title: str, prompt: str) -> bool:
        return PrimeConfirmDialog.ask(
            parent=self,
            title=title,
            message=prompt,
            ok_text="Confirm",
            cancel_text="Cancel",
        )

    def _set_active_tab(self, tab_id: str) -> None:
        index_map = {
            "overview": 0,
            "record": 1,
            "alarm": 2,
            "repeated": 3,
            "server": 4,
        }
        if tab_id not in index_map:
            return
        self._stack.setCurrentIndex(index_map[tab_id])
        button = self._nav_buttons.get(tab_id)
        if button is not None:
            button.setChecked(True)

    def _toast_success(self, summary: str, detail: str = "", life: int = 3200) -> None:
        self.toast.success(summary, detail, life)

    def _toast_error(self, summary: str, detail: str = "", life: int = 4200) -> None:
        self.toast.error(summary, detail, life)

    def _set_buttons_enabled(self, enabled: bool, *buttons: PrimeButton) -> None:
        for button in buttons:
            button.setEnabled(enabled)

    def _record_payload(self) -> RecordSetting:
        return RecordSetting(
            valid_space=self.record_valid_space.value(),
            save_path=self.record_save_path.text().strip(),
            quality=str(self.record_quality.currentData() or "normal"),
            is_remove=bool(self.record_is_remove.currentData()),
            is_record=bool(self.record_is_record.currentData()),
            fps_delay=self.record_fps_delay.value(),
            media_server_ip=self.record_media_server_ip.text().strip(),
            media_server_port=self.record_media_server_port.value(),
            server_public_ip=self.record_server_public_ip.text().strip(),
            server_public_port=self.record_server_public_port.value(),
            db_limit_days=self.record_db_limit_days.value(),
            backup_days=self.record_backup_days.value(),
            backup_path=self.record_backup_path.text().strip(),
            backup_last_date=self.record_backup_last_date.value(),
        )

    def _alarm_payload(self) -> AlarmSetting:
        return AlarmSetting(
            blacklist_date=self.alarm_blacklist_date.value(),
            repeated_date=self.alarm_repeated_date.value(),
            blacklist_alarm=bool(self.alarm_blacklist_alarm.currentData()),
        )

    def _repeated_payload(self) -> RepeatedSetting:
        return RepeatedSetting(
            repeated_cars=self.repeated_cars.value(),
            in_time=self.repeated_in_time.value(),
        )

    def _apply_record_setting(self, setting: RecordSetting) -> None:
        self.record_valid_space.setValue(setting.valid_space)
        self.record_save_path.setText(setting.save_path)
        self._set_combo_value(self.record_quality, setting.quality or "normal")
        self._set_combo_value(self.record_is_record, bool(setting.is_record))
        self._set_combo_value(self.record_is_remove, bool(setting.is_remove))
        self.record_fps_delay.setValue(setting.fps_delay)
        self.record_backup_last_date.set_value(setting.backup_last_date)
        self.record_media_server_ip.setText(setting.media_server_ip)
        self.record_media_server_port.setValue(setting.media_server_port)
        self.record_server_public_ip.setText(setting.server_public_ip)
        self.record_server_public_port.setValue(setting.server_public_port)
        self.record_db_limit_days.setValue(setting.db_limit_days)
        self.record_backup_days.setValue(setting.backup_days)
        self.record_backup_path.setText(setting.backup_path)
        self._refresh_overview_cards()

    def _apply_alarm_setting(self, setting: AlarmSetting) -> None:
        self.alarm_blacklist_date.set_value(setting.blacklist_date)
        self.alarm_repeated_date.set_value(setting.repeated_date)
        self._set_combo_value(self.alarm_blacklist_alarm, bool(setting.blacklist_alarm))
        self._refresh_overview_cards()

    def _apply_repeated_setting(self, setting: RepeatedSetting) -> None:
        self.repeated_cars.setValue(setting.repeated_cars)
        self.repeated_in_time.setValue(setting.in_time)
        self._refresh_overview_cards()

    def _refresh_overview_cards(self) -> None:
        record = self.store.record_setting
        alarm = self.store.alarm_setting
        repeated = self.store.repeated_setting

        quality = (record.quality or "normal").strip().title()
        self._card_values["record_quality"].setText(quality or "Normal")

        repeated_text = f"{repeated.repeated_cars} cars in {repeated.in_time} min"
        self._card_values["repeated_rule"].setText(repeated_text)

        self._card_values["alarm_status"].setText("Enabled" if alarm.blacklist_alarm else "Disabled")
        self._card_values["backup_path"].setText(record.backup_path or "Not configured")

        if self._last_sync_label is not None:
            self._last_sync_label.setText(
                f"Last sync: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

    def _load_record_setting(self, notify: bool = False) -> bool:
        setting = self.store.load_record_setting()
        if setting is None:
            if notify:
                self._toast_error("Record Settings", self.store.last_error or "Failed to load record settings.")
            return False
        self._apply_record_setting(setting)
        return True

    def _load_alarm_setting(self, notify: bool = False) -> bool:
        setting = self.store.load_alarm_setting()
        if setting is None:
            if notify:
                self._toast_error("Alarm Settings", self.store.last_error or "Failed to load alarm settings.")
            return False
        self._apply_alarm_setting(setting)
        return True

    def _load_repeated_setting(self, notify: bool = False) -> bool:
        setting = self.store.load_repeated_setting()
        if setting is None:
            if notify:
                self._toast_error("Repeated Settings", self.store.last_error or "Failed to load repeated settings.")
            return False
        self._apply_repeated_setting(setting)
        return True

    def _load_network_interfaces(self, notify: bool = False) -> bool:
        interfaces = self.store.load_network_interfaces()
        if interfaces is None:
            if notify:
                self._toast_error("Server Settings", self.store.last_error or "Failed to load network interfaces.")
            return False
        # Best-effort fetch for current IP assignments used to auto-fill network fields.
        self.store.load_network_ips()
        self._refresh_server_interface_options()
        self._fill_record_media_server_ip_from_current_server()
        return True

    def reload_all_settings(self, notify: bool = False) -> None:
        self._set_buttons_enabled(False, self._reload_all_btn)
        results: list[bool] = []
        errors: list[str] = []
        for loader in (
            self._load_record_setting,
            self._load_alarm_setting,
            self._load_repeated_setting,
            self._load_network_interfaces,
        ):
            ok = loader(notify=False)
            results.append(ok)
            if not ok and self.store.last_error:
                errors.append(self.store.last_error)
        self._set_buttons_enabled(True, self._reload_all_btn)

        if notify:
            if all(results):
                self._toast_success("Settings", "All settings reloaded successfully.")
            else:
                detail = errors[0] if errors else "One or more setting groups failed to load."
                self._toast_error("Settings", detail)

    def _set_static_ip(self) -> None:
        try:
            payload = self._server_set_static_ip_payload()
        except ValueError as exc:
            self._toast_error("Server Settings", str(exc))
            return

        self._set_buttons_enabled(False, self._server_set_static_btn, self._server_add_ip_btn, self._server_remove_ip_btn)
        ok = self.store.set_static_ip(payload)
        self._set_buttons_enabled(True, self._server_set_static_btn, self._server_add_ip_btn, self._server_remove_ip_btn)
        if not ok:
            self._toast_error("Server Settings", self.store.last_error or "Failed to set static IP.")
            return
        self._refresh_server_interface_options()
        self._toast_success("Server Settings", self.store.last_message or "Static IP updated successfully.")

    def _add_network_ip(self) -> None:
        try:
            payload = self._server_network_payload(require_interface_name=True)
        except ValueError as exc:
            self._toast_error("Server Settings", str(exc))
            return

        self._set_buttons_enabled(False, self._server_set_static_btn, self._server_add_ip_btn, self._server_remove_ip_btn)
        ok = self.store.add_network_ip(payload)
        self._set_buttons_enabled(True, self._server_set_static_btn, self._server_add_ip_btn, self._server_remove_ip_btn)
        if not ok:
            self._toast_error("Server Settings", self.store.last_error or "Failed to add IP address.")
            return
        self._refresh_server_interface_options()
        self._toast_success("Server Settings", self.store.last_message or "IP address added successfully.")

    def _remove_network_ip(self) -> None:
        try:
            payload = self._server_network_payload(require_interface_name=True)
        except ValueError as exc:
            self._toast_error("Server Settings", str(exc))
            return

        self._set_buttons_enabled(False, self._server_set_static_btn, self._server_add_ip_btn, self._server_remove_ip_btn)
        ok = self.store.remove_network_ip(payload)
        self._set_buttons_enabled(True, self._server_set_static_btn, self._server_add_ip_btn, self._server_remove_ip_btn)
        if not ok:
            self._toast_error("Server Settings", self.store.last_error or "Failed to remove IP address.")
            return
        self._refresh_server_interface_options()
        self._toast_success("Server Settings", self.store.last_message or "IP address removed successfully.")

    def _reboot_system(self) -> None:
        if not self._confirm_server_action("Reboot Computer", "Send a reboot request to this server?"):
            return
        self._set_buttons_enabled(False, self._server_reboot_btn)
        ok = self.store.reboot_system()
        self._set_buttons_enabled(True, self._server_reboot_btn)
        if not ok:
            self._toast_error("Server Settings", self.store.last_error or "Failed to request reboot.")
            return
        self._toast_success("Server Settings", self.store.last_message or "Reboot requested successfully.")

    def _shutdown_system(self) -> None:
        if not self._confirm_server_action("Shutdown Computer", "Send a shutdown request to this server?"):
            return
        self._set_buttons_enabled(False, self._server_shutdown_btn)
        ok = self.store.shutdown_system()
        self._set_buttons_enabled(True, self._server_shutdown_btn)
        if not ok:
            self._toast_error("Server Settings", self.store.last_error or "Failed to request shutdown.")
            return
        self._toast_success("Server Settings", self.store.last_message or "Shutdown requested successfully.")

    def _cancel_shutdown(self) -> None:
        if not self._confirm_server_action("Cancel Shutdown", "Send a shutdown cancellation request to this server?"):
            return
        self._set_buttons_enabled(False, self._server_cancel_shutdown_btn)
        ok = self.store.cancel_shutdown()
        self._set_buttons_enabled(True, self._server_cancel_shutdown_btn)
        if not ok:
            self._toast_error("Server Settings", self.store.last_error or "Failed to cancel shutdown.")
            return
        self._toast_success("Server Settings", self.store.last_message or "Shutdown cancellation requested successfully.")

    def save_record_setting(self) -> None:
        self._set_buttons_enabled(False, self._record_save_btn, self._record_reset_btn)
        updated = self.store.update_record_setting(self._record_payload())
        self._set_buttons_enabled(True, self._record_save_btn, self._record_reset_btn)
        if updated is None:
            self._toast_error("Record Settings", self.store.last_error or "Failed to save record settings.")
            return
        self._apply_record_setting(updated)
        self._toast_success("Record Settings", self.store.last_message or "Record settings updated successfully.")

    def save_alarm_setting(self) -> None:
        self._set_buttons_enabled(False, self._alarm_save_btn, self._alarm_reset_btn)
        updated = self.store.update_alarm_setting(self._alarm_payload())
        self._set_buttons_enabled(True, self._alarm_save_btn, self._alarm_reset_btn)
        if updated is None:
            self._toast_error("Alarm Settings", self.store.last_error or "Failed to save alarm settings.")
            return
        self._apply_alarm_setting(updated)
        self._toast_success("Alarm Settings", self.store.last_message or "Alarm settings updated successfully.")

    def save_repeated_setting(self) -> None:
        self._set_buttons_enabled(False, self._repeated_save_btn, self._repeated_reset_btn)
        updated = self.store.update_repeated_setting(self._repeated_payload())
        self._set_buttons_enabled(True, self._repeated_save_btn, self._repeated_reset_btn)
        if updated is None:
            self._toast_error("Repeated Settings", self.store.last_error or "Failed to save repeated settings.")
            return
        self._apply_repeated_setting(updated)
        self._toast_success("Repeated Settings", self.store.last_message or "Repeated settings updated successfully.")
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        p.fillPath(path, QColor(Constants.DARK_BG))   # dark bg — cards float above it
        super().paintEvent(event)
