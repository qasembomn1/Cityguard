import sys
from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QFrame,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
)


class SelectItem(QWidget):
    toggled = Signal(object, bool)

    def __init__(self, text, value, checked=False, parent=None):
        super().__init__(parent)
        self.text = text
        self.value = value
        self.checked = checked
        self.hovered = False
        self.setFixedHeight(42)
        self.setCursor(Qt.PointingHandCursor)

    def set_checked(self, checked: bool):
        self.checked = checked
        self.update()

    def enterEvent(self, event):
        self.hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.checked = not self.checked
        self.toggled.emit(self.value, self.checked)
        self.update()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(4, 2, -4, -2)

        if self.hovered:
            bg = QColor("#2a2d31")
            text_color = QColor("#f5f5f5")
        else:
            bg = QColor("#1f2023")
            text_color = QColor("#f5f5f5")
        border_color = QColor("#2563eb") if self.checked else QColor("#64748b")
        box_fill = QColor("#2563eb") if self.checked else QColor("#1b1d20")

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(rect, 4, 4)

        painter.setPen(QPen(text_color))
        text_rect = rect.adjusted(14, 0, -42, 0)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text)

        box_size = 18
        box_x = rect.right() - box_size - 12
        box_y = rect.y() + (rect.height() - box_size) // 2
        box_rect = rect.adjusted(
            box_x - rect.x(),
            box_y - rect.y(),
            -(rect.width() - box_size - (box_x - rect.x())),
            -(rect.height() - box_size - (box_y - rect.y())),
        )
        painter.setPen(QPen(border_color, 1.4))
        painter.setBrush(QBrush(box_fill))
        painter.drawRoundedRect(box_rect, 5, 5)

        if self.checked:
            check_pen = QPen(QColor("#ffffff"), 2.1)
            check_pen.setCapStyle(Qt.RoundCap)
            check_pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(check_pen)
            x = box_rect.x()
            y = box_rect.y()
            s = box_size
            painter.drawLine(x + int(s * 0.22), y + int(s * 0.55), x + int(s * 0.43), y + int(s * 0.74))
            painter.drawLine(x + int(s * 0.43), y + int(s * 0.74), x + int(s * 0.78), y + int(s * 0.30))


class PopupPanel(QFrame):
    selection_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)
        self.setObjectName("popupPanel")
        self.resize(440, 210)

        self.items = []
        self.selected_values = set()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.container = QFrame()
        self.container.setObjectName("popupContainer")
        self.container.setAutoFillBackground(True)
        outer.addWidget(self.container)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(10, 10, 10, 10)
        container_layout.setSpacing(6)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("background: transparent;")

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(4)
        self.content_layout.addStretch()

        self.scroll.setWidget(self.content)
        container_layout.addWidget(self.scroll)

        self.setStyleSheet("""
            #popupPanel {
                background-color: #1b1c1f;
                border: 1px solid #101114;
                border-radius: 10px;
            }
            #popupContainer {
                background-color: #1b1c1f;
                border: 1px solid #101114;
                border-radius: 10px;
            }
            QScrollArea {
                background: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 4px 0 4px 0;
            }
            QScrollBar::handle:vertical {
                background: #3a3d42;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

    def set_options(self, options, selected_values=None):
        self.selected_values = set(selected_values or [])
        self.items.clear()

        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for option in options:
            text = option["label"]
            value = option["value"]
            item_widget = SelectItem(text, value, value in self.selected_values)
            item_widget.toggled.connect(self.on_item_toggled)
            self.items.append(item_widget)
            self.content_layout.addWidget(item_widget)

        self.content_layout.addStretch()

    def on_item_toggled(self, value, checked):
        if checked:
            self.selected_values.add(value)
        else:
            self.selected_values.discard(value)
        self.selection_changed.emit()


class PrimeMultiSelect(QWidget):
    selection_changed = Signal(list)

    def __init__(self, options=None, placeholder="Select", parent=None):
        super().__init__(parent)
        self.options = options or []
        self.selected_values = []
        self.placeholder = placeholder
        self.popup = None

        self.setFixedWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.button = QPushButton()
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.setFixedHeight(40)
        self.button.clicked.connect(self.toggle_popup)
        self.button.setText("")
        layout.addWidget(self.button)

        button_layout = QHBoxLayout(self.button)
        button_layout.setContentsMargins(14, 0, 12, 0)
        button_layout.setSpacing(8)

        self._label = QLabel("", self.button)
        self._label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._label.setStyleSheet("color:#d6d6d6; background:transparent;")
        button_layout.addWidget(self._label, 1)

        self._arrow = QLabel("⌄", self.button)
        self._arrow.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._arrow.setStyleSheet("color:#aeb6c2; background:transparent; font-size:14px;")
        button_layout.addWidget(self._arrow, 0, Qt.AlignRight | Qt.AlignVCenter)

        self.popup = PopupPanel(self)
        self.popup.selection_changed.connect(self.sync_from_popup)
        self.popup.installEventFilter(self)

        self.setStyleSheet("""
            QWidget {
                background-color: #111315;
                color: #e5e7eb;
                font-size: 14px;
            }
            QPushButton {
                text-align: left;
                padding: 0 36px 0 14px;
                background-color: #2a2d31;
                color: #d6d6d6;
                border: 1px solid #2f3338;
                border-radius: 10px;
            }
            QPushButton:hover {
                background-color: #30343a;
                border: 1px solid #3a3f45;
            }
        """)

        self.refresh_label()

    def set_options(self, options):
        self.options = options
        self.refresh_label()

    def set_value(self, values):
        self.selected_values = list(values)
        self.refresh_label()

    def value(self):
        return self.selected_values

    def refresh_label(self):
        labels = [
            opt["label"] for opt in self.options
            if opt["value"] in self.selected_values
        ]

        if labels:
            text = ", ".join(labels)
        else:
            text = self.placeholder

        self._label.setText(text)
        popup_visible = bool(self.popup is not None and self.popup.isVisible())
        self._arrow.setText("⌃" if popup_visible else "⌄")

    def toggle_popup(self):
        if self.popup is None:
            return
        if self.popup.isVisible():
            self.popup.hide()
            self.refresh_label()
            return

        self.popup.set_options(self.options, self.selected_values)

        pos = self.button.mapToGlobal(QPoint(0, self.button.height() + 6))
        self.popup.move(pos)
        self.popup.resize(self.width(), 210)
        self.popup.show()
        self.refresh_label()

    def sync_from_popup(self):
        if self.popup is None:
            return
        self.selected_values = [
            opt["value"] for opt in self.options
            if opt["value"] in self.popup.selected_values
        ]
        self.refresh_label()
        self.selection_changed.emit(self.selected_values)

    def eventFilter(self, watched, event):
        if self.popup is not None and watched is self.popup and event.type() in (QEvent.Type.Show, QEvent.Type.Hide):
            self.refresh_label()
        return super().eventFilter(watched, event)


class Demo(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PrimeVue Style MultiSelect - PySide6")
        self.resize(560, 320)
        self.setStyleSheet("background-color: #0f1113;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 40, 50, 40)

        options = [
            {"label": "CAM-1", "value": 1},
            {"label": "CAM-2", "value": 2},
            {"label": "CAM-4", "value": 4},
            {"label": "CAM-5", "value": 5},
        ]

        self.select = PrimeMultiSelect(
            options=options,
            placeholder="Select Cameras"
        )
        self.select.selection_changed.connect(self.on_change)

        self.info = QLabel("Selected: []")
        self.info.setStyleSheet("""
            QLabel {
                color: #d1d5db;
                padding-top: 12px;
                font-size: 13px;
            }
        """)

        layout.addWidget(self.select)
        layout.addWidget(self.info)
        layout.addStretch()

    def on_change(self, values):
        self.info.setText(f"Selected: {values}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Demo()
    window.show()
    sys.exit(app.exec())
