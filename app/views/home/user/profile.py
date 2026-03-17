from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QTimer, Qt, Signal,QRectF
from PySide6.QtGui import QIcon,QColor,QPainter,QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.models.logs import UserLogResponse
from app.constants._init_ import Constants
from app.models.profile import ProfileResponse
from app.services.home.user.profile_service import ProfileService
from app.services.home.user.user_log_service import UserLogService
from app.store.home.user.profile_store import ProfileStore
from app.store.home.user.user_log_store import UserLogStore
from app.ui.table import PrimeDataTable, PrimeTableColumn
from app.views.home.user._shared import USER_MANAGEMENT_SIDEBAR_STYLES, UserManagementSidebar


_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


def _format_datetime(value: Optional[datetime]) -> str:
    if value is None:
        return "-"
    try:
        return value.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return value.strftime("%Y-%m-%d %H:%M")


class ProfilePage(QWidget):
    navigate = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.profile_store = ProfileStore(ProfileService())
        self.user_log_store = UserLogStore(UserLogService())
        self._editing = False
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(self._hide_notice)

        self._build_ui()
        self._connect_store()
        self.profile_store.load()

    def _build_ui(self) -> None:
        self.setObjectName("profileRoot")

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        self.sidebar = UserManagementSidebar("/user/profile", self)
        self.sidebar.navigate.connect(self.navigate.emit)
        root.addWidget(self.sidebar)

        main = QFrame()
        main.setObjectName("userMainPanel")
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        root.addWidget(main, 1)

        scroll = QScrollArea(main)
        scroll.setObjectName("profileScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        main_layout.addWidget(scroll)

        content = QWidget()
        content.setObjectName("profileContent")
        scroll.setWidget(content)

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(18)

        self.notice_label = QLabel("")
        self.notice_label.setObjectName("profileNotice")
        self.notice_label.setWordWrap(True)
        self.notice_label.hide()
        content_layout.addWidget(self.notice_label)

        content_layout.addWidget(self._build_header_card())

        top_grid = QGridLayout()
        top_grid.setHorizontalSpacing(18)
        top_grid.setVerticalSpacing(18)
        top_grid.setColumnStretch(0, 3)
        top_grid.setColumnStretch(1, 2)
        top_grid.addWidget(self._build_account_card(), 0, 0)
        top_grid.addWidget(self._build_password_card(), 0, 1)
        content_layout.addLayout(top_grid)

        content_layout.addWidget(self._build_activity_card())
        content_layout.addStretch(1)

        self._apply_theme()
        self._sync_edit_state()

    def _build_header_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("profileHeroCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        avatar_wrap = QFrame()
        avatar_wrap.setObjectName("avatarWrap")
        avatar_wrap.setFixedSize(108, 108)
        avatar_layout = QVBoxLayout(avatar_wrap)
        avatar_layout.setContentsMargins(18, 18, 18, 18)

        avatar_icon = QLabel("")
        avatar_icon.setAlignment(Qt.AlignCenter)
        avatar_icon.setObjectName("avatarIcon")
        profile_icon = QIcon(_icon_path("profile.svg"))
        pixmap = profile_icon.pixmap(64, 64)
        if not pixmap.isNull():
            avatar_icon.setPixmap(pixmap)
        else:
            avatar_icon.setText("U")
        avatar_layout.addWidget(avatar_icon)
        layout.addWidget(avatar_wrap, 0, Qt.AlignTop)

        status_dot = QLabel(avatar_wrap)
        status_dot.setObjectName("avatarStatusDot")
        status_dot.setFixedSize(18, 18)
        status_dot.move(78, 78)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(8)

        self.hero_title = QLabel("User Profile")
        self.hero_title.setObjectName("heroTitle")
        text_col.addWidget(self.hero_title)

        self.hero_subtitle = QLabel("@username")
        self.hero_subtitle.setObjectName("heroSubtitle")
        text_col.addWidget(self.hero_subtitle)

        chip_row = QHBoxLayout()
        chip_row.setContentsMargins(0, 8, 0, 0)
        chip_row.setSpacing(8)

        self.account_status_badge = QLabel("Inactive")
        self.account_status_badge.setObjectName("profileBadge")
        chip_row.addWidget(self.account_status_badge)

        self.privilege_badge = QLabel("Standard User")
        self.privilege_badge.setObjectName("profileBadge")
        chip_row.addWidget(self.privilege_badge)

        self.department_badge = QLabel("Department #0")
        self.department_badge.setObjectName("profileBadge")
        chip_row.addWidget(self.department_badge)
        chip_row.addStretch(1)

        text_col.addLayout(chip_row)
        layout.addLayout(text_col, 1)
        return card

    def _build_account_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("profileCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("cardHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(4)

        title = QLabel("Account Settings")
        title.setObjectName("cardTitle")
        title_col.addWidget(title)

        subtitle = QLabel("Update fullname, email, phone, and address.")
        subtitle.setObjectName("cardSubtitle")
        title_col.addWidget(subtitle)

        header_layout.addLayout(title_col, 1)

        self.edit_button = QPushButton("Edit")
        self.edit_button.setObjectName("secondaryButton")
        self.edit_button.clicked.connect(self._toggle_editing)
        header_layout.addWidget(self.edit_button, 0, Qt.AlignRight)

        layout.addWidget(header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(18, 18, 18, 18)
        body_layout.setSpacing(16)

        helper = QLabel("Username is read-only. Other fields become editable after you click Edit.")
        helper.setObjectName("helperText")
        helper.setWordWrap(True)
        body_layout.addWidget(helper)

        form_grid = QGridLayout()
        form_grid.setHorizontalSpacing(16)
        form_grid.setVerticalSpacing(16)
        form_grid.addWidget(self._create_field("Username", "username"), 0, 0)
        form_grid.addWidget(self._create_field("Full Name", "fullname"), 0, 1)
        form_grid.addWidget(self._create_field("Email Address", "email"), 1, 0)
        form_grid.addWidget(self._create_field("Phone Number", "phone"), 1, 1)
        form_grid.addWidget(self._create_field("Address", "area"), 2, 0, 1, 2)
        body_layout.addLayout(form_grid)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 8, 0, 0)
        footer.addStretch(1)

        self.save_button = QPushButton("Save Changes")
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self._save_profile)
        footer.addWidget(self.save_button)
        body_layout.addLayout(footer)

        layout.addWidget(body)
        return card

    def _build_password_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("profileCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("cardHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(4)

        title = QLabel("Change Password")
        title.setObjectName("cardTitle")
        header_layout.addWidget(title)

        subtitle = QLabel("Update your account password using the current password.")
        subtitle.setObjectName("cardSubtitle")
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(18, 18, 18, 18)
        body_layout.setSpacing(14)

        body_layout.addWidget(self._create_password_field("Current Password", "old_password"))
        body_layout.addWidget(self._create_password_field("New Password", "new_password"))
        body_layout.addWidget(self._create_password_field("Confirm New Password", "confirm_password"))

        note = QFrame()
        note.setObjectName("infoNote")
        note_layout = QVBoxLayout(note)
        note_layout.setContentsMargins(14, 14, 14, 14)
        note_layout.setSpacing(6)

        note_title = QLabel("Use a strong password.")
        note_title.setObjectName("noteTitle")
        note_title.setWordWrap(True)
        note_layout.addWidget(note_title)

        note_body = QLabel(
            "Make sure your password is at least 8 characters long and includes a mix of letters, numbers, and symbols."
        )
        note_body.setObjectName("noteBody")
        note_body.setWordWrap(True)
        note_layout.addWidget(note_body)
        body_layout.addWidget(note)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 6, 0, 0)
        footer.addStretch(1)

        self.password_button = QPushButton("Update Password")
        self.password_button.setObjectName("primaryButton")
        self.password_button.clicked.connect(self._change_password)
        footer.addWidget(self.password_button)
        body_layout.addLayout(footer)

        layout.addWidget(body)
        return card

    def _build_activity_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("profileCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("cardHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(4)

        title = QLabel("Recent Activity")
        title.setObjectName("cardTitle")
        header_layout.addWidget(title)

        self.activity_subtitle = QLabel("Loading activity logs...")
        self.activity_subtitle.setObjectName("cardSubtitle")
        header_layout.addWidget(self.activity_subtitle)
        layout.addWidget(header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(18, 18, 18, 18)
        body_layout.setSpacing(10)

        self.activity_table = PrimeDataTable(page_size=5, row_height=50, show_footer=True)
        self.activity_table.set_columns(
            [
                PrimeTableColumn("user", "User", width=220),
                PrimeTableColumn(
                    "action",
                    "Action",
                    width=150,
                    alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                ),
                PrimeTableColumn("created_at", "Date & Time", width=180),
                PrimeTableColumn("detail", "Details", stretch=True),
            ]
        )
        self.activity_table.table.horizontalHeader().setStretchLastSection(True)
        self.activity_table.set_cell_widget_factory("action", self._activity_action_widget)
        body_layout.addWidget(self.activity_table)

        layout.addWidget(body)
        return card

    def _create_field(self, label_text: str, key: str) -> QWidget:
        wrapper = QWidget()
        wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel(label_text)
        label.setObjectName("fieldLabel")
        layout.addWidget(label)

        input_widget = QLineEdit()
        input_widget.setObjectName("profileInput")
        input_widget.setPlaceholderText(f"Enter {label_text.lower()}")
        if key == "username":
            input_widget.setReadOnly(True)
        setattr(self, f"{key}_input", input_widget)
        layout.addWidget(input_widget)
        return wrapper

    def _create_password_field(self, label_text: str, key: str) -> QWidget:
        wrapper = QWidget()
        wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel(label_text)
        label.setObjectName("fieldLabel")
        layout.addWidget(label)

        input_widget = QLineEdit()
        input_widget.setObjectName("profileInput")
        input_widget.setEchoMode(QLineEdit.EchoMode.Password)
        input_widget.setPlaceholderText(f"Enter {label_text.lower()}")
        setattr(self, f"{key}_input", input_widget)
        layout.addWidget(input_widget)
        return wrapper

    def _connect_store(self) -> None:
        self.profile_store.changed.connect(self._on_store_changed)
        self.profile_store.success.connect(self._on_store_success)
        self.profile_store.error.connect(self._on_store_error)
        self.user_log_store.changed.connect(self._on_logs_changed)
        self.user_log_store.error.connect(self._on_logs_error)

    def _on_store_changed(self) -> None:
        profile = self.profile_store.profile
        if profile is None:
            return
        self._populate_form(profile, force=not self._editing)
        self._update_summary(profile)
        if profile.id > 0:
            self.user_log_store.load_for_user(profile.id)

    def _on_store_success(self, text: str) -> None:
        if self.profile_store.last_action == "profile":
            self._editing = False
            if self.profile_store.profile is not None:
                self._populate_form(self.profile_store.profile, force=True)
            self._sync_edit_state()
        elif self.profile_store.last_action == "password":
            self._clear_password_form()
        self._show_notice(text or "Profile updated successfully.", "success")

    def _on_store_error(self, text: str) -> None:
        self._show_notice(text or "Profile request failed.", "error")

    def _on_logs_changed(self) -> None:
        self._populate_activity_table(self.user_log_store.logs)

    def _on_logs_error(self, _text: str) -> None:
        self._populate_activity_table([])
        self.activity_subtitle.setText("Unable to load activity logs.")

    def _populate_form(self, profile: ProfileResponse, force: bool = False) -> None:
        if not force and self._editing:
            return
        self.username_input.setText(profile.username)
        self.fullname_input.setText(profile.fullname)
        self.email_input.setText(profile.email)
        self.phone_input.setText(profile.phone)
        self.area_input.setText(profile.area)

    def _update_summary(self, profile: ProfileResponse) -> None:
        self.hero_title.setText(profile.display_name)
        self.hero_subtitle.setText(f"@{profile.username}" if profile.username else "User account")

        self._set_badge_state(
            self.account_status_badge,
            "Active" if profile.is_active else "Inactive",
            "success" if profile.is_active else "danger",
        )
        self._set_badge_state(
            self.privilege_badge,
            "Super Admin" if profile.is_superadmin else "Standard User",
            "info" if profile.is_superadmin else "neutral",
        )
        self._set_badge_state(
            self.department_badge,
            f"Department #{profile.department_id or 0}",
            "neutral",
        )

    def _set_badge_state(self, label: QLabel, text: str, tone: str) -> None:
        label.setText(text)
        label.setProperty("tone", tone)
        label.style().unpolish(label)
        label.style().polish(label)

    def _toggle_editing(self) -> None:
        if self.profile_store.profile is None:
            self._show_notice("Profile data is not loaded yet.", "error")
            return

        if self._editing:
            self._editing = False
            self._populate_form(self.profile_store.profile, force=True)
        else:
            self._editing = True
        self._sync_edit_state()

    def _sync_edit_state(self) -> None:
        editable_inputs = (
            self.fullname_input,
            self.email_input,
            self.phone_input,
            self.area_input,
        )
        for widget in editable_inputs:
            widget.setReadOnly(not self._editing)

        self.edit_button.setText("Cancel" if self._editing else "Edit")
        self.save_button.setEnabled(self._editing)

    def _save_profile(self) -> None:
        if not self._editing:
            self._show_notice("Click Edit before saving profile changes.", "error")
            return

        payload = {
            "fullname": self.fullname_input.text().strip(),
            "email": self.email_input.text().strip(),
            "phone": self.phone_input.text().strip(),
            "area": self.area_input.text().strip(),
        }
        if any(not value for value in payload.values()):
            self._show_notice("Please fill all required profile fields.", "error")
            return

        self.profile_store.update_profile(payload)

    def _change_password(self) -> None:
        old_password = self.old_password_input.text()
        new_password = self.new_password_input.text()
        confirm_password = self.confirm_password_input.text()

        if not old_password or not new_password or not confirm_password:
            self._show_notice("Please fill all password fields.", "error")
            return
        if new_password != confirm_password:
            self._show_notice("New password and confirmation do not match.", "error")
            return
        self.profile_store.change_password(old_password, new_password)

    def _clear_password_form(self) -> None:
        self.old_password_input.clear()
        self.new_password_input.clear()
        self.confirm_password_input.clear()

    def _populate_activity_table(self, entries: list[UserLogResponse]) -> None:
        rows = [
            {
                "user": entry.user.display_name,
                "action": entry.action or "-",
                "created_at": entry.created_at_text,
                "detail": entry.detail or "-",
                "_entry": entry,
            }
            for entry in entries
        ]
        self.activity_table.set_rows(rows)
        count = len(entries)
        if count == 0:
            self.activity_subtitle.setText("No activity logs found for this user.")
        elif count == 1:
            self.activity_subtitle.setText("1 activity log found.")
        else:
            self.activity_subtitle.setText(f"{count} activity logs found.")

    def _activity_action_widget(self, row: dict) -> QWidget:
        text = str(row.get("action") or "-").strip()
        return self._activity_chip(text or "-", "#1d4ed8", "#dbeafe", "#2563eb")

    def _activity_chip(self, text: str, bg: str, fg: str, border: str) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumHeight(28)
        label.setMinimumWidth(86)
        label.setStyleSheet(
            f"background:{bg}; color:{fg}; border:1px solid {border}; border-radius:14px;"
            "padding:2px 8px; font-size:12px; font-weight:700;"
        )
        layout.addWidget(label)
        return wrapper

    def _show_notice(self, text: str, tone: str, duration_ms: int = 3600) -> None:
        self.notice_label.setText(text)
        self.notice_label.setProperty("tone", tone)
        self.notice_label.style().unpolish(self.notice_label)
        self.notice_label.style().polish(self.notice_label)
        self.notice_label.show()
        self._notice_timer.start(duration_ms)

    def _hide_notice(self) -> None:
        self.notice_label.hide()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            USER_MANAGEMENT_SIDEBAR_STYLES
            + f"""
            QWidget#profileRoot {{
                background: #0f1217;
                color: #e5e7eb;
            }}
            QScrollArea#profileScroll {{
                border: none;
                background: transparent;
            }}
            QWidget#profileContent {{
                background: transparent;
            }}
            QLabel#profileNotice {{
                border-radius: 14px;
                padding: 12px 14px;
                font-size: 13px;
                font-weight: 600;
            }}
            QLabel#profileNotice[tone="success"] {{
                background: rgba(34, 197, 94, 0.14);
                color: #86efac;
                border: 1px solid rgba(34, 197, 94, 0.35);
            }}
            QLabel#profileNotice[tone="error"] {{
                background: rgba(239, 68, 68, 0.14);
                color: #fca5a5;
                border: 1px solid rgba(239, 68, 68, 0.35);
            }}
            QFrame#profileHeroCard,
            QFrame#profileCard {{
                background: #171b22;
                border: 1px solid #2a3140;
                border-radius: 18px;
            }}
            QFrame#avatarWrap {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #152235,
                    stop: 1 #0f1725
                );
                border: 1px solid rgba(59, 130, 246, 0.35);
                border-radius: 54px;
            }}
            QLabel#avatarIcon {{
                background: transparent;
                color: #eff6ff;
                font-size: 34px;
                font-weight: 700;
            }}
            QLabel#avatarStatusDot {{
                background: #22c55e;
                border: 2px solid #171b22;
                border-radius: 9px;
            }}
            QLabel#heroTitle {{
                color: #f8fafc;
                font-size: 28px;
                font-weight: 700;
            }}
            QLabel#heroSubtitle {{
                color: #94a3b8;
                font-size: 13px;
            }}
            QLabel#profileBadge {{
                border-radius: 999px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 700;
                border: 1px solid rgba(148, 163, 184, 0.22);
                background: rgba(148, 163, 184, 0.08);
                color: #cbd5e1;
            }}
            QLabel#profileBadge[tone="success"] {{
                background: rgba(34, 197, 94, 0.14);
                color: #86efac;
                border: 1px solid rgba(34, 197, 94, 0.32);
            }}
            QLabel#profileBadge[tone="danger"] {{
                background: rgba(239, 68, 68, 0.14);
                color: #fca5a5;
                border: 1px solid rgba(239, 68, 68, 0.3);
            }}
            QLabel#profileBadge[tone="info"] {{
                background: rgba(59, 130, 246, 0.14);
                color: #93c5fd;
                border: 1px solid rgba(59, 130, 246, 0.32);
            }}
            QFrame#cardHeader {{
                background: rgba(255, 255, 255, 0.02);
                border: none;
                border-bottom: 1px solid #242c39;
                border-top-left-radius: 18px;
                border-top-right-radius: 18px;
            }}
            QLabel#cardTitle {{
                color: #f8fafc;
                font-size: 20px;
                font-weight: 700;
            }}
            QLabel#cardSubtitle {{
                color: #94a3b8;
                font-size: 12px;
            }}
            QLabel#fieldLabel {{
                color: #dbe3ef;
                font-size: 12px;
                font-weight: 600;
            }}
            QLabel#helperText,
            QLabel#noteBody {{
                color: #9aa6b8;
                font-size: 12px;
                line-height: 1.45em;
            }}
            QLabel#noteTitle {{
                color: #e2e8f0;
                font-size: 14px;
                font-weight: 700;
            }}
            QLineEdit#profileInput {{
                background: #101722;
                border: 1px solid #2f3b4d;
                border-radius: 12px;
                padding: 12px 14px;
                color: #f8fafc;
                font-size: 13px;
                selection-background-color: #2563eb;
                min-height: 20px;
            }}
            QLineEdit#profileInput:focus {{
                border: 1px solid #3b82f6;
            }}
            QLineEdit#profileInput:read-only {{
                background: #0d141d;
                border: 1px solid #243041;
                color: #93a1b6;
            }}
            QPushButton#primaryButton,
            QPushButton#secondaryButton {{
                border-radius: 12px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: 700;
                min-height: 18px;
            }}
            QPushButton#primaryButton {{
                background: #2563eb;
                color: white;
                border: 1px solid #2563eb;
            }}
            QPushButton#primaryButton:hover:!disabled {{
                background: #1d4ed8;
                border: 1px solid #1d4ed8;
            }}
            QPushButton#primaryButton:disabled {{
                background: #1c2431;
                color: #66758d;
                border: 1px solid #263142;
            }}
            QPushButton#secondaryButton {{
                background: rgba(148, 163, 184, 0.08);
                color: #e2e8f0;
                border: 1px solid rgba(148, 163, 184, 0.18);
            }}
            QPushButton#secondaryButton:hover {{
                background: rgba(148, 163, 184, 0.14);
            }}
            QFrame#infoNote {{
                background: rgba(245, 158, 11, 0.08);
                border: 1px solid rgba(245, 158, 11, 0.24);
                border-radius: 14px;
            }}
            """
        )

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        p.fillPath(path, QColor(Constants.DARK_BG))   # dark bg — cards float above it
        super().paintEvent(event)

