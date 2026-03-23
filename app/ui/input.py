import sys
from PySide6.QtCore import QSize
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QSizePolicy, QLineEdit
)


class PrimeInput(QLineEdit):
    _height = 40

    def __init__(
        self,
        parent=None,
        radius=10,
        type="text",
        minimum=0.0,
        maximum=999999999.0,
        decimals=0,
        value=None,
        placeholder_text="",
    ):
        super().__init__(parent)
        self._radius = radius
        self._error = False
        self._type = type
        self._minimum = float(minimum)
        self._maximum = float(maximum)
        self._decimals = decimals

        self.setFixedHeight(self._height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        if type == "number":
            validator = QDoubleValidator(self._minimum, self._maximum, decimals, self)
            validator.setNotation(QDoubleValidator.Notation.StandardNotation)
            self.setValidator(validator)
            self.setValue(value if value is not None else minimum)

        if placeholder_text:
            self.setPlaceholderText(placeholder_text)

        self._apply_style()

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(max(180, hint.width()), self._height)

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(max(120, hint.width()), self._height)

    def value(self) -> float:
        try:
            return float(self.text())
        except ValueError:
            return self._minimum

    def setValue(self, val) -> None:
        v = max(self._minimum, min(self._maximum, float(val)))
        self.setText(str(int(v)) if self._decimals == 0 else f"{v:.{self._decimals}f}")

    def _build_stylesheet(self) -> str:
        border_color = "#ff6b81" if self._error else "#3a3a3d"
        focus_border_color = "#ff6b81" if self._error else "#1456be"
        return f"""
            QLineEdit {{
                background-color: #2a2d31;
                border: 1px solid {border_color};
                border-radius: {self._radius}px;
                padding: 0 16px;
                font-size: 14px;
                color: white;
                selection-background-color: #1456be;
                selection-color: white;
            }}
            QLineEdit:focus {{
                border: 1px solid {focus_border_color};
            }}
            QLineEdit:disabled {{
                color: rgba(255, 255, 255, 0.55);
                background-color: rgba(42, 45, 49, 0.65);
            }}
        """

    def _apply_style(self):
        self.setStyleSheet(self._build_stylesheet())

    def set_error(self, enabled=True):
        self._error = enabled
        self._apply_style()

    def clear_error(self):
        self.set_error(False)


# demo window
class DemoWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("PrimeInput Demo")
        self.setMinimumSize(400, 260)
        self.setStyleSheet("background-color: #1e1e21;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        self.text_input = PrimeInput(radius=14, placeholder_text="Enter your name...")
        layout.addWidget(self.text_input)

        self.number_input = PrimeInput(
            type="number",
            minimum=1,
            maximum=65535,
            decimals=0,
            value=554,
            placeholder_text="Enter port",
        )
        layout.addWidget(self.number_input)

        btn_error = QPushButton("Set Error")
        btn_clear = QPushButton("Clear Error")

        btn_error.clicked.connect(lambda: self.text_input.set_error(True))
        btn_clear.clicked.connect(lambda: self.text_input.clear_error())

        layout.addWidget(btn_error)
        layout.addWidget(btn_clear)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DemoWindow()
    window.show()
    sys.exit(app.exec())
