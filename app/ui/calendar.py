import os
import sys
from collections.abc import Mapping, Sequence

from PySide6.QtCore import QDate, QLocale, QRectF, QSignalBlocker, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPen, QTextCharFormat
from PySide6.QtWidgets import (
    QApplication,
    QCalendarWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.input import PrimeInput
from app.ui.select import PrimeSelect

_DAY_STATES = (
    "default",
    "outside_month",
    "weekend",
    "today",
    "selected",
    "disabled",
)

_DEFAULT_DAY_TEXT_COLORS = {
    "default": "#f5f5f5",
    "outside_month": "#6b7280",
    "weekend": "#dbeafe",
    "today": "#ffffff",
    "selected": "#111111",
    "disabled": "#4b5563",
}

_DEFAULT_DAY_BACKGROUND_COLORS = {
    "default": "transparent",
    "outside_month": "transparent",
    "weekend": "transparent",
    "today": "#1456be",
    "selected": "#e7e7e7",
    "disabled": "rgba(255, 255, 255, 0.03)",
}

_DEFAULT_DAY_BORDER_COLORS = {
    "default": "transparent",
    "outside_month": "transparent",
    "weekend": "transparent",
    "today": "#3b82f6",
    "selected": "transparent",
    "disabled": "rgba(148, 163, 184, 0.16)",
}


def _to_qcolor(value: str | QColor | None, fallback: str = "transparent") -> QColor:
    if isinstance(value, QColor):
        return QColor(value)
    if value is None:
        return QColor(fallback)
    return QColor(str(value))


def _normalize_date_value(value: QDate | str | None) -> QDate | None:
    if isinstance(value, QDate):
        return value if value.isValid() else None

    text = str(value or "").strip()
    if not text:
        return None

    for fmt in ("yyyy-MM-dd", Qt.DateFormat.ISODate):
        if isinstance(fmt, str):
            parsed = QDate.fromString(text[: len(fmt)], fmt)
        else:
            parsed = QDate.fromString(text, fmt)
        if parsed.isValid():
            return parsed
    return None


def _date_key(value: QDate) -> str:
    return value.toString(Qt.DateFormat.ISODate)


class _PrimeCalendarWidget(QCalendarWidget):
    date_selected = Signal(QDate)

    def __init__(
        self,
        parent=None,
        selected_date: QDate | None = None,
        disabled_dates: Sequence[QDate | str] | None = None,
        day_text_colors: Mapping[str, str | QColor] | None = None,
        day_background_colors: Mapping[str, str | QColor] | None = None,
        day_border_colors: Mapping[str, str | QColor] | None = None,
        day_radius: int = 8,
        full_circle_dates: bool = True,
    ) -> None:
        super().__init__(parent)
        self._disabled_date_keys: set[str] = set()
        self._last_valid_date = selected_date if selected_date and selected_date.isValid() else QDate.currentDate()
        self._day_radius = max(0, day_radius)
        self._full_circle_dates = bool(full_circle_dates)
        self._day_text_colors = {
            state: _to_qcolor(color)
            for state, color in _DEFAULT_DAY_TEXT_COLORS.items()
        }
        self._day_background_colors = {
            state: _to_qcolor(color)
            for state, color in _DEFAULT_DAY_BACKGROUND_COLORS.items()
        }
        self._day_border_colors = {
            state: _to_qcolor(color)
            for state, color in _DEFAULT_DAY_BORDER_COLORS.items()
        }

        if day_text_colors:
            self.set_day_text_colors(day_text_colors)
        if day_background_colors:
            self.set_day_background_colors(day_background_colors)
        if day_border_colors:
            self.set_day_border_colors(day_border_colors)

        self.selectionChanged.connect(self._ensure_valid_selection)
        self.clicked.connect(self._on_clicked)
        self.activated.connect(self._on_activated)

        if disabled_dates:
            self.set_disabled_dates(disabled_dates)

    def _update_color_map(
        self,
        target: dict[str, QColor],
        values: Mapping[str, str | QColor],
    ) -> None:
        for state, color in values.items():
            if state not in _DAY_STATES:
                continue
            target[state] = _to_qcolor(color)
        self.updateCells()

    def _resolve_state(self, date: QDate) -> str:
        if self.is_date_disabled(date):
            return "disabled"
        if date == self.selectedDate():
            return "selected"
        if date == QDate.currentDate():
            return "today"
        if date.year() != self.yearShown() or date.month() != self.monthShown():
            return "outside_month"
        if date.dayOfWeek() in (6, 7):
            return "weekend"
        return "default"

    def _resolve_color(self, mapping: dict[str, QColor], state: str) -> QColor:
        color = mapping.get(state)
        if color is not None:
            return QColor(color)
        return QColor(mapping["default"])

    def _in_bounds(self, date: QDate) -> bool:
        return (
            date.isValid()
            and date >= self.minimumDate()
            and date <= self.maximumDate()
        )

    def _find_enabled_date(self, anchor: QDate | None = None) -> QDate:
        candidates = [
            anchor,
            self._last_valid_date,
            QDate.currentDate(),
            self.minimumDate(),
            self.maximumDate(),
        ]
        for candidate in candidates:
            if isinstance(candidate, QDate) and self._in_bounds(candidate) and not self.is_date_disabled(candidate):
                return candidate

        base = anchor if isinstance(anchor, QDate) and anchor.isValid() else QDate.currentDate()
        for offset in range(1, 3661):
            for candidate in (base.addDays(offset), base.addDays(-offset)):
                if self._in_bounds(candidate) and not self.is_date_disabled(candidate):
                    return candidate
        return QDate()

    def _ensure_valid_selection(self) -> None:
        current = self.selectedDate()
        if not current.isValid():
            return

        if self.is_date_disabled(current):
            fallback = self._find_enabled_date(current)
            if fallback.isValid() and fallback != current:
                with QSignalBlocker(self):
                    self.setSelectedDate(fallback)
                self.updateCells()
            return

        self._last_valid_date = current
        self.updateCells()

    def _on_clicked(self, value: QDate) -> None:
        if not self.is_date_disabled(value):
            self.date_selected.emit(value)

    def _on_activated(self, value: QDate) -> None:
        if not self.is_date_disabled(value):
            self.date_selected.emit(value)

    def paintCell(self, painter: QPainter, rect, date: QDate) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        state = self._resolve_state(date)
        inner = rect.adjusted(3, 3, -3, -3)
        bg = self._resolve_color(self._day_background_colors, state)
        border = self._resolve_color(self._day_border_colors, state)
        text = self._resolve_color(self._day_text_colors, state)

        if bg.alpha() > 0 or border.alpha() > 0:
            painter.setPen(Qt.NoPen if border.alpha() == 0 else QPen(border, 1))
            painter.setBrush(QBrush(bg))
            if self._full_circle_dates:
                diameter = max(0.0, min(float(inner.width()), float(inner.height())) - 1.0)
                circle = QRectF(
                    inner.center().x() - (diameter / 2.0),
                    inner.center().y() - (diameter / 2.0),
                    diameter,
                    diameter,
                )
                painter.drawEllipse(circle)
            else:
                painter.drawRoundedRect(inner, self._day_radius, self._day_radius)

        painter.setPen(QPen(text))
        painter.drawText(inner, Qt.AlignmentFlag.AlignCenter, str(date.day()))
        painter.restore()

    def set_day_text_colors(self, values: Mapping[str, str | QColor]) -> None:
        self._update_color_map(self._day_text_colors, values)

    def set_day_background_colors(self, values: Mapping[str, str | QColor]) -> None:
        self._update_color_map(self._day_background_colors, values)

    def set_day_border_colors(self, values: Mapping[str, str | QColor]) -> None:
        self._update_color_map(self._day_border_colors, values)

    def set_day_radius(self, value: int) -> None:
        self._day_radius = max(0, value)
        self.updateCells()

    def set_full_circle_dates(self, enabled: bool) -> None:
        self._full_circle_dates = bool(enabled)
        self.updateCells()

    def disabled_dates(self) -> list[QDate]:
        return sorted(
            (QDate.fromString(value, Qt.DateFormat.ISODate) for value in self._disabled_date_keys),
            key=lambda item: item.toJulianDay(),
        )

    def is_date_disabled(self, value: QDate | str | None) -> bool:
        normalized = _normalize_date_value(value)
        if normalized is None:
            return False
        return _date_key(normalized) in self._disabled_date_keys

    def set_disabled_dates(self, values: Sequence[QDate | str] | None) -> None:
        self._disabled_date_keys.clear()
        for value in values or []:
            normalized = _normalize_date_value(value)
            if normalized is not None:
                self._disabled_date_keys.add(_date_key(normalized))
        self._ensure_valid_selection()
        self.updateCells()

    def add_disabled_date(self, value: QDate | str) -> None:
        normalized = _normalize_date_value(value)
        if normalized is None:
            return
        self._disabled_date_keys.add(_date_key(normalized))
        self._ensure_valid_selection()
        self.updateCells()

    def remove_disabled_date(self, value: QDate | str) -> None:
        normalized = _normalize_date_value(value)
        if normalized is None:
            return
        self._disabled_date_keys.discard(_date_key(normalized))
        self.updateCells()

    def clear_disabled_dates(self) -> None:
        self._disabled_date_keys.clear()
        self.updateCells()


class PrimeCalendar(QWidget):
    date_changed = Signal(QDate)
    date_selected = Signal(QDate)

    def __init__(
        self,
        parent=None,
        radius: int = 10,
        selected_date: QDate | None = None,
        framed: bool = True,
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
    ) -> None:
        super().__init__(parent)
        self._radius = radius
        self._framed = framed
        self._weekday_header_text_color = _to_qcolor(weekday_header_text_color)
        self._weekday_header_weekend_text_color = _to_qcolor(weekday_header_weekend_text_color)
        self._navigation_prev_icon = navigation_prev_icon
        self._navigation_next_icon = navigation_next_icon
        self._navigation_icon_color = _to_qcolor(navigation_icon_color)
        self._navigation_hover_background = _to_qcolor(navigation_hover_background)
        self._navigation_icon_padding = max(0, navigation_icon_padding)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.container = QFrame(self)
        self.container.setObjectName("primeCalendarContainer")
        container_layout = QVBoxLayout(self.container)
        padding = 10 if self._framed else 0
        container_layout.setContentsMargins(padding, padding, padding, padding)
        container_layout.setSpacing(0)

        self.calendar = _PrimeCalendarWidget(
            self.container,
            selected_date=selected_date,
            disabled_dates=disabled_dates,
            day_text_colors=day_text_colors,
            day_background_colors=day_background_colors,
            day_border_colors=day_border_colors,
            day_radius=day_radius,
            full_circle_dates=full_circle_dates,
        )
        self.calendar.setObjectName("primeCalendar")
        self.calendar.setLocale(QLocale.system())
        self.calendar.setGridVisible(False)
        self.calendar.setNavigationBarVisible(False)
        self.calendar.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        self.calendar.setHorizontalHeaderFormat(
            QCalendarWidget.HorizontalHeaderFormat.NoHorizontalHeader
        )

        if selected_date is not None and selected_date.isValid():
            self.calendar.setSelectedDate(selected_date)

        self.calendar.selectionChanged.connect(self._on_selection_changed)
        self.calendar.date_selected.connect(self.date_selected.emit)

        # Custom navigation bar
        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(0, 0, 0, 6)
        nav_row.setSpacing(6)

        self._nav_prev_btn = QPushButton("‹")
        self._nav_prev_btn.setObjectName("calNavBtn")
        self._nav_prev_btn.setFixedSize(36, 36)
        self._nav_prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._nav_prev_btn.clicked.connect(self._go_prev_month)

        _locale = QLocale.system()
        month_options = [
            {"label": _locale.monthName(i, QLocale.FormatType.LongFormat), "value": i}
            for i in range(1, 13)
        ]
        self._month_select = PrimeSelect(month_options, placeholder="Month")
        self._month_select.setMinimumWidth(0)
        self._month_select.value_changed.connect(self._on_month_select_changed)

        self._year_input = PrimeInput(
            type="number",
            minimum=1900,
            maximum=2100,
            decimals=0,
            value=QDate.currentDate().year(),
        )
        self._year_input.setMinimumWidth(0)
        self._year_input.editingFinished.connect(self._on_year_input_changed)

        self._nav_next_btn = QPushButton("›")
        self._nav_next_btn.setObjectName("calNavBtn")
        self._nav_next_btn.setFixedSize(36, 36)
        self._nav_next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._nav_next_btn.clicked.connect(self._go_next_month)

        nav_row.addWidget(self._nav_prev_btn)
        nav_row.addWidget(self._month_select, 1)
        nav_row.addWidget(self._year_input, 1)
        nav_row.addWidget(self._nav_next_btn)

        self.calendar.currentPageChanged.connect(lambda y, m: self._sync_nav_selects())

        container_layout.addLayout(nav_row)
        container_layout.addWidget(self.calendar)
        root.addWidget(self.container)

        self._apply_style()
        QTimer.singleShot(0, self._sync_nav_selects)

    def _go_prev_month(self) -> None:
        d = QDate(self.calendar.yearShown(), self.calendar.monthShown(), 1).addMonths(-1)
        self.calendar.setCurrentPage(d.year(), d.month())

    def _go_next_month(self) -> None:
        d = QDate(self.calendar.yearShown(), self.calendar.monthShown(), 1).addMonths(1)
        self.calendar.setCurrentPage(d.year(), d.month())

    def _on_month_select_changed(self, value: object) -> None:
        if value is None:
            return
        self.calendar.setCurrentPage(self.calendar.yearShown(), int(value))

    def _on_year_input_changed(self) -> None:
        year = int(self._year_input.value())
        if 1900 <= year <= 2100:
            self.calendar.setCurrentPage(year, self.calendar.monthShown())

    def _sync_nav_selects(self) -> None:
        self._month_select.set_value(self.calendar.monthShown())
        self._year_input.setValue(self.calendar.yearShown())

    @staticmethod
    def _normalize_nav_icon(value: QIcon | str | None) -> QIcon | str | None:
        if isinstance(value, QIcon):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            if os.path.exists(text):
                return QIcon(text)
            return text
        return None

    def _apply_button_icon(self, button: QToolButton | None, value: QIcon | str | None) -> None:
        if button is None:
            return
        normalized = self._normalize_nav_icon(value)
        button_extent = max(28, 16 + (self._navigation_icon_padding * 2))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAutoRaise(True)
        button.setFixedSize(button_extent, button_extent)
        if isinstance(normalized, QIcon):
            button.setText("")
            button.setIcon(normalized)
            icon_extent = max(12, button_extent - (self._navigation_icon_padding * 2))
            button.setIconSize(QSize(icon_extent, icon_extent))
            return
        button.setIcon(QIcon())
        button.setText(str(normalized or ""))

    def _configure_navigation_buttons(self) -> None:
        prev_button = self.calendar.findChild(QToolButton, "qt_calendar_prevmonth")
        next_button = self.calendar.findChild(QToolButton, "qt_calendar_nextmonth")
        month_button = self.calendar.findChild(QToolButton, "qt_calendar_monthbutton")
        year_button = self.calendar.findChild(QToolButton, "qt_calendar_yearbutton")

        self._apply_button_icon(prev_button, self._navigation_prev_icon)
        self._apply_button_icon(next_button, self._navigation_next_icon)

        for button in (month_button, year_button):
            if button is not None:
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setAutoRaise(True)

    def _apply_weekday_formats(self) -> None:
        weekday_format = QTextCharFormat()
        weekday_format.setForeground(self._weekday_header_text_color)
        weekday_format.setFontWeight(int(QFont.Weight.DemiBold))

        weekend_format = QTextCharFormat()
        weekend_format.setForeground(self._weekday_header_weekend_text_color)
        weekend_format.setFontWeight(int(QFont.Weight.Bold))

        for day in range(1, 8):
            day_of_week = Qt.DayOfWeek(day)
            is_weekend = day in (6, 7)
            self.calendar.setWeekdayTextFormat(
                day_of_week,
                weekend_format if is_weekend else weekday_format,
            )

    def _build_stylesheet(self) -> str:
        container_background = "#1b1c1f" if self._framed else "transparent"
        container_border = "1px solid #101114" if self._framed else "none"
        container_radius = f"{self._radius}px" if self._framed else "0px"
        navigation_icon_color = self._navigation_icon_color.name(QColor.NameFormat.HexArgb)
        navigation_hover_background = self._navigation_hover_background.name(QColor.NameFormat.HexArgb)
        navigation_button_extent = max(28, 16 + (self._navigation_icon_padding * 2))
        navigation_button_radius = navigation_button_extent // 2

        return f"""
            #primeCalendarContainer {{
                background-color: {container_background};
                border: {container_border};
                border-radius: {container_radius};
            }}
            QCalendarWidget#primeCalendar {{
                background: transparent;
                border: none;
            }}
            QCalendarWidget#primeCalendar QAbstractItemView:enabled {{
                background: transparent;
                color: transparent;
                selection-background-color: transparent;
                selection-color: transparent;
                outline: 0;
                border: none;
            }}
            QPushButton#calNavBtn {{
                background: #2a2d31;
                color: {navigation_icon_color};
                border: 1px solid #2f3338;
                border-radius: 8px;
                font-size: 18px;
                font-weight: 700;
                padding: 0;
            }}
            QPushButton#calNavBtn:hover {{
                background: {navigation_hover_background};
                border-color: #3a3f45;
            }}
            QPushButton#calNavBtn:pressed {{
                background: #1e2125;
            }}
        """

    def _apply_style(self) -> None:
        self.setStyleSheet(self._build_stylesheet())

    def _on_selection_changed(self) -> None:
        self.date_changed.emit(self.selected_date())

    def sizeHint(self) -> QSize:
        hint = self.calendar.sizeHint()
        extra = 20 if self._framed else 0
        return QSize(max(320, hint.width() + extra), hint.height() + extra)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def selected_date(self) -> QDate:
        return self.calendar.selectedDate()

    def set_selected_date(self, value: QDate) -> None:
        if value.isValid():
            self.calendar.setSelectedDate(value)

    def set_minimum_date(self, value: QDate) -> None:
        self.calendar.setMinimumDate(value)

    def set_maximum_date(self, value: QDate) -> None:
        self.calendar.setMaximumDate(value)

    def set_locale(self, locale: QLocale) -> None:
        self.calendar.setLocale(locale)
        month_options = [
            {"label": locale.monthName(i, QLocale.FormatType.LongFormat), "value": i}
            for i in range(1, 13)
        ]
        self._month_select.set_options(month_options)
        self._sync_nav_selects()

    def set_grid_visible(self, visible: bool) -> None:
        self.calendar.setGridVisible(visible)

    def set_radius(self, value: int) -> None:
        self._radius = max(0, value)
        self._apply_style()

    def set_day_text_colors(self, values: Mapping[str, str | QColor]) -> None:
        self.calendar.set_day_text_colors(values)

    def set_day_background_colors(self, values: Mapping[str, str | QColor]) -> None:
        self.calendar.set_day_background_colors(values)

    def set_day_border_colors(self, values: Mapping[str, str | QColor]) -> None:
        self.calendar.set_day_border_colors(values)

    def set_day_radius(self, value: int) -> None:
        self.calendar.set_day_radius(value)

    def set_full_circle_dates(self, enabled: bool) -> None:
        self.calendar.set_full_circle_dates(enabled)

    def set_weekday_header_colors(
        self,
        default: str | QColor,
        weekend: str | QColor | None = None,
    ) -> None:
        self._weekday_header_text_color = _to_qcolor(default)
        self._weekday_header_weekend_text_color = _to_qcolor(
            weekend,
            self._weekday_header_text_color.name(),
        )
        self._apply_weekday_formats()

    def set_navigation_icons(
        self,
        previous: QIcon | str | None = None,
        next_: QIcon | str | None = None,
    ) -> None:
        if previous is not None:
            self._navigation_prev_icon = previous
        if next_ is not None:
            self._navigation_next_icon = next_
        self._configure_navigation_buttons()

    def set_navigation_style(
        self,
        icon_color: str | QColor | None = None,
        hover_background: str | QColor | None = None,
    ) -> None:
        if icon_color is not None:
            self._navigation_icon_color = _to_qcolor(icon_color)
        if hover_background is not None:
            self._navigation_hover_background = _to_qcolor(hover_background)
        self._apply_style()
        QTimer.singleShot(0, self._configure_navigation_buttons)

    def set_navigation_icon_padding(self, value: int) -> None:
        self._navigation_icon_padding = max(0, value)
        self._apply_style()
        QTimer.singleShot(0, self._configure_navigation_buttons)

    def disabled_dates(self) -> list[QDate]:
        return self.calendar.disabled_dates()

    def set_disabled_dates(self, values: Sequence[QDate | str] | None) -> None:
        self.calendar.set_disabled_dates(values)

    def add_disabled_date(self, value: QDate | str) -> None:
        self.calendar.add_disabled_date(value)

    def remove_disabled_date(self, value: QDate | str) -> None:
        self.calendar.remove_disabled_date(value)

    def clear_disabled_dates(self) -> None:
        self.calendar.clear_disabled_dates()

    def is_date_disabled(self, value: QDate | str | None) -> bool:
        return self.calendar.is_date_disabled(value)


class DemoWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("PrimeCalendar Demo")
        self.setMinimumSize(420, 380)
        self.setStyleSheet("background-color: #1e1e21;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        self.status_label = QLabel("Selected date: --")
        self.status_label.setStyleSheet("color: #eef2f8; font-size: 13px;")
        layout.addWidget(self.status_label)

        self.calendar = PrimeCalendar(
            selected_date=QDate.currentDate(),
            disabled_dates=[
                QDate.currentDate().addDays(1),
                QDate.currentDate().addDays(3),
            ],
            day_text_colors={
                "default": "#f8fafc",
                "weekend": "#fca5a5",
                "disabled": "#6b7280",
            },
            day_background_colors={
                "today": "#1d4ed8",
                "selected": "#f8fafc",
                "disabled": "rgba(255, 255, 255, 0.04)",
            },
            day_border_colors={
                "today": "#93c5fd",
                "disabled": "rgba(148, 163, 184, 0.18)",
            },
            day_radius=10,
        )
        self.calendar.date_selected.connect(self._update_status)
        layout.addWidget(self.calendar)

        today_btn = QPushButton("Go To Today")
        today_btn.clicked.connect(
            lambda: self.calendar.set_selected_date(QDate.currentDate())
        )
        layout.addWidget(today_btn)

        self._update_status(self.calendar.selected_date())

    def _update_status(self, value: QDate) -> None:
        self.status_label.setText(f"Selected date: {value.toString('yyyy-MM-dd')}")


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = DemoWindow()
    window.show()

    sys.exit(app.exec())
