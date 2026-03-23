import sys

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class PrimeTextArea(QTextEdit):
    def __init__(
        self,
        parent=None,
        radius: int = 14,
        min_height: int = 120,
        placeholder_text: str = "",
        accept_rich_text: bool = False,
    ) -> None:
        super().__init__(parent)
        self._radius = radius
        self._error = False

        self.setAcceptRichText(accept_rich_text)
        self.setPlaceholderText(placeholder_text)
        self.setMinimumHeight(max(64, min_height))
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.document().setDocumentMargin(0)
        self._apply_style()

    def _build_stylesheet(self) -> str:
        border_color = "#ff6b81" if self._error else "#3a3a3d"
        focus_border_color = "#ff6b81" if self._error else "#1456be"
        scrollbar_handle = "#4b5563" if self._error else "#3a3a3d"

        return f"""
            QTextEdit {{
                background-color: rgba(30, 30, 33, 0.92);
                border: 1px solid {border_color};
                border-radius: {self._radius}px;
                padding: 14px 16px;
                font-size: 14px;
                color: white;
                selection-background-color: #1456be;
                selection-color: white;
            }}
            QTextEdit:focus {{
                border: 1px solid {focus_border_color};
            }}
            QTextEdit:disabled {{
                color: rgba(255, 255, 255, 0.55);
                background-color: rgba(30, 30, 33, 0.65);
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 10px 4px 10px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {scrollbar_handle};
                border-radius: 4px;
                min-height: 24px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
                height: 0;
            }}
        """

    def _apply_style(self) -> None:
        self.setStyleSheet(self._build_stylesheet())

    def set_error(self, enabled: bool = True) -> None:
        self._error = enabled
        self._apply_style()

    def clear_error(self) -> None:
        self.set_error(False)

    def set_placeholder_text(self, text: str) -> None:
        self.setPlaceholderText(text)


class DemoWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("PrimeTextArea Demo")
        self.setMinimumSize(440, 320)
        self.setStyleSheet("background-color: #1e1e21;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        self.text_area = PrimeTextArea(
            radius=14,
            min_height=160,
            placeholder_text="Write your note here...",
        )

        btn_error = QPushButton("Set Error")
        btn_clear = QPushButton("Clear Error")

        btn_error.clicked.connect(lambda: self.text_area.set_error(True))
        btn_clear.clicked.connect(lambda: self.text_area.clear_error())

        layout.addWidget(self.text_area)
        layout.addWidget(btn_error)
        layout.addWidget(btn_clear)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = DemoWindow()
    window.show()

    sys.exit(app.exec())
