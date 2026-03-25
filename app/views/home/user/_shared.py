from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget


_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


USER_NAV_ITEMS = [
    ("Profile", "profile.svg", "/user/profile"),
    ("Users", "user_managment.svg", "/user/users"),
    ("Roles", "settings.svg", "/user/roles"),
    ("Department", "home.svg", "/user/department"),
]


USER_MANAGEMENT_SIDEBAR_STYLES = """
QFrame#userSideNav {
    background: #1b1c20;
    border: 1px solid #2e3138;
    border-radius: 12px;
}
QToolButton#userSideBtn, QToolButton#userSideBtnActive {
    min-width: 72px;
    max-width: 72px;
    min-height: 72px;
    max-height: 72px;
    border-radius: 14px;
    border: 1px solid transparent;
    font-size: 11px;
    font-weight: 600;
    text-align: center;
    padding: 5px 2px;
}
QToolButton#userSideBtn {
    background: #23272e;
    color: #8f98a8;
    border-color: #2f3742;
}
QToolButton#userSideBtn:hover {
    background: #2b3038;
    color: #f3f6fc;
    border-color: #4b5563;
}
QToolButton#userSideBtnActive {
    background: #2f6ff0;
    color: white;
    border-color: #5f92ff;
}
QFrame#userMainPanel {
    background: #1f2024;
    border: 1px solid #2e3138;
    border-radius: 12px;
}
"""


class UserManagementSidebar(QFrame):
    navigate = Signal(str)

    def __init__(self, current_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_path = current_path
        self.setObjectName("userSideNav")
        self.setFixedWidth(96)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        for label, icon_name, path in USER_NAV_ITEMS:
            btn = QToolButton()
            btn.setText(label)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setFixedSize(72, 72)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setObjectName("userSideBtnActive" if path == current_path else "userSideBtn")
            icon_file = _icon_path(icon_name)
            if os.path.isfile(icon_file):
                btn.setIcon(QIcon(icon_file))
                btn.setIconSize(QSize(22, 22))
            btn.clicked.connect(lambda _checked=False, p=path: self.navigate.emit(p))
            layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch(1)


class UserManagementPlaceholderPage(QWidget):
    navigate = Signal(str)

    def __init__(
        self,
        current_path: str,
        title_text: str,
        description_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._current_path = current_path

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        self.sidebar = UserManagementSidebar(current_path, self)
        self.sidebar.navigate.connect(self.navigate.emit)
        root.addWidget(self.sidebar)

        main = QFrame()
        main.setObjectName("userMainPanel")
        root.addWidget(main, 1)

        layout = QVBoxLayout(main)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel(title_text)
        title.setObjectName("userSectionTitle")
        layout.addWidget(title)

        subtitle = QLabel(description_text)
        subtitle.setObjectName("userSectionSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        hint = QLabel("This route now shares the same sidebar structure as the profile page.")
        hint.setObjectName("userSectionHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)

        self.setStyleSheet(
            USER_MANAGEMENT_SIDEBAR_STYLES
            + """
            QWidget {
                color: #f5f7fb;
            }
            QLabel#userSectionTitle {
                color: #f8fafc;
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#userSectionSubtitle {
                color: #cbd5e1;
                font-size: 14px;
                line-height: 1.45em;
            }
            QLabel#userSectionHint {
                color: #93a1b6;
                font-size: 13px;
            }
            """
        )
