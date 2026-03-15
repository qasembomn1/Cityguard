from PySide6.QtWidgets import QLineEdit


class PrimeInput(QLineEdit):
    def __init__(self, parent=None, radius=14):
        super().__init__(parent)
        self._radius = radius
        self._error = False
        self._apply_style()

    def _build_stylesheet(self) -> str:
        border_color = "#ff6b81" if self._error else "#3a3a3d"
        focus_border_color = "#ff6b81" if self._error else "#6c63ff"
        return f"""
            QLineEdit {{
                background-color: rgba(30, 30, 33, 0.92);
                border: 1px solid {border_color};
                border-radius: {self._radius}px;
                padding: 14px 16px;
                font-size: 14px;
                color: white;
            }}
            QLineEdit:focus {{
                border: 1px solid {focus_border_color};
            }}
            QLineEdit:disabled {{
                color: rgba(255, 255, 255, 0.55);
                background-color: rgba(30, 30, 33, 0.65);
            }}
        """

    def _apply_style(self):
        self.setStyleSheet(self._build_stylesheet())

    def set_error(self, enabled=True):
        self._error = enabled
        self._apply_style()

    def clear_error(self):
        self.set_error(False)
