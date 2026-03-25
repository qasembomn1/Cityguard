from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QToolButton, QVBoxLayout, QWidget


_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


SECTION_SIDEBAR_STYLES = """
QFrame#sectionSideNav {
    background: #1b1c20;
    border: 1px solid #2e3138;
    border-radius: 12px;
}
QToolButton#sectionSideBtn, QToolButton#sectionSideBtnActive {
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
QToolButton#sectionSideBtn {
    background: #23272e;
    color: #8f98a8;
    border-color: #2f3742;
}
QToolButton#sectionSideBtn:hover {
    background: #2b3038;
    color: #f3f6fc;
    border-color: #4b5563;
}
QToolButton#sectionSideBtnActive {
    background: #2f6ff0;
    color: white;
    border-color: #5f92ff;
}
"""


class SectionSidebar(QFrame):
    navigate = Signal(str)

    def __init__(
        self,
        current_path: str,
        nav_items: list[dict[str, str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("sectionSideNav")
        self.setFixedWidth(96)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        for item in nav_items:
            path = str(item.get("path") or "")
            btn = QToolButton()
            btn.setText(str(item.get("label") or ""))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setFixedSize(72, 72)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(str(item.get("tooltip") or path))
            btn.setObjectName("sectionSideBtnActive" if path == current_path else "sectionSideBtn")

            icon_name = str(item.get("icon") or "")
            icon_file = _icon_path(icon_name)
            if os.path.isfile(icon_file):
                btn.setIcon(QIcon(icon_file))
                btn.setIconSize(QSize(22, 22))

            btn.clicked.connect(lambda _checked=False, p=path: self.navigate.emit(p))
            layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch(1)
