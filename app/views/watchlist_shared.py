from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from app.views.home.user._shared import USER_MANAGEMENT_SIDEBAR_STYLES


_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


WATCHLIST_NAV_ITEMS = [
    ("LPR\nBlack", "list_management.svg", "/lpr/blacklist"),
    ("LPR\nWhite", "list_management.svg", "/lpr/whitelist"),
    ("Face\nBlack", "faces.svg", "/face/blacklist"),
    ("Face\nWhite", "faces.svg", "/face/whitelist"),
]


WATCHLIST_SIDEBAR_STYLES = USER_MANAGEMENT_SIDEBAR_STYLES


class WatchlistSidebar(QFrame):
    navigate = Signal(str)

    def __init__(self, current_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("userSideNav")
        self.setFixedWidth(96)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        for label, icon_name, path in WATCHLIST_NAV_ITEMS:
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


class WatchlistPlaceholderPage(QWidget):
    navigate = Signal(str)

    def __init__(
        self,
        current_path: str,
        title_text: str,
        description_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        self.sidebar = WatchlistSidebar(current_path, self)
        self.sidebar.navigate.connect(self.navigate.emit)
        root.addWidget(self.sidebar)

        main = QFrame()
        main.setObjectName("userMainPanel")
        root.addWidget(main, 1)

        layout = QVBoxLayout(main)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel(title_text)
        title.setObjectName("watchlistSectionTitle")
        layout.addWidget(title)

        subtitle = QLabel(description_text)
        subtitle.setObjectName("watchlistSectionSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        hint = QLabel("This route now shares the same sidebar layout as the user management pages.")
        hint.setObjectName("watchlistSectionHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)

        self.setStyleSheet(
            WATCHLIST_SIDEBAR_STYLES
            + """
            QWidget {
                color: #f5f7fb;
            }
            QLabel#watchlistSectionTitle {
                color: #f8fafc;
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#watchlistSectionSubtitle {
                color: #cbd5e1;
                font-size: 14px;
            }
            QLabel#watchlistSectionHint {
                color: #93a1b6;
                font-size: 13px;
            }
            """
        )
