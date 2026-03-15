from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton

from app.constants._init_ import Constants
from app.ui.button import PrimeButton


class Sidebar(QWidget):
    def __init__(self, on_close, width, parent=None):
        super().__init__(parent)

        self.setFixedWidth(width)
        self.setStyleSheet(
            f"background:{Constants.SIDEBAR_BG}; border-right:1px solid {Constants.BORDER};"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        close_btn = PrimeButton("Close", "danger")
        close_btn.clicked.connect(on_close)
        layout.addWidget(close_btn)
