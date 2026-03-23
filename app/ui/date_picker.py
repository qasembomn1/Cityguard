import os
import sys
from collections.abc import Mapping, Sequence

from PySide6.QtCore import QDate, QDateTime, QPoint, QRect, QSize, QTime, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

if __package__ in (None, ""):
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from app.ui.calendar import PrimeCalendar


def _copy_time(value: QTime) -> QTime:
    return QTime(value.hour(), value.minute(), value.second(), value.msec())


def _normalize_time_value(value: QTime | str | None) -> QTime | None:
    if isinstance(value, QTime):
        return _copy_time(value) if value.isValid() else None

    text = str(value or "").strip()
    if not text:
        return None

    for fmt in ("HH:mm:ss", "HH:mm", "hh:mm AP", "hh:mm ap"):
        parsed = QTime.fromString(text, fmt)
        if parsed.isValid():
            return parsed

    parsed = QTime.fromString(text, Qt.DateFormat.ISODate)
    return parsed if parsed.isValid() else None


def _time_format_uses_meridiem(value: str) -> bool:
    return "AP" in value or "ap" in value


def _time_format_uses_seconds(value: str) -> bool:
    return "s" in value


def _time_format_meridiem_token(value: str) -> str:
    return "ap" if "ap" in value else "AP"


class _TimeWheelColumn(QFrame):
    value_changed = Signal(object)

    def __init__(self, values: Sequence[tuple[str, object]], parent=None) -> None:
        super().__init__(parent)
        self._values: list[tuple[str, object]] = list(values)
        self._index = 0
        self.setObjectName("primeTimeColumn")
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.up_button = QPushButton("⌃", self)
        self.up_button.setObjectName("primeTimeStepperButton")
        self.up_button.clicked.connect(lambda: self._step(1))
        layout.addWidget(self.up_button, 0, Qt.AlignmentFlag.AlignCenter)

        self.value_label = QLabel("--", self)
        self.value_label.setObjectName("primeTimeValue")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.value_label, 0, Qt.AlignmentFlag.AlignCenter)

        self.down_button = QPushButton("⌄", self)
        self.down_button.setObjectName("primeTimeStepperButton")
        self.down_button.clicked.connect(lambda: self._step(-1))
        layout.addWidget(self.down_button, 0, Qt.AlignmentFlag.AlignCenter)

        self._sync_label()

    def value(self) -> object:
        if not self._values:
            return None
        return self._values[self._index][1]

    def set_values(self, values: Sequence[tuple[str, object]]) -> None:
        current = self.value()
        self._values = list(values)
        self._index = 0
        self.set_value(current, emit_signal=False)
        self._sync_label()

    def set_value(self, value: object, emit_signal: bool = False) -> None:
        if not self._values:
            self._index = 0
            self._sync_label()
            return
        for index, (_, current_value) in enumerate(self._values):
            if current_value == value:
                self._index = index
                self._sync_label()
                if emit_signal:
                    self.value_changed.emit(self.value())
                return
        self._index = 0
        self._sync_label()

    def _step(self, delta: int) -> None:
        if not self._values:
            return
        self._index = (self._index + delta) % len(self._values)
        self._sync_label()
        self.value_changed.emit(self.value())

    def _sync_label(self) -> None:
        if not self._values:
            self.value_label.setText("--")
            return
        self.value_label.setText(str(self._values[self._index][0]))


class _TimeSelector(QWidget):
    time_changed = Signal(QTime)

    def __init__(self, parent=None, display_format: str = "HH:mm") -> None:
        super().__init__(parent)
        self.setObjectName("primeTimeSelector")
        self._display_format = display_format or "HH:mm"
        self._uses_meridiem = False
        self._uses_seconds = False
        self._meridiem_token = "AP"
        self._hour_column: _TimeWheelColumn | None = None
        self._minute_column: _TimeWheelColumn | None = None
        self._second_column: _TimeWheelColumn | None = None
        self._meridiem_column: _TimeWheelColumn | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout = layout

        self.set_display_format(self._display_format)
        self.set_time(QTime.currentTime())

    def time(self) -> QTime:
        hour_value = int(self._hour_column.value() or 0) if self._hour_column is not None else 0
        minute_value = int(self._minute_column.value() or 0) if self._minute_column is not None else 0
        second_value = int(self._second_column.value() or 0) if self._second_column is not None else 0

        if self._uses_meridiem:
            meridiem = str(self._meridiem_column.value() or "AM").upper()
            if hour_value == 12:
                hour_value = 0 if meridiem == "AM" else 12
            elif meridiem == "PM":
                hour_value += 12

        return QTime(hour_value, minute_value, second_value)

    def set_time(self, value: QTime | str | None, emit_signal: bool = False) -> None:
        normalized = _normalize_time_value(value)
        if normalized is None or not normalized.isValid():
            return

        if self._uses_meridiem:
            display_hour = normalized.hour() % 12
            if display_hour == 0:
                display_hour = 12
            meridiem = "AM" if normalized.hour() < 12 else "PM"
            if self._meridiem_token == "ap":
                meridiem = meridiem.lower()
            if self._meridiem_column is not None:
                self._meridiem_column.set_value(meridiem, emit_signal=False)
            if self._hour_column is not None:
                self._hour_column.set_value(display_hour, emit_signal=False)
        elif self._hour_column is not None:
            self._hour_column.set_value(normalized.hour(), emit_signal=False)

        if self._minute_column is not None:
            self._minute_column.set_value(normalized.minute(), emit_signal=False)
        if self._second_column is not None:
            self._second_column.set_value(normalized.second(), emit_signal=False)

        if emit_signal:
            self.time_changed.emit(self.time())

    def set_display_format(self, value: str) -> None:
        current_time = self.time() if self._hour_column is not None else QTime.currentTime()
        self._display_format = value or "HH:mm"
        self._uses_meridiem = _time_format_uses_meridiem(self._display_format)
        self._uses_seconds = _time_format_uses_seconds(self._display_format)
        self._meridiem_token = _time_format_meridiem_token(self._display_format)
        self._rebuild_columns()
        self.set_time(current_time, emit_signal=False)

    def _rebuild_columns(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._hour_column = self._build_column(
            [(f"{value:02d}", value) for value in (range(1, 13) if self._uses_meridiem else range(24))]
        )
        self._layout.addWidget(self._hour_column)

        self._layout.addWidget(self._separator(":"))

        self._minute_column = self._build_column([(f"{value:02d}", value) for value in range(60)])
        self._layout.addWidget(self._minute_column)

        self._second_column = None
        if self._uses_seconds:
            self._layout.addWidget(self._separator(":"))
            self._second_column = self._build_column([(f"{value:02d}", value) for value in range(60)])
            self._layout.addWidget(self._second_column)

        self._meridiem_column = None
        if self._uses_meridiem:
            self._layout.addSpacing(4)
            meridiem_values = [("AM", "AM"), ("PM", "PM")]
            if self._meridiem_token == "ap":
                meridiem_values = [("am", "am"), ("pm", "pm")]
            self._meridiem_column = self._build_column(meridiem_values)
            self._layout.addWidget(self._meridiem_column)

    def _build_column(self, values: Sequence[tuple[str, object]]) -> _TimeWheelColumn:
        column = _TimeWheelColumn(values, self)
        column.value_changed.connect(lambda _value: self.time_changed.emit(self.time()))
        return column

    def _separator(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("primeTimeSeparator")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label


class _DatePickerTrigger(QFrame):
    clicked = Signal()
    _height = 40

    def __init__(
        self,
        parent=None,
        radius: int = 10,
        icon: QIcon | str | None = None,
        icon_size: int = 16,
        icon_padding_left: int = 14,
    ) -> None:
        super().__init__(parent)
        self._radius = radius
        self._text = ""
        self._placeholder = "Select date"
        self._hovered = False
        self._active = False
        self._error = False
        self._icon = self._normalize_icon(icon)
        self._icon_size = max(12, icon_size)
        self._icon_padding_left = max(0, icon_padding_left)
        self._icon_color = QColor("#9ca3af")
        self._icon_active_color = QColor("#d6d6d6")
        self._chevron_color = QColor("#9ca3af")
        self._chevron_active_color = QColor("#d6d6d6")

        self.setFixedHeight(self._height)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    @staticmethod
    def _normalize_icon(icon: QIcon | str | None) -> QIcon | None:
        if isinstance(icon, QIcon):
            return icon
        if isinstance(icon, str) and icon.strip():
            return QIcon(icon)
        return None

    def set_text(self, text: str) -> None:
        self._text = text
        self.update()

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        self.update()

    def set_error(self, enabled: bool) -> None:
        self._error = enabled
        self.update()

    def set_active(self, enabled: bool) -> None:
        self._active = enabled
        self.update()

    def set_radius(self, value: int) -> None:
        self._radius = max(0, value)
        self.update()

    def set_icon(self, icon: QIcon | str | None) -> None:
        self._icon = self._normalize_icon(icon)
        self.update()

    def set_icon_size(self, value: int) -> None:
        self._icon_size = max(12, value)
        self.update()

    def set_icon_padding_left(self, value: int) -> None:
        self._icon_padding_left = max(0, value)
        self.update()

    def set_icon_color(self, value: str | QColor) -> None:
        self._icon_color = QColor(value)
        self.update()

    def set_active_icon_color(self, value: str | QColor) -> None:
        self._icon_active_color = QColor(value)
        self.update()

    def set_chevron_color(self, value: str | QColor) -> None:
        self._chevron_color = QColor(value)
        self.update()

    def set_active_chevron_color(self, value: str | QColor) -> None:
        self._chevron_active_color = QColor(value)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(180, self._height)

    def minimumSizeHint(self) -> QSize:
        return QSize(120, self._height)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(0, 0, -1, -1)
        bg = QColor("#30343a") if (self._hovered or self._active) else QColor("#2a2d31")
        border = QColor("#ff6b81") if self._error else QColor(
            "#1456be" if self._active else "#3a3f45" if self._hovered else "#2f3338"
        )

        painter.setPen(QPen(border, 1))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(rect, self._radius, self._radius)

        self._draw_calendar_icon(painter, rect)

        display_text = self._text or self._placeholder
        text_color = QColor("#e5e7eb" if self._text else "#9ca3af")
        painter.setPen(QPen(text_color))
        text_left = self._icon_padding_left + self._icon_size + 12
        text_rect = rect.adjusted(text_left, 0, -28, 0)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, display_text)

        chevron_x = rect.right() - 14
        chevron_y = rect.center().y()
        painter.setPen(
            QPen(self._chevron_active_color if self._active else self._chevron_color, 1.5)
        )
        painter.drawLine(chevron_x - 5, chevron_y - 2, chevron_x, chevron_y + 3)
        painter.drawLine(chevron_x, chevron_y + 3, chevron_x + 5, chevron_y - 2)

    def _draw_calendar_icon(self, painter: QPainter, rect: QRect) -> None:
        icon_rect = QRect(
            rect.x() + self._icon_padding_left,
            rect.center().y() - (self._icon_size // 2),
            self._icon_size,
            self._icon_size,
        )
        if self._icon is not None and not self._icon.isNull():
            self._icon.paint(
                painter,
                icon_rect,
                Qt.AlignmentFlag.AlignCenter,
                QIcon.Mode.Normal,
                QIcon.State.Off,
            )
            return

        icon_pen = QPen(
            self._icon_active_color if self._active else self._icon_color,
            1.4,
        )
        painter.setPen(icon_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(icon_rect, 3, 3)
        painter.drawLine(
            icon_rect.left(),
            icon_rect.top() + 5,
            icon_rect.right(),
            icon_rect.top() + 5,
        )
        painter.drawLine(
            icon_rect.left() + 4,
            icon_rect.top() - 1,
            icon_rect.left() + 4,
            icon_rect.top() + 3,
        )
        painter.drawLine(
            icon_rect.right() - 4,
            icon_rect.top() - 1,
            icon_rect.right() - 4,
            icon_rect.top() + 3,
        )


class _CalendarPopup(QFrame):
    selection_applied = Signal(QDateTime)
    popup_closed = Signal()

    def __init__(
        self,
        parent=None,
        radius: int = 10,
        minimum_popup_height: int | None = None,
        disabled_dates: Sequence[QDate | str] | None = None,
        day_text_colors: Mapping[str, str | QColor] | None = None,
        day_background_colors: Mapping[str, str | QColor] | None = None,
        day_border_colors: Mapping[str, str | QColor] | None = None,
        day_radius: int = 8,
        full_circle_dates: bool = True,
        weekday_header_text_color: str | QColor = "#94a3b8",
        weekday_header_weekend_text_color: str | QColor = "#cbd5e1",
        navigation_prev_icon: QIcon | str | None = "‹",
        navigation_next_icon: QIcon | str | None = "›",
        navigation_icon_color: str | QColor = "#f5f5f5",
        navigation_hover_background: str | QColor = "#2a2d31",
        navigation_icon_padding: int = 7,
        include_time: bool = False,
        time_display_format: str = "HH:mm",
    ) -> None:
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("primeDatePickerPopup")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self._include_time = bool(include_time)
        self._radius = max(0, radius)
        self._time_display_format = time_display_format or "HH:mm"
        self._minimum_popup_height = (
            max(0, int(minimum_popup_height))
            if minimum_popup_height is not None
            else (430 if self._include_time else 380)
        )
        self._panel: QFrame | None = None
        self._time_selector: _TimeSelector | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        container_layout = layout
        container_parent: QWidget = self
        if self._include_time:
            self._panel = QFrame(self)
            self._panel.setObjectName("primeDateTimePickerPanel")
            self._panel.setStyleSheet(self._build_stylesheet())
            panel_layout = QVBoxLayout(self._panel)
            panel_layout.setContentsMargins(12, 12, 12, 12)
            panel_layout.setSpacing(12)
            layout.addWidget(self._panel)
            container_layout = panel_layout
            container_parent = self._panel

        self.calendar_panel = PrimeCalendar(
            container_parent,
            radius=self._radius,
            framed=not self._include_time,
            disabled_dates=disabled_dates,
            day_text_colors=day_text_colors,
            day_background_colors=day_background_colors,
            day_border_colors=day_border_colors,
            day_radius=day_radius,
            full_circle_dates=full_circle_dates,
            weekday_header_text_color=weekday_header_text_color,
            weekday_header_weekend_text_color=weekday_header_weekend_text_color,
            navigation_prev_icon=navigation_prev_icon,
            navigation_next_icon=navigation_next_icon,
            navigation_icon_color=navigation_icon_color,
            navigation_hover_background=navigation_hover_background,
            navigation_icon_padding=navigation_icon_padding,
        )
        self.calendar_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        container_layout.addWidget(self.calendar_panel)

        if self._include_time:
            time_block = QVBoxLayout()
            time_block.setContentsMargins(0, 0, 0, 0)
            time_block.setSpacing(8)
            container_layout.addLayout(time_block)

            time_label = QLabel("Time", container_parent)
            time_label.setObjectName("primeDatePickerTimeLabel")
            time_block.addWidget(time_label, 0, Qt.AlignmentFlag.AlignCenter)

            self._time_selector = _TimeSelector(container_parent, display_format=self._time_display_format)
            time_block.addWidget(self._time_selector, 0, Qt.AlignmentFlag.AlignCenter)

            actions = QHBoxLayout()
            actions.setContentsMargins(0, 0, 0, 0)
            actions.setSpacing(8)
            actions.addStretch(1)
            container_layout.addLayout(actions)

            apply_button = QPushButton("Apply", container_parent)
            apply_button.setObjectName("primeDatePickerApplyButton")
            apply_button.clicked.connect(self._apply_selection)
            actions.addWidget(apply_button)
        else:
            self.calendar_panel.date_selected.connect(self._on_date_selected)

    def _build_stylesheet(self) -> str:
        return f"""
            QFrame#primeDateTimePickerPanel {{
                background-color: #1b1c1f;
                border: 1px solid #101114;
                border-radius: {self._radius}px;
            }}
            QLabel#primeDatePickerTimeLabel {{
                color: #cbd5e1;
                font-size: 12px;
                font-weight: 700;
            }}
            QWidget#primeTimeSelector {{
                background: transparent;
            }}
            QFrame#primeTimeColumn {{
                background: transparent;
                border: none;
            }}
            QPushButton#primeTimeStepperButton {{
                min-width: 34px;
                max-width: 34px;
                min-height: 26px;
                max-height: 26px;
                border: none;
                border-radius: 8px;
                background: transparent;
                color: #a8b4c7;
                font-size: 15px;
                font-weight: 700;
                padding: 0;
            }}
            QPushButton#primeTimeStepperButton:hover {{
                background: rgba(59, 130, 246, 0.16);
                color: #f8fafc;
            }}
            QLabel#primeTimeValue {{
                color: #f8fafc;
                font-size: 20px;
                font-weight: 800;
                min-width: 36px;
                padding: 0 4px;
            }}
            QLabel#primeTimeSeparator {{
                color: #94a3b8;
                font-size: 20px;
                font-weight: 700;
            }}
            QPushButton#primeDatePickerApplyButton {{
                min-height: 36px;
                border: none;
                border-radius: 10px;
                padding: 0 16px;
                font-weight: 700;
                color: #f8fafc;
                background: #1456be;
            }}
            QPushButton#primeDatePickerApplyButton:hover {{
                background: #1d4ed8;
            }}
        """

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(hint.width(), max(hint.height(), self._minimum_popup_height))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def set_minimum_popup_height(self, value: int) -> None:
        self._minimum_popup_height = max(0, int(value))
        self.updateGeometry()

    def selected_date(self) -> QDate:
        return self.calendar_panel.selected_date()

    def set_selected_date(self, value: QDate) -> None:
        self.calendar_panel.set_selected_date(value)

    def selected_time(self) -> QTime:
        if self._time_selector is None:
            return QTime(0, 0)
        return _copy_time(self._time_selector.time())

    def set_time(self, value: QTime | str | None) -> None:
        if self._time_selector is None:
            return
        normalized = _normalize_time_value(value)
        if normalized is None:
            return
        self._time_selector.set_time(normalized)

    def selected_date_time(self) -> QDateTime:
        return QDateTime(self.selected_date(), self.selected_time())

    def set_selected_date_time(self, value: QDateTime | None) -> None:
        if value is None or not value.isValid():
            return
        self.set_selected_date(value.date())
        if self._include_time:
            self.set_time(value.time())

    def set_minimum_date(self, value: QDate) -> None:
        self.calendar_panel.set_minimum_date(value)

    def set_maximum_date(self, value: QDate) -> None:
        self.calendar_panel.set_maximum_date(value)

    def set_disabled_dates(self, values: Sequence[QDate | str] | None) -> None:
        self.calendar_panel.set_disabled_dates(values)

    def add_disabled_date(self, value: QDate | str) -> None:
        self.calendar_panel.add_disabled_date(value)

    def remove_disabled_date(self, value: QDate | str) -> None:
        self.calendar_panel.remove_disabled_date(value)

    def clear_disabled_dates(self) -> None:
        self.calendar_panel.clear_disabled_dates()

    def disabled_dates(self) -> list[QDate]:
        return self.calendar_panel.disabled_dates()

    def is_date_disabled(self, value: QDate | str | None) -> bool:
        return self.calendar_panel.is_date_disabled(value)

    def set_title(self, value: str) -> None:
        return None

    def set_radius(self, value: int) -> None:
        self._radius = max(0, value)
        self.calendar_panel.set_radius(self._radius)
        if self._panel is not None:
            self._panel.setStyleSheet(self._build_stylesheet())

    def set_day_text_colors(self, values: Mapping[str, str | QColor]) -> None:
        self.calendar_panel.set_day_text_colors(values)

    def set_day_background_colors(self, values: Mapping[str, str | QColor]) -> None:
        self.calendar_panel.set_day_background_colors(values)

    def set_day_border_colors(self, values: Mapping[str, str | QColor]) -> None:
        self.calendar_panel.set_day_border_colors(values)

    def set_day_radius(self, value: int) -> None:
        self.calendar_panel.set_day_radius(value)

    def set_time_display_format(self, value: str) -> None:
        self._time_display_format = value or "HH:mm"
        if self._time_selector is not None:
            self._time_selector.set_display_format(self._time_display_format)

    def _apply_selection(self) -> None:
        if self.calendar_panel.is_date_disabled(self.selected_date()):
            return
        self.selection_applied.emit(self.selected_date_time())
        self.hide()

    def _on_date_selected(self, value: QDate) -> None:
        if self.calendar_panel.is_date_disabled(value):
            return
        self._apply_selection()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.popup_closed.emit()


class PrimeDatePicker(QWidget):
    date_changed = Signal(QDate)
    date_time_changed = Signal(QDateTime)

    def __init__(
        self,
        parent=None,
        placeholder: str = "Select date",
        display_format: str | None = None,
        radius: int = 10,
        popup_radius: int | None = None,
        minimum_popup_height: int | None = None,
        value: QDate | QDateTime | str | None = None,
        icon: QIcon | str | None = None,
        icon_size: int = 16,
        disabled_dates: Sequence[QDate | str] | None = None,
        day_text_colors: Mapping[str, str | QColor] | None = None,
        day_background_colors: Mapping[str, str | QColor] | None = None,
        day_border_colors: Mapping[str, str | QColor] | None = None,
        day_radius: int = 8,
        full_circle_dates: bool = True,
        weekday_header_text_color: str | QColor = "#94a3b8",
        weekday_header_weekend_text_color: str | QColor = "#cbd5e1",
        navigation_prev_icon: QIcon | str | None = "‹",
        navigation_next_icon: QIcon | str | None = "›",
        navigation_icon_color: str | QColor = "#f5f5f5",
        navigation_hover_background: str | QColor = "#2a2d31",
        navigation_icon_padding: int = 7,
        icon_padding_left: int = 14,
        include_time: bool = False,
        time_display_format: str = "HH:mm",
    ) -> None:
        super().__init__(parent)
        self._radius = radius
        self._popup_radius = max(0, popup_radius if popup_radius is not None else radius)
        self._include_time = bool(include_time)
        self._time_display_format = time_display_format or "HH:mm"
        self._display_format = display_format or (
            f"yyyy-MM-dd {self._time_display_format}" if self._include_time else "yyyy-MM-dd"
        )
        self._placeholder = placeholder
        self._error = False
        self._value: QDateTime | None = None
        self._popup_title: str | None = None

        self.setMinimumWidth(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.trigger = _DatePickerTrigger(
            self,
            radius=radius,
            icon=icon,
            icon_size=icon_size,
            icon_padding_left=icon_padding_left,
        )
        self.trigger.set_placeholder(placeholder)
        self.trigger.clicked.connect(self.toggle_popup)
        layout.addWidget(self.trigger)

        self.popup = _CalendarPopup(
            self,
            radius=self._popup_radius,
            minimum_popup_height=minimum_popup_height,
            disabled_dates=disabled_dates,
            day_text_colors=day_text_colors,
            day_background_colors=day_background_colors,
            day_border_colors=day_border_colors,
            day_radius=day_radius,
            full_circle_dates=full_circle_dates,
            weekday_header_text_color=weekday_header_text_color,
            weekday_header_weekend_text_color=weekday_header_weekend_text_color,
            navigation_prev_icon=navigation_prev_icon,
            navigation_next_icon=navigation_next_icon,
            navigation_icon_color=navigation_icon_color,
            navigation_hover_background=navigation_hover_background,
            navigation_icon_padding=navigation_icon_padding,
            include_time=self._include_time,
            time_display_format=self._time_display_format,
        )
        self.popup.selection_applied.connect(self._on_popup_selection_applied)
        self.popup.popup_closed.connect(self._on_popup_closed)

        self.set_date(value)

    def _format_has_time_tokens(self, value: str) -> bool:
        return any(token in value for token in ("H", "h", "m", "s"))

    def _default_time(self) -> QTime:
        if self._value is not None and self._value.isValid():
            return _copy_time(self._value.time())
        popup_time = self.popup.selected_time()
        if popup_time.isValid():
            return popup_time
        now = QTime.currentTime()
        return QTime(now.hour(), now.minute(), 0)

    def _compose_value(self, date: QDate | None, time: QTime | None = None) -> QDateTime | None:
        if not isinstance(date, QDate) or not date.isValid():
            return None
        if self._include_time:
            normalized_time = (
                _copy_time(time) if isinstance(time, QTime) and time.isValid() else self._default_time()
            )
        else:
            normalized_time = QTime(0, 0)
        return QDateTime(date, normalized_time)

    def _normalize_value(self, value: QDate | QDateTime | str | None) -> QDateTime | None:
        if isinstance(value, QDateTime):
            if not value.isValid():
                return None
            return self._compose_value(value.date(), value.time())

        if isinstance(value, QDate):
            return self._compose_value(value)

        text = str(value or "").strip()
        if not text:
            return None

        parsed_date_time = QDateTime.fromString(text, Qt.DateFormat.ISODate)
        if parsed_date_time.isValid():
            return self._compose_value(parsed_date_time.date(), parsed_date_time.time())

        cleaned = text.replace("T", " ")
        for fmt in (self._display_format, "yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd HH:mm"):
            if not fmt:
                continue
            parsed_date_time = QDateTime.fromString(cleaned, fmt)
            if parsed_date_time.isValid():
                return self._compose_value(parsed_date_time.date(), parsed_date_time.time())

        date_text = cleaned.split(" ", 1)[0]
        date_formats = ["yyyy-MM-dd"]
        if self._display_format and not self._format_has_time_tokens(self._display_format):
            date_formats.insert(0, self._display_format)

        for fmt in date_formats:
            parsed_date = QDate.fromString(date_text, fmt)
            if parsed_date.isValid():
                return self._compose_value(parsed_date)

        parsed_date = QDate.fromString(date_text, Qt.DateFormat.ISODate)
        if parsed_date.isValid():
            return self._compose_value(parsed_date)
        return None

    def _update_trigger(self) -> None:
        display_text = self._value.toString(self._display_format) if self._value is not None else ""
        self.trigger.set_text(display_text)
        self.trigger.set_placeholder(self._placeholder)
        self.trigger.set_error(self._error)

    def _popup_position(self) -> QPoint:
        popup_size = self.popup.sizeHint()
        popup_width = max(self.width(), popup_size.width())
        popup_height = popup_size.height()
        top_left = self.mapToGlobal(QPoint(0, self.height() + 6))
        screen = QApplication.screenAt(top_left) or QApplication.primaryScreen()

        if screen is None:
            self.popup.resize(popup_width, popup_height)
            return top_left

        available = screen.availableGeometry()
        x = max(
            available.left(),
            min(top_left.x(), available.right() - popup_width + 1),
        )
        y = top_left.y()
        if y + popup_height - 1 > available.bottom():
            above = self.mapToGlobal(QPoint(0, -popup_height - 6))
            y = max(available.top(), above.y())

        self.popup.resize(popup_width, popup_height)
        return QPoint(x, y)

    def toggle_popup(self) -> None:
        if self.popup.isVisible():
            self.popup.hide()
            return

        popup_value = self._value or self._compose_value(QDate.currentDate())
        if popup_value is not None:
            self.popup.set_selected_date_time(popup_value)
        self.popup.set_title(self._popup_title or self._placeholder or "Select date")
        self.popup.move(self._popup_position())
        self.popup.show()
        self.popup.raise_()
        self.popup.activateWindow()
        self.trigger.set_active(True)

    def _on_popup_selection_applied(self, value: QDateTime) -> None:
        self._value = value if value.isValid() else None
        self._update_trigger()
        if self._value is not None:
            self.date_changed.emit(self._value.date())
            self.date_time_changed.emit(self._value)

    def _on_popup_closed(self) -> None:
        self.trigger.set_active(False)

    def date(self) -> QDate | None:
        return self._value.date() if self._value is not None else None

    def date_time(self) -> QDateTime | None:
        return self._value

    def time(self) -> QTime | None:
        if not self._include_time or self._value is None:
            return None
        return _copy_time(self._value.time())

    def set_date(self, value: QDate | QDateTime | str | None) -> None:
        self._value = self._normalize_value(value)
        if self._value is not None:
            self.popup.set_selected_date_time(self._value)
        self._update_trigger()

    def set_date_time(self, value: QDateTime | str | None) -> None:
        self.set_date(value)

    def set_time(self, value: QTime | str | None) -> None:
        if not self._include_time:
            return
        normalized = _normalize_time_value(value)
        if normalized is None:
            return
        self.popup.set_time(normalized)
        if self._value is not None:
            self._value = QDateTime(self._value.date(), normalized)
            self._update_trigger()

    def clear(self) -> None:
        self._value = None
        self._update_trigger()

    def text(self) -> str:
        return self._value.toString(self._display_format) if self._value else ""

    def set_placeholder_text(self, text: str) -> None:
        self._placeholder = text
        self._update_trigger()

    def set_popup_title(self, value: str | None) -> None:
        self._popup_title = str(value).strip() if value is not None else None
        self.popup.set_title(self._popup_title or self._placeholder or "Select date")

    def set_display_format(self, value: str) -> None:
        self._display_format = value
        self._update_trigger()

    def set_time_display_format(self, value: str) -> None:
        self._time_display_format = value or "HH:mm"
        self.popup.set_time_display_format(self._time_display_format)

    def set_error(self, enabled: bool = True) -> None:
        self._error = enabled
        self._update_trigger()

    def clear_error(self) -> None:
        self.set_error(False)

    def set_radius(self, value: int) -> None:
        self._radius = max(0, value)
        self.trigger.set_radius(self._radius)

    def set_popup_radius(self, value: int) -> None:
        self._popup_radius = max(0, value)
        self.popup.set_radius(self._popup_radius)

    def set_minimum_popup_height(self, value: int) -> None:
        self.popup.set_minimum_popup_height(value)

    def set_day_text_colors(self, values: Mapping[str, str | QColor]) -> None:
        self.popup.set_day_text_colors(values)

    def set_day_background_colors(self, values: Mapping[str, str | QColor]) -> None:
        self.popup.set_day_background_colors(values)

    def set_day_border_colors(self, values: Mapping[str, str | QColor]) -> None:
        self.popup.set_day_border_colors(values)

    def set_day_radius(self, value: int) -> None:
        self.popup.set_day_radius(value)

    def set_full_circle_dates(self, enabled: bool) -> None:
        self.popup.calendar_panel.set_full_circle_dates(enabled)

    def set_weekday_header_colors(
        self,
        default: str | QColor,
        weekend: str | QColor | None = None,
    ) -> None:
        self.popup.calendar_panel.set_weekday_header_colors(default, weekend)

    def set_navigation_icons(
        self,
        previous: QIcon | str | None = None,
        next_: QIcon | str | None = None,
    ) -> None:
        self.popup.calendar_panel.set_navigation_icons(previous, next_)

    def set_navigation_style(
        self,
        icon_color: str | QColor | None = None,
        hover_background: str | QColor | None = None,
    ) -> None:
        self.popup.calendar_panel.set_navigation_style(icon_color, hover_background)

    def set_navigation_icon_padding(self, value: int) -> None:
        self.popup.calendar_panel.set_navigation_icon_padding(value)

    def set_icon(self, icon: QIcon | str | None) -> None:
        self.trigger.set_icon(icon)

    def set_icon_size(self, value: int) -> None:
        self.trigger.set_icon_size(value)

    def set_icon_padding_left(self, value: int) -> None:
        self.trigger.set_icon_padding_left(value)

    def set_icon_color(self, value: str | QColor) -> None:
        self.trigger.set_icon_color(value)

    def set_active_icon_color(self, value: str | QColor) -> None:
        self.trigger.set_active_icon_color(value)

    def set_chevron_color(self, value: str | QColor) -> None:
        self.trigger.set_chevron_color(value)

    def set_active_chevron_color(self, value: str | QColor) -> None:
        self.trigger.set_active_chevron_color(value)

    def disabled_dates(self) -> list[QDate]:
        return self.popup.disabled_dates()

    def set_disabled_dates(self, values: Sequence[QDate | str] | None) -> None:
        self.popup.set_disabled_dates(values)

    def add_disabled_date(self, value: QDate | str) -> None:
        self.popup.add_disabled_date(value)

    def remove_disabled_date(self, value: QDate | str) -> None:
        self.popup.remove_disabled_date(value)

    def clear_disabled_dates(self) -> None:
        self.popup.clear_disabled_dates()

    def is_date_disabled(self, value: QDate | str | None) -> bool:
        return self.popup.is_date_disabled(value)

    def set_minimum_date(self, value: QDate) -> None:
        self.popup.set_minimum_date(value)

    def set_maximum_date(self, value: QDate) -> None:
        self.popup.set_maximum_date(value)


class DemoWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("PrimeDatePicker Demo")
        self.setMinimumSize(420, 240)
        self.setStyleSheet("background-color: #1e1e21;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        self.status_label = QLabel("Selected value: --")
        self.status_label.setStyleSheet("color: #eef2f8; font-size: 13px;")
        layout.addWidget(self.status_label)

        self.date_picker = PrimeDatePicker(
            value=QDateTime.currentDateTime(),
            radius=12,
            popup_radius=18,
            icon_size=18,
            disabled_dates=[
                QDate.currentDate().addDays(1),
                QDate.currentDate().addDays(2),
            ],
            day_text_colors={
                "default": "#f8fafc",
                "weekend": "#fde68a",
                "disabled": "#6b7280",
            },
            day_background_colors={
                "today": "#1456be",
                "selected": "#f8fafc",
                "disabled": "rgba(255, 255, 255, 0.04)",
            },
            day_border_colors={
                "today": "#60a5fa",
                "disabled": "rgba(148, 163, 184, 0.18)",
            },
            day_radius=12,
            full_circle_dates=True,
            weekday_header_text_color="#94a3b8",
            weekday_header_weekend_text_color="#e2e8f0",
            navigation_prev_icon="‹",
            navigation_next_icon="›",
            navigation_icon_padding=8,
            icon_padding_left=16,
            include_time=True,
            time_display_format="hh:mm AP",
        )
        self.date_picker.date_time_changed.connect(self._update_status)
        layout.addWidget(self.date_picker)

        self._update_status(self.date_picker.date_time() or QDateTime.currentDateTime())

    def _update_status(self, value: QDateTime) -> None:
        self.status_label.setText(f"Selected value: {value.toString('yyyy-MM-dd hh:mm AP')}")


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = DemoWindow()
    window.show()

    sys.exit(app.exec())
