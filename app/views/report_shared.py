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


REPORT_NAV_ITEMS = [
    ("LPR", "report.svg", "/report/lpr", "LPR Report"),
    ("Face", "faces.svg", "/report/face", "Face Report"),
    ("Count", "view.svg", "/report/face_count", "Face Count Report"),
]


REPORT_SIDEBAR_STYLES = """
QFrame#reportSideNav {
    background: #181d25;
    border: 1px solid #2f3948;
    border-radius: 18px;
}
QToolButton#reportSideBtn, QToolButton#reportSideBtnActive {
    min-width: 72px;
    max-width: 72px;
    min-height: 72px;
    max-height: 72px;
    border-radius: 16px;
    font-size: 11px;
    font-weight: 700;
    text-align: center;
    padding: 6px 4px;
}
QToolButton#reportSideBtn {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #212833,
        stop:1 #1a2028);
    color: #9aa8bb;
    border: 1px solid #313c4c;
}
QToolButton#reportSideBtn:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #273244,
        stop:1 #1f2937);
    color: #f8fafc;
    border: 1px solid #4b607a;
}
QToolButton#reportSideBtnActive {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #2563eb,
        stop:1 #1d4ed8);
    color: white;
    border: 1px solid #60a5fa;
}
"""


class ReportSidebar(QFrame):
    navigate = Signal(str)

    def __init__(self, current_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("reportSideNav")
        self.setFixedWidth(96)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        for label, icon_name, path, tooltip in REPORT_NAV_ITEMS:
            btn = QToolButton()
            btn.setText(label)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setFixedSize(72, 72)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip)
            btn.setObjectName("reportSideBtnActive" if path == current_path else "reportSideBtn")
            icon_file = _icon_path(icon_name)
            if os.path.isfile(icon_file):
                btn.setIcon(QIcon(icon_file))
                btn.setIconSize(QSize(22, 22))
            btn.clicked.connect(lambda _checked=False, p=path: self.navigate.emit(p))
            layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch(1)
