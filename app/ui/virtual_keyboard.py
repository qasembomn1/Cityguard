from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QAbstractSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    from shiboken6 import isValid as _qt_object_is_valid
except Exception:  # pragma: no cover - runtime fallback
    _qt_object_is_valid = None


EditableWidget = QLineEdit | QTextEdit | QPlainTextEdit


def _is_alive(widget: QObject | None) -> bool:
    if widget is None:
        return False
    if _qt_object_is_valid is not None:
        try:
            return bool(_qt_object_is_valid(widget))
        except Exception:
            return False
    try:
        widget.objectName()
    except RuntimeError:
        return False
    except Exception:
        return True
    return True


def _resolve_target(widget: QObject | None) -> EditableWidget | None:
    current = widget
    while _is_alive(current):
        if isinstance(current, QLineEdit):
            return current
        if isinstance(current, (QTextEdit, QPlainTextEdit)):
            return current
        if isinstance(current, QAbstractSpinBox):
            try:
                line_edit = current.lineEdit()
            except RuntimeError:
                line_edit = None
            if _is_alive(line_edit):
                return line_edit
        try:
            current = current.parent()
        except RuntimeError:
            return None
    return None


def _can_type_into(widget: EditableWidget | None) -> bool:
    if not _is_alive(widget):
        return False
    try:
        if not widget.isEnabled():
            return False
        return not widget.isReadOnly()
    except RuntimeError:
        return False


class FloatingKeyboard(QFrame):
    def __init__(self, root: QWidget):
        super().__init__(None)
        self._root = root
        self._target: EditableWidget | None = None
        self._drag_offset: QPoint | None = None
        self._shift_enabled = False
        self._user_positioned = False
        self._letter_buttons: list[QPushButton] = []
        self._shift_button: QPushButton | None = None
        self._drag_handles: tuple[QWidget, ...] = ()

        self.setObjectName("virtualKeyboard")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        header = QFrame(self)
        header.setObjectName("virtualKeyboardHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 6, 8, 6)
        header_layout.setSpacing(6)

        self.header_title = QLabel("Keyboard")
        self.header_title.setObjectName("virtualKeyboardTitle")
        header_layout.addWidget(self.header_title)
        header_layout.addStretch(1)

        self.close_button = self._create_button("Close", self.hide, wide=True, accent=True)
        self.close_button.setObjectName("virtualKeyboardClose")
        header_layout.addWidget(self.close_button)
        root_layout.addWidget(header)
        self._drag_handles = (header, self.header_title)
        for widget in self._drag_handles:
            widget.installEventFilter(self)

        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        root_layout.addLayout(grid)

        self._add_text_row(grid, 0, list("1234567890"), start_col=0)
        self._add_action_button(grid, 0, 10, "-", lambda: self._insert_text("-"))
        self._add_action_button(grid, 0, 11, "/", lambda: self._insert_text("/"))

        self._add_letter_row(grid, 1, "qwertyuiop")
        self._add_action_button(grid, 1, 10, ".", lambda: self._insert_text("."))
        self._add_action_button(grid, 1, 11, ":", lambda: self._insert_text(":"))

        self._add_letter_row(grid, 2, "asdfghjkl")
        self._add_action_button(grid, 2, 9, "@", lambda: self._insert_text("@"))
        self._add_action_button(grid, 2, 10, "_", lambda: self._insert_text("_"))
        self._add_action_button(grid, 2, 11, "BS", self._backspace, kind="danger")

        self._shift_button = self._create_button("Shift", self._toggle_shift, wide=True)
        grid.addWidget(self._shift_button, 3, 0, 1, 2)
        self._add_letter_row(grid, 3, "zxcvbnm", start_col=2)
        self._add_action_button(grid, 3, 9, ",", lambda: self._insert_text(","))
        self._add_action_button(grid, 3, 10, "(", lambda: self._insert_text("("))
        self._add_action_button(grid, 3, 11, ")", lambda: self._insert_text(")"))

        self._add_action_button(grid, 4, 0, "Clear", self._clear_target, span=2, kind="danger")
        self._add_action_button(grid, 4, 2, "Space", lambda: self._insert_text(" "), span=4, wide=True)
        self._add_action_button(grid, 4, 6, "Next", self._focus_next, span=2, wide=True)
        self._add_action_button(grid, 4, 8, "Enter", self._enter, span=2, accent=True, wide=True)
        self._add_action_button(grid, 4, 10, "Hide", self.hide, span=2, wide=True)

        self.setStyleSheet(
            """
            QFrame#virtualKeyboard {
                background: rgba(9, 14, 22, 0.97);
                border: 1px solid rgba(71, 85, 105, 0.75);
                border-radius: 14px;
            }
            QFrame#virtualKeyboardHeader {
                background: rgba(15, 23, 42, 0.92);
                border: 1px solid rgba(71, 85, 105, 0.55);
                border-radius: 10px;
            }
            QLabel#virtualKeyboardTitle {
                color: #f8fafc;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton {
                background: rgba(30, 41, 59, 0.96);
                color: #e2e8f0;
                border: 1px solid rgba(100, 116, 139, 0.7);
                border-radius: 8px;
                padding: 7px 6px;
                font-size: 12px;
                font-weight: 600;
                min-width: 36px;
                min-height: 30px;
            }
            QPushButton:hover {
                background: rgba(51, 65, 85, 0.98);
                border-color: rgba(148, 163, 184, 0.92);
            }
            QPushButton:pressed {
                background: rgba(15, 23, 42, 0.98);
            }
            QPushButton[wide="true"] {
                padding-left: 10px;
                padding-right: 10px;
            }
            QPushButton[accent="true"] {
                background: rgba(14, 116, 144, 0.96);
                border-color: rgba(103, 232, 249, 0.8);
                color: #ecfeff;
            }
            QPushButton[accent="true"]:hover {
                background: rgba(8, 145, 178, 0.98);
            }
            QPushButton[danger="true"] {
                background: rgba(127, 29, 29, 0.92);
                border-color: rgba(248, 113, 113, 0.78);
                color: #fee2e2;
            }
            QPushButton[shift="true"] {
                background: rgba(29, 78, 216, 0.96);
                border-color: rgba(147, 197, 253, 0.86);
                color: #eff6ff;
            }
            """
        )
        self.resize(620, 260)
        self.hide()

    def _create_button(
        self,
        label: str,
        handler,
        *,
        wide: bool = False,
        accent: bool = False,
        kind: str = "",
    ) -> QPushButton:
        button = QPushButton(label)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(handler)
        button.setProperty("wide", wide)
        button.setProperty("accent", accent)
        button.setProperty("danger", kind == "danger")
        return button

    def _add_action_button(
        self,
        layout: QGridLayout,
        row: int,
        column: int,
        label: str,
        handler,
        *,
        span: int = 1,
        wide: bool = False,
        accent: bool = False,
        kind: str = "",
    ) -> None:
        layout.addWidget(
            self._create_button(label, handler, wide=wide, accent=accent, kind=kind),
            row,
            column,
            1,
            span,
        )

    def _add_text_row(self, layout: QGridLayout, row: int, keys: Iterable[str], *, start_col: int = 0) -> None:
        for offset, key in enumerate(keys):
            self._add_action_button(layout, row, start_col + offset, key, lambda _checked=False, text=key: self._insert_text(text))

    def _add_letter_row(self, layout: QGridLayout, row: int, letters: str, *, start_col: int = 0) -> None:
        for offset, letter in enumerate(letters):
            button = self._create_button(letter.upper(), lambda _checked=False, text=letter: self._insert_letter(text))
            button.setProperty("letter", letter)
            self._letter_buttons.append(button)
            layout.addWidget(button, row, start_col + offset)

    def set_root(self, root: QWidget) -> None:
        self._root = root

    def set_target(self, widget: EditableWidget | None) -> None:
        if not _is_alive(widget):
            widget = None
        self._target = widget
        self.header_title.setText("Keyboard" if widget is None else f"Keyboard: {type(widget).__name__}")

    def show_for(self, widget: EditableWidget) -> None:
        previous_target = self._target
        self.set_target(widget)
        should_reposition = (not self.isVisible()) or (previous_target is not widget and not self._user_positioned)
        if should_reposition:
            self._move_to_default_position()
        if not self.isVisible():
            self.show()
        self.raise_()

    def current_target(self) -> EditableWidget | None:
        if not _is_alive(self._target):
            self._target = None
        return self._target

    def hide(self) -> None:
        super().hide()
        self._target = None

    def contains_widget(self, widget: QObject | None) -> bool:
        current = widget
        while _is_alive(current):
            if current is self:
                return True
            try:
                current = current.parent()
            except RuntimeError:
                return False
        return False

    def contains_global_point(self, point: QPoint) -> bool:
        return self.isVisible() and self.frameGeometry().contains(point)

    def _move_to_default_position(self) -> None:
        target = self.current_target()
        screen = None
        if target is not None:
            try:
                screen = target.screen()
            except RuntimeError:
                screen = None
        if screen is None and self._root is not None:
            screen = self._root.screen()
        geometry = screen.availableGeometry() if screen is not None else (self._root.frameGeometry() if self._root.isVisible() else self._root.geometry())
        if not geometry.isValid():
            return
        x = geometry.left() + max(0, (geometry.width() - self.width()) // 2)
        y = geometry.top() + max(0, (geometry.height() - self.height()) // 2)
        self.move(x, y)

    def _toggle_shift(self) -> None:
        self._shift_enabled = not self._shift_enabled
        self._refresh_letter_buttons()

    def _refresh_letter_buttons(self) -> None:
        for button in self._letter_buttons:
            letter = str(button.property("letter") or "")
            button.setText(letter.upper() if self._shift_enabled else letter.lower())
        if self._shift_button is not None:
            self._shift_button.setProperty("shift", self._shift_enabled)
            self._shift_button.style().unpolish(self._shift_button)
            self._shift_button.style().polish(self._shift_button)

    def _insert_letter(self, letter: str) -> None:
        self._insert_text(letter.upper() if self._shift_enabled else letter.lower())

    def _insert_text(self, text: str) -> None:
        target = self._prepare_target_for_input()
        if target is None:
            return
        if isinstance(target, QLineEdit):
            target.insert(text)
            return
        cursor = target.textCursor()
        cursor.insertText(text)
        target.setTextCursor(cursor)

    def _backspace(self) -> None:
        target = self._prepare_target_for_input()
        if target is None:
            return
        if isinstance(target, QLineEdit):
            target.backspace()
            return
        cursor = target.textCursor()
        if cursor.hasSelection():
            cursor.removeSelectedText()
        else:
            cursor.deletePreviousChar()
        target.setTextCursor(cursor)

    def _clear_target(self) -> None:
        target = self._prepare_target_for_input()
        if target is None:
            return
        target.clear()

    def _focus_next(self) -> None:
        target = self._prepare_target_for_input()
        if target is None:
            return
        window = target.window()
        window.setWindowFlags(Qt.FramelessWindowHint)
        if window is not None:
            window.focusNextChild()

    def _enter(self) -> None:
        target = self._prepare_target_for_input()
        if target is None:
            return
        if isinstance(target, QLineEdit):
            target.returnPressed.emit()
            target.editingFinished.emit()
            return
        cursor = target.textCursor()
        cursor.insertText("\n")
        target.setTextCursor(cursor)

    def _prepare_target_for_input(self) -> EditableWidget | None:
        target = self.current_target()
        if not _can_type_into(target):
            self._target = None
            return None
        try:
            if not target.hasFocus():
                target.setFocus(Qt.FocusReason.OtherFocusReason)
        except RuntimeError:
            self._target = None
            return None
        return target

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            self._user_positioned = True
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched in self._drag_handles:
            if event.type() == QEvent.Type.MouseButtonPress:
                mouse_event = event
                if isinstance(mouse_event, QMouseEvent) and mouse_event.button() == Qt.MouseButton.LeftButton:
                    self._drag_offset = mouse_event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    return True
            if event.type() == QEvent.Type.MouseMove:
                mouse_event = event
                if isinstance(mouse_event, QMouseEvent) and self._drag_offset is not None and (mouse_event.buttons() & Qt.MouseButton.LeftButton):
                    self.move(mouse_event.globalPosition().toPoint() - self._drag_offset)
                    self._user_positioned = True
                    return True
            if event.type() == QEvent.Type.MouseButtonRelease:
                self._drag_offset = None
                return True
        return super().eventFilter(watched, event)


class KeyboardToggleButton(QToolButton):
    def __init__(self, root: QWidget, toggle_handler):
        super().__init__(root)
        self._root = root
        self.clicked.connect(toggle_handler)
        self.setText("⌨")
        self.setFixedSize(36, 36)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip("Toggle Keyboard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoRaise(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setStyleSheet(
            """
            QToolButton {
                background: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(148, 163, 184, 0.45);
                border-radius: 10px;
                color: #e5e7eb;
                padding: 0;
                font-size: 12px;
                font-weight: 600;
            }
            QToolButton:hover {
                background: rgba(30, 41, 59, 0.95);
                border: 1px solid rgba(203, 213, 225, 0.75);
            }
            QToolButton:pressed {
                background: rgba(17, 24, 39, 0.98);
            }
            """
        )

    def set_root(self, root: QWidget) -> None:
        self._root = root
        self.setParent(root)
        self.raise_()

    def move_to_top_left(self) -> None:
        if self._root is None:
            return
        root_rect = self._root.rect()
        if not root_rect.isValid():
            return
        self.move(
            20,
            max(20, root_rect.height() - self.height() - 20),
        )
        self.raise_()

    def contains_global_point(self, point: QPoint) -> bool:
        return self.isVisible() and self.rect().contains(self.mapFromGlobal(point))


class VirtualKeyboardManager(QObject):
    def __init__(self, root: QWidget):
        super().__init__(root)
        self._root = root
        self._keyboard = FloatingKeyboard(root)
        self._keyboard.hide()
        self._toggle_button = KeyboardToggleButton(root, self.toggle_keyboard)
        self._toggle_button.move_to_top_left()
        self._toggle_button.show()
        self._last_target: EditableWidget | None = None

        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._on_focus_changed)

    def set_root(self, root: QWidget) -> None:
        self._root = root
        self._keyboard.set_root(root)
        self._toggle_button.set_root(root)
        self._toggle_button.move_to_top_left()

    def show_keyboard(self) -> None:
        app = QApplication.instance()
        focus_target = _resolve_target(app.focusWidget()) if app is not None else None
        last_target = self._last_target if _can_type_into(self._last_target) else None
        if last_target is None:
            self._last_target = None
        target = focus_target if _can_type_into(focus_target) else last_target
        if not _can_type_into(target):
            return
        self._keyboard.show_for(target)

    def hide_keyboard(self) -> None:
        self._keyboard.hide()

    def toggle_keyboard(self) -> None:
        if self._keyboard.isVisible():
            self.hide_keyboard()
            return
        self.show_keyboard()

    def set_toggle_visible(self, visible: bool) -> None:
        if visible:
            self._toggle_button.show()
            self._toggle_button.raise_()
            return
        self.hide_keyboard()
        self._toggle_button.hide()

    def _remember_target(self, widget: EditableWidget | None) -> None:
        if not _can_type_into(widget):
            return
        self._last_target = widget
        self._keyboard.set_target(widget)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        event_type = event.type()
        if watched is self._root and event_type in (
            QEvent.Type.Show,
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.WindowStateChange,
        ):
            self._toggle_button.move_to_top_left()
        if event_type == QEvent.Type.MouseButtonPress:
            mouse_event = event if isinstance(event, QMouseEvent) else None
            if mouse_event is not None and self._keyboard.contains_global_point(mouse_event.globalPosition().toPoint()):
                return super().eventFilter(watched, event)
            if mouse_event is not None and self._toggle_button.contains_global_point(mouse_event.globalPosition().toPoint()):
                return super().eventFilter(watched, event)
            if self._keyboard.contains_widget(watched):
                return super().eventFilter(watched, event)
            target = _resolve_target(watched)
            if _can_type_into(target):
                self._remember_target(target)
        return super().eventFilter(watched, event)

    def _on_focus_changed(self, _old: QWidget | None, now: QWidget | None) -> None:
        if now is None:
            return
        if self._keyboard.contains_widget(now):
            return
        if now is self._toggle_button:
            return
        target = _resolve_target(now)
        if _can_type_into(target):
            self._remember_target(target)


def install_virtual_keyboard(root: QWidget | None = None) -> None:
    app = QApplication.instance()
    if app is None:
        return

    manager = getattr(app, "_virtual_keyboard_manager", None)
    if manager is None:
        if root is None:
            return
        manager = VirtualKeyboardManager(root)
        app.installEventFilter(manager)
        app._virtual_keyboard_manager = manager
        return

    if root is not None:
        manager.set_root(root)


def set_virtual_keyboard_toggle_visible(visible: bool) -> None:
    app = QApplication.instance()
    if app is None:
        return
    manager = getattr(app, "_virtual_keyboard_manager", None)
    if manager is None:
        return
    manager.set_toggle_visible(bool(visible))
