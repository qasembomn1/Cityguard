from __future__ import annotations

from PySide6.QtCore import QEvent, QLocale, QObject, Qt
from PySide6.QtWidgets import QApplication, QAbstractSpinBox, QDateTimeEdit, QLineEdit, QWidget

from app.utils.digits import normalize_ascii_digits


ENGLISH_LOCALE = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
_SAFE_CONFIG_EVENTS = {
    QEvent.Type.Show,
    QEvent.Type.FocusIn,
    QEvent.Type.Polish,
    QEvent.Type.PolishRequest,
}


def _normalize_line_edit(field: QLineEdit) -> None:
    text = field.text()
    normalized = normalize_ascii_digits(text)
    if normalized == text:
        return
    cursor = field.cursorPosition()
    field.blockSignals(True)
    field.setText(normalized)
    field.blockSignals(False)
    field.setCursorPosition(min(cursor, len(normalized)))


def _configure_widget(widget: QObject) -> None:
    if isinstance(widget, QLineEdit):
        if widget.property("_ascii_digits_ready") is not None:
            _normalize_line_edit(widget)
            return
        widget.setInputMethodHints(widget.inputMethodHints() | Qt.InputMethodHint.ImhPreferLatin)
        widget.textChanged.connect(lambda _text, field=widget: _normalize_line_edit(field))
        widget.editingFinished.connect(lambda field=widget: _normalize_line_edit(field))
        widget.setProperty("_ascii_digits_ready", True)
        _normalize_line_edit(widget)
        return

    if isinstance(widget, QAbstractSpinBox):
        widget.setLocale(ENGLISH_LOCALE)
        line_edit = widget.lineEdit()
        if line_edit is not None:
            _configure_widget(line_edit)
        widget.setProperty("_ascii_digits_ready", True)
        return

    if isinstance(widget, QDateTimeEdit):
        widget.setLocale(ENGLISH_LOCALE)
        widget.setProperty("_ascii_digits_ready", True)


class EnglishDigitEventFilter(QObject):
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if isinstance(watched, (QLineEdit, QAbstractSpinBox, QDateTimeEdit)):
            if (
                watched.property("_ascii_digits_ready") is None
                and event.type() in _SAFE_CONFIG_EVENTS
            ):
                _configure_widget(watched)

            if (
                isinstance(watched, QLineEdit)
                and watched.property("_ascii_digits_ready") is not None
                and event.type() == QEvent.Type.FocusOut
            ):
                _normalize_line_edit(watched)

            if (
                isinstance(watched, QAbstractSpinBox)
                and watched.property("_ascii_digits_ready") is not None
                and event.type() in (
                QEvent.Type.Show,
                QEvent.Type.FocusIn,
                )
            ):
                _configure_widget(watched)

        return super().eventFilter(watched, event)


def install_english_digit_support(root: QWidget | None = None) -> None:
    app = QApplication.instance()
    if app is None:
        return

    QLocale.setDefault(ENGLISH_LOCALE)

    event_filter = getattr(app, "_english_digit_filter", None)
    if event_filter is None:
        event_filter = EnglishDigitEventFilter(app)
        app.installEventFilter(event_filter)
        app._english_digit_filter = event_filter

    if root is None:
        return

    _configure_widget(root)
    for widget in root.findChildren(QWidget):
        _configure_widget(widget)
