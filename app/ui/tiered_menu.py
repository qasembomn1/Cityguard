from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from typing import Any

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

if __package__ in (None, ""):
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from app.ui.menu import PrimeMenu


class PrimeTieredMenu(PrimeMenu):
    def __init__(
        self,
        items: Sequence[Any] | None = None,
        title: str = "",
        parent: QWidget | None = None,
        radius: int = 10,
        minimum_width: int = 220,
    ) -> None:
        self._submenus: list[PrimeTieredMenu] = []
        super().__init__(
            items=None,
            title=title,
            parent=parent,
            radius=radius,
            minimum_width=minimum_width,
        )
        if items is not None:
            self.set_items(items)

    def _re_emit_item_triggered(self, item: object) -> None:
        self.item_triggered.emit(item)

    def _add_tiered_items(self, menu: PrimeMenu, items: Sequence[Any]) -> None:
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
                if not label:
                    self._add_tiered_items(menu, children)
                    continue

                submenu = PrimeTieredMenu(
                    items=children,
                    title=label,
                    parent=menu,
                    radius=self._radius,
                    minimum_width=self.minimumWidth(),
                )
                submenu.item_triggered.connect(self._re_emit_item_triggered)
                self._submenus.append(submenu)

                action = menu.addMenu(submenu)
                self._apply_action_properties(action, item, checkable=False)
                submenu.setEnabled(action.isEnabled())
                continue

            self._add_action_item(menu, item)

    def set_items(self, items: Sequence[Any] | None) -> None:
        self.clear()
        self._actions.clear()
        self._submenus.clear()
        self._items = list(items or [])
        self._add_tiered_items(self, self._items)


class DemoWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("PrimeTieredMenu Demo")
        self.setMinimumSize(440, 300)
        self.setStyleSheet("background-color: #1e1e21;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        self.status_label = QLabel("Open the tiered menu to test nested actions.")
        self.status_label.setStyleSheet("color: #eef2f8; font-size: 13px;")
        layout.addWidget(self.status_label)

        self.open_button = QPushButton("Open Tiered Menu")
        layout.addWidget(self.open_button)

        self.menu = PrimeTieredMenu(
            items=[
                {
                    "label": "Create",
                    "items": [
                        {"label": "Project", "command": lambda: self._set_status("Create > Project")},
                        {
                            "label": "Team",
                            "items": [
                                {"label": "Engineering", "command": lambda: self._set_status("Create > Team > Engineering")},
                                {"label": "Operations", "command": lambda: self._set_status("Create > Team > Operations")},
                            ],
                        },
                    ],
                },
                {
                    "label": "Share",
                    "items": [
                        {"label": "Copy Link", "command": lambda: self._set_status("Share > Copy Link")},
                        {"label": "Invite User", "command": lambda: self._set_status("Share > Invite User")},
                    ],
                },
                {"separator": True},
                {"label": "Delete", "disabled": True},
            ],
            parent=self,
        )
        self.menu.item_triggered.connect(self._on_item_triggered)
        self.open_button.clicked.connect(lambda: self.menu.popup_below(self.open_button))

        layout.addStretch(1)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _on_item_triggered(self, item: object) -> None:
        if not isinstance(item, dict):
            return
        label = str(item.get("label", "")).strip()
        if label:
            self.status_label.setText(f"Triggered: {label}")


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = DemoWindow()
    window.show()

    sys.exit(app.exec())
