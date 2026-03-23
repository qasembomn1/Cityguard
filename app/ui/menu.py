from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from typing import Any

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QCursor, QIcon, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget


class PrimeMenu(QMenu):
    item_triggered = Signal(object)

    def __init__(
        self,
        items: Sequence[Any] | None = None,
        title: str = "",
        parent: QWidget | None = None,
        radius: int = 10,
        minimum_width: int = 220,
    ) -> None:
        super().__init__(title, parent)
        self._radius = radius
        self._minimum_width = max(0, minimum_width)
        self._panel_padding = 10
        self._items: list[Any] = []
        self._actions: list[QAction] = []

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setToolTipsVisible(True)
        self.setMinimumWidth(self._minimum_width)
        self._apply_style()

        if items is not None:
            self.set_items(items)

    def _build_stylesheet(self) -> str:
        return f"""
            QMenu {{
                background: transparent;
                border: none;
                color: #f5f5f5;
                padding: {self._panel_padding}px;
                margin: 0;
            }}
            QMenu::item {{
                background: #1f2023;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 8px 12px;
                margin: 2px 0;
            }}
            QMenu::item:selected {{
                background: #2a2d31;
                color: #f5f5f5;
            }}
            QMenu::item:disabled {{
                color: rgba(245, 245, 245, 0.38);
            }}
            QMenu::separator {{
                height: 1px;
                background: #101114;
                margin: 8px 0;
            }}
            QMenu::section {{
                background: transparent;
                color: #94a3b8;
                padding: 6px 8px 4px 8px;
                margin: 2px 0;
                font-weight: 700;
            }}
            QMenu::icon {{
                padding-left: 2px;
            }}
            QMenu::right-arrow {{
                margin-right: 8px;
            }}
        """

    def _apply_style(self) -> None:
        self.setStyleSheet(self._build_stylesheet())

    def sizeHint(self):
        hint = super().sizeHint()
        if self._minimum_width > 0:
            hint.setWidth(max(hint.width(), self._minimum_width))
        return hint

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        panel_rect = self.rect().adjusted(0, 0, -1, -1)
        painter.setPen(QPen(QColor("#101114"), 1))
        painter.setBrush(QBrush(QColor("#1b1c1f")))
        painter.drawRoundedRect(panel_rect, self._radius, self._radius)

        super().paintEvent(event)

    def set_minimum_menu_width(self, value: int) -> None:
        self._minimum_width = max(0, value)
        self.setMinimumWidth(self._minimum_width)
        self.updateGeometry()

    @staticmethod
    def normalize_item(item: Any) -> dict[str, Any]:
        if isinstance(item, str):
            return {"label": item}

        if isinstance(item, tuple):
            if len(item) == 2:
                label, payload = item
                if callable(payload):
                    return {"label": str(label), "command": payload}
                if isinstance(payload, (list, tuple)):
                    return {"label": str(label), "items": list(payload)}
                return {"label": str(label), "data": payload}
            raise ValueError("Menu tuple items must contain exactly 2 values.")

        if isinstance(item, Mapping):
            return dict(item)

        raise TypeError("Menu items must be strings, 2-tuples, or mappings.")

    def _resolve_icon(self, icon_value: Any) -> QIcon | None:
        if isinstance(icon_value, QIcon):
            return icon_value
        if isinstance(icon_value, str) and icon_value.strip():
            return QIcon(icon_value)
        return None

    def _apply_action_properties(self, action: QAction, item: dict[str, Any], checkable: bool = True) -> None:
        icon = self._resolve_icon(item.get("icon"))
        if icon is not None:
            action.setIcon(icon)

        tooltip = item.get("tooltip")
        if tooltip:
            action.setToolTip(str(tooltip))

        shortcut = item.get("shortcut")
        if shortcut:
            action.setShortcut(str(shortcut))

        action.setVisible(bool(item.get("visible", True)))
        action.setEnabled(not bool(item.get("disabled", False)))

        if checkable and item.get("checkable"):
            action.setCheckable(True)
            action.setChecked(bool(item.get("checked", False)))

    def _on_action_triggered(self, item: dict[str, Any]) -> None:
        self.item_triggered.emit(item)
        command = item.get("command")
        if callable(command):
            command()

    def _add_action_item(self, menu: QMenu, item: dict[str, Any]) -> QAction | None:
        label = str(item.get("label", "")).strip()
        if not label:
            return None

        payload = dict(item)
        action = menu.addAction(label)
        self._apply_action_properties(action, payload)
        action.triggered.connect(
            lambda checked=False, current_item=payload: self._on_action_triggered(current_item)
        )
        self._actions.append(action)
        return action

    def _add_group_items(self, menu: QMenu, items: Sequence[Any]) -> None:
        for raw_item in items:
            item = self.normalize_item(raw_item)
            if not item.get("visible", True):
                continue
            if item.get("separator"):
                menu.addSeparator()
                continue

            children = item.get("items") or []
            if children:
                label = str(item.get("label", "")).strip()
                if label:
                    menu.addSection(label)
                self._add_group_items(menu, children)
                continue

            self._add_action_item(menu, item)

    def set_items(self, items: Sequence[Any] | None) -> None:
        self.clear()
        self._actions.clear()
        self._items = list(items or [])
        self._add_group_items(self, self._items)

    def popup_below(
        self,
        widget: QWidget,
        align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft,
        x_offset: int = 0,
        y_offset: int = 6,
    ) -> None:
        pos = widget.mapToGlobal(QPoint(0, widget.height() + y_offset))
        if align == Qt.AlignmentFlag.AlignRight:
            pos.setX(pos.x() + widget.width() - self.sizeHint().width())
        pos.setX(pos.x() + x_offset)
        self.popup(pos)

    def popup_at_cursor(self) -> None:
        self.popup(QCursor.pos())


class DemoWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("PrimeMenu Demo")
        self.setMinimumSize(500, 300)
        self.setStyleSheet("background-color: #1e1e21;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        self.status_label = QLabel("Select an action from the menu.")
        self.status_label.setStyleSheet("color: #eef2f8; font-size: 13px;")
        layout.addWidget(self.status_label)

        self.open_button = QPushButton("Open Menu")
        layout.addWidget(self.open_button)

        self.menu = PrimeMenu(
            items=[
                {
                    "label": "File",
                    "items": [
                        {"label": "New", "command": lambda: self._set_status("New clicked")},
                        {"label": "Open", "command": lambda: self._set_status("Open clicked")},
                        {"separator": True},
                        {"label": "Archived", "disabled": True},
                    ],
                },
                {"separator": True},
                {"label": "Refresh", "command": lambda: self._set_status("Refresh clicked")},
                {"label": "Close", "command": self.close},
            ],
            parent=self,
        )
        self.menu.item_triggered.connect(self._on_item_triggered)
        self.open_button.clicked.connect(lambda: self.menu.popup_below(self.open_button))

        layout.addStretch(1)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _on_item_triggered(self, item: dict[str, Any]) -> None:
        label = str(item.get("label", "")).strip()
        if label:
            self.status_label.setText(f"Triggered: {label}")


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = DemoWindow()
    window.show()

    sys.exit(app.exec())
