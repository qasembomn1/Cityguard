import sys
from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
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
    QSizePolicy,
    QToolButton,
)


class SelectItem(QWidget):
    toggled = Signal(object, bool)
    _item_height = 42

    def __init__(self, text, value, checked=False, parent=None):
        super().__init__(parent)
        self.text = text
        self.value = value
        self.checked = checked
        self.hovered = False
        self.setFixedHeight(self._item_height)
        self.setCursor(Qt.PointingHandCursor)

    def sizeHint(self):
        return QSize(0, self._item_height)

    def minimumSizeHint(self):
        return QSize(0, self._item_height)

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


class ChevronIcon(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = False
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedSize(12, 8)

    def set_expanded(self, expanded: bool):
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self.update()

    def sizeHint(self):
        return QSize(12, 8)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#9ca3af"), 1.5))

        if self._expanded:
            painter.drawLine(1, 5, 6, 1)
            painter.drawLine(6, 1, 11, 5)
        else:
            painter.drawLine(1, 2, 6, 6)
            painter.drawLine(6, 6, 11, 2)


class PopupPanel(QFrame):
    selection_changed = Signal()
    _padding = 10
    _min_content_height = 24

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setObjectName("popupPanel")
        self.resize(440, 210)

        self.items = []
        self.selected_values = set()

        self.container = QFrame(self)
        self.container.setObjectName("popupContainer")
        self.container.setAutoFillBackground(True)

        self.scroll = QScrollArea(self.container)
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

        self.setStyleSheet("""
            #popupPanel {
                background: transparent;
                border: none;
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
        self._sync_shell_geometry()

    def resizeEvent(self, event):
        self._sync_shell_geometry()
        super().resizeEvent(event)

    def _sync_shell_geometry(self) -> None:
        self.container.setGeometry(self.rect())
        inner_rect = self.container.rect().adjusted(
            self._padding,
            self._padding,
            -self._padding,
            -self._padding,
        )
        self.scroll.setGeometry(inner_rect)

    def set_options(self, options, selected_values=None):
        self.selected_values = set(selected_values or [])
        self.items.clear()

        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for option in options:
            text, value = PrimeMultiSelect.normalize_option(option)
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

    def preferred_height(self) -> int:
        item_height = sum(item.sizeHint().height() for item in self.items)
        spacing = self.content_layout.spacing() * max(0, len(self.items) - 1)
        margins = self.content_layout.contentsMargins()
        content_height = (
            margins.top()
            + item_height
            + spacing
            + margins.bottom()
        )
        return max(
            (self._padding * 2) + content_height,
            (self._padding * 2) + self._min_content_height,
        )


class PrimeMultiSelect(QWidget):
    selection_changed = Signal(list)

    def __init__(self, options=None, placeholder="Select", parent=None):
        super().__init__(parent)
        self.setObjectName("primeMultiSelect")
        self.options = list(options or [])
        self.selected_values = []
        self.placeholder = placeholder
        self.popup = None

        self.setMinimumWidth(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

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

        self.clear_btn = QToolButton(self.button)
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setText("×")
        self.clear_btn.setFixedSize(20, 20)
        self.clear_btn.hide()
        self.clear_btn.clicked.connect(self.clear)
        button_layout.addWidget(self.clear_btn, 0, Qt.AlignRight | Qt.AlignVCenter)

        self._arrow = ChevronIcon(self.button)
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
            QToolButton {
                background: transparent;
                border: none;
                border-radius: 10px;
                color: #aeb6c2;
                font-size: 15px;
                font-weight: 600;
                padding: 0;
            }
            QToolButton:hover {
                background-color: #3a3f45;
                color: #f3f4f6;
            }
        """)

        self.refresh_label()

    @staticmethod
    def normalize_option(option):
        if isinstance(option, dict):
            return str(option.get("label", "")), option.get("value")
        return str(option), option

    def set_options(self, options):
        self.options = list(options or [])
        valid_values = {self.normalize_option(option)[1] for option in self.options}
        self.selected_values = [value for value in self.selected_values if value in valid_values]
        self.refresh_label()

    def set_value(self, values):
        valid_values = {self.normalize_option(option)[1] for option in self.options}
        incoming_values = list(values or [])
        self.selected_values = [value for value in incoming_values if value in valid_values]
        self.refresh_label()

    def value(self):
        return self.selected_values

    def clear(self):
        self.selected_values = []
        if self.popup is not None:
            self.popup.selected_values.clear()
            for item in self.popup.items:
                item.set_checked(False)
            if self.popup.isVisible():
                self.popup.hide()
        self.refresh_label()
        self.selection_changed.emit(self.selected_values)

    def refresh_label(self):
        labels = [
            label for opt in self.options
            for label, value in [self.normalize_option(opt)]
            if value in self.selected_values
        ]

        if labels:
            text = ", ".join(labels)
        else:
            text = self.placeholder

        self._label.setText(text)
        self.clear_btn.setVisible(bool(labels))
        popup_visible = bool(self.popup is not None and self.popup.isVisible())
        self._arrow.set_expanded(popup_visible)

    def _popup_screen_geometry(self):
        anchor = self.button.mapToGlobal(self.button.rect().center())
        screen = QApplication.screenAt(anchor)
        if screen is None and self.window().windowHandle() is not None:
            screen = self.window().windowHandle().screen()
        if screen is None:
            screen = QApplication.primaryScreen()
        return screen.availableGeometry() if screen is not None else None

    def _popup_position(self, popup_width: int, popup_height: int) -> QPoint:
        gap = 6
        top_left = self.button.mapToGlobal(QPoint(0, 0))
        top_right = self.button.mapToGlobal(QPoint(self.button.width(), 0))
        bottom_left = self.button.mapToGlobal(QPoint(0, self.button.height()))
        screen_rect = self._popup_screen_geometry()
        x = top_left.x()

        if screen_rect is None:
            return QPoint(x, bottom_left.y() + gap)

        space_below = screen_rect.bottom() - bottom_left.y()
        space_above = top_left.y() - screen_rect.top()

        if space_below >= popup_height or space_below >= space_above:
            y = bottom_left.y() + gap
        else:
            y = top_left.y() - popup_height - gap

        if x + popup_width - 1 > screen_rect.right():
            x = top_right.x() - popup_width

        min_x = screen_rect.left()
        max_x = max(min_x, screen_rect.right() - popup_width + 1)
        min_y = screen_rect.top()
        max_y = max(min_y, screen_rect.bottom() - popup_height + 1)

        x = min(max(x, min_x), max_x)
        y = min(max(y, min_y), max_y)
        return QPoint(x, y)

    def toggle_popup(self):
        if self.popup is None:
            return
        if self.popup.isVisible():
            self.popup.hide()
            self.refresh_label()
            return

        self.popup.set_options(self.options, self.selected_values)
        screen_rect = self._popup_screen_geometry()
        popup_width = self.button.width() or self.width() or 180
        popup_height = self.popup.preferred_height()
        if screen_rect is not None:
            popup_width = min(popup_width, screen_rect.width())
            popup_height = min(popup_height, screen_rect.height())

        self.popup.resize(popup_width, popup_height)
        self.popup.move(self._popup_position(popup_width, popup_height))
        self.popup.show()
        self.refresh_label()

    def sync_from_popup(self):
        if self.popup is None:
            return
        self.selected_values = [
            value for opt in self.options
            for _, value in [self.normalize_option(opt)]
            if value in self.popup.selected_values
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
