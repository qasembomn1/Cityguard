from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSizePolicy, QToolButton, QWidget


_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


class SidebarToggleButton(QToolButton):
    def __init__(self, sidebar_visible: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebarToggleButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setIconSize(QSize(25, 25))
        self.setFixedSize(40, 40)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            """
            QToolButton#sidebarToggleButton {
                background: #27303d;
                border: 1px solid #374151;
                border-radius: 11px;
                padding: 0;
            }
            QToolButton#sidebarToggleButton:hover {
                background: #313b4a;
                border-color: #4b5a6f;
            }
            QToolButton#sidebarToggleButton[sidebarVisible="true"] {
                background: #2563eb;
                border: none;
            }
            QToolButton#sidebarToggleButton[sidebarVisible="true"]:hover {
                background: #1d4ed8;
            }
            QToolButton#sidebarToggleButton:disabled {
                background: #1f252d;
                color: #64748b;
                border: 1px solid #2a3340;
            }
            """
        )
        self.sync_visibility(sidebar_visible)

    def sync_visibility(self, sidebar_visible: bool) -> None:
        visible = bool(sidebar_visible)
        self.setProperty("sidebarVisible", visible)
        self.setToolTip("Hide Sidebar" if visible else "Show Sidebar")
        self.setAccessibleName(self.toolTip())
        self.setIcon(QIcon(_icon_path("close.svg" if visible else "left_toggle.svg")))
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.update()
