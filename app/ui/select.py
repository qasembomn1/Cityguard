import sys

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class SelectItem(QWidget):
    selected = Signal(object)
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

    def set_checked(self, checked: bool) -> None:
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
        self.selected.emit(self.value)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(4, 2, -4, -2)

        if self.checked:
            bg = QColor("#e7e7e7")
            text_color = QColor("#111111")
        elif self.hovered:
            bg = QColor("#2a2d31")
            text_color = QColor("#f5f5f5")
        else:
            bg = QColor("#1f2023")
            text_color = QColor("#f5f5f5")

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(rect, 4, 4)

        painter.setPen(QPen(text_color))
        text_rect = rect.adjusted(16, 0, -12, 0)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text)


class SelectTrigger(QFrame):
    clicked = Signal()
    _height = 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self._hovered = False
        self.setFixedHeight(self._height)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_text(self, text: str) -> None:
        self._text = text
        self.update()

    def sizeHint(self):
        return QSize(180, self._height)

    def minimumSizeHint(self):
        return QSize(120, self._height)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(0, 0, -1, -1)
        bg = QColor("#30343a") if self._hovered else QColor("#2a2d31")
        border = QColor("#3a3f45") if self._hovered else QColor("#2f3338")

        painter.setPen(QPen(border, 1))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(rect, 10, 10)

        painter.setPen(QPen(QColor("#d6d6d6")))
        text_rect = rect.adjusted(16, 0, -28, 0)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self._text)

        chevron_x = rect.right() - 14
        chevron_y = rect.center().y()
        painter.setPen(QPen(QColor("#9ca3af"), 1.5))
        painter.drawLine(chevron_x - 5, chevron_y - 2, chevron_x, chevron_y + 3)
        painter.drawLine(chevron_x, chevron_y + 3, chevron_x + 5, chevron_y - 2)


class PopupPanel(QFrame):
    selection_changed = Signal(object)
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
        self.selected_value = None

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

        self.setStyleSheet(
            """
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
            """
        )
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

    def set_options(self, options, selected_value=None) -> None:
        self.selected_value = selected_value
        self.items.clear()

        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for option in options:
            text, value = PrimeSelect.normalize_option(option)
            item_widget = SelectItem(text, value, value == self.selected_value)
            item_widget.selected.connect(self.on_item_selected)
            self.items.append(item_widget)
            self.content_layout.addWidget(item_widget)

        self.content_layout.addStretch()

    def on_item_selected(self, value) -> None:
        self.selected_value = value
        for item in self.items:
            item.set_checked(item.value == value)
        self.selection_changed.emit(value)

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


class PrimeSelect(QWidget):
    selection_changed = Signal(object)
    value_changed = Signal(object)

    def __init__(self, options=None, placeholder="Select", parent=None):
        super().__init__(parent)
        self.setObjectName("primeSelect")
        self.options = list(options or [])
        self.selected_value = None
        self.placeholder = placeholder

        self.setMinimumWidth(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.button = SelectTrigger()
        self.button.clicked.connect(self.toggle_popup)
        layout.addWidget(self.button)

        self.popup = PopupPanel(self)
        self.popup.selection_changed.connect(self.sync_from_popup)

        self.setStyleSheet(
            """
            QWidget#primeSelect {
                background: transparent;
                color: #e5e7eb;
                font-size: 14px;
            }
            """
        )

        self.refresh_label()

    @staticmethod
    def normalize_option(option):
        if isinstance(option, dict):
            return str(option.get("label", "")), option.get("value")
        return str(option), option

    def set_options(self, options) -> None:
        self.options = list(options or [])
        valid_values = {self.normalize_option(option)[1] for option in self.options}
        if self.selected_value not in valid_values:
            self.selected_value = None
        self.refresh_label()

    def set_value(self, value) -> None:
        valid_values = {self.normalize_option(option)[1] for option in self.options}
        self.selected_value = value if value in valid_values else None
        self.refresh_label()

    def clear(self) -> None:
        self.selected_value = None
        self.refresh_label()
        self.selection_changed.emit(self.selected_value)
        self.value_changed.emit(self.selected_value)

    def value(self):
        return self.selected_value

    def refresh_label(self) -> None:
        text = self.placeholder
        for option in self.options:
            label, value = self.normalize_option(option)
            if value == self.selected_value:
                text = label
                break

        self.button.set_text(text)

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

    def toggle_popup(self) -> None:
        if self.popup.isVisible():
            self.popup.hide()
            return

        self.popup.set_options(self.options, self.selected_value)
        screen_rect = self._popup_screen_geometry()
        popup_width = self.button.width() or self.width() or 180
        popup_height = self.popup.preferred_height()
        if screen_rect is not None:
            popup_width = min(popup_width, screen_rect.width())
            popup_height = min(popup_height, screen_rect.height())

        self.popup.resize(popup_width, popup_height)
        self.popup.move(self._popup_position(popup_width, popup_height))
        self.popup.show()

    def sync_from_popup(self, value) -> None:
        self.selected_value = value
        self.refresh_label()
        self.popup.hide()
        self.selection_changed.emit(self.selected_value)
        self.value_changed.emit(self.selected_value)


class SelectWidget(PrimeSelect):
    pass


class Demo(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Prime Style Select - PySide6")
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

        self.select = PrimeSelect(options=options, placeholder="Select Camera")
        self.select.value_changed.connect(self.on_change)

        self.info = QLabel("Selected: None")
        self.info.setStyleSheet(
            """
            QLabel {
                color: #d1d5db;
                padding-top: 12px;
                font-size: 13px;
            }
            """
        )

        layout.addWidget(self.select)
        layout.addWidget(self.info)
        layout.addStretch()

    def on_change(self, value) -> None:
        self.info.setText(f"Selected: {value}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Demo()
    window.show()
    sys.exit(app.exec())
