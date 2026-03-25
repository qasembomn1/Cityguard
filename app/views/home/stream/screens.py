from __future__ import annotations

import os
import re
from math import isqrt
from typing import Dict, List, Optional

from PySide6.QtCore import QMimeData, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QColor, QDrag, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models.camera import Camera
from app.models.screen import ScreenResponse
from app.store.home.stream.screen_store import ScreenStore
from app.ui.confirm_dialog import PrimeConfirmDialog
from app.ui.dialog import PrimeDialog
from app.ui.toast import show_toast_message


_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../resources/icons")
)

_SCREEN_SIZES = [2, 3, 4, 5, 6, 7, 8]
_SCREEN_CARD_WIDTH = 400
_SCREEN_CARD_HEIGHT = 500

def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


def _camera_ip(camera: Camera) -> str:
    return str(camera.camera_ip or "").strip()


def _screen_created_at(screen: ScreenResponse) -> str:
    if screen.created_at is None:
        return "No date"
    return screen.created_at.strftime("%b %d, %Y")


def _screen_total_slots(screen: ScreenResponse) -> int:
    size = _screen_grid_size(screen)
    return size * size


def _screen_assigned_count(screen: ScreenResponse) -> int:
    return len(screen.cameras)


def _screen_grid_size(screen: ScreenResponse) -> int:
    raw = screen.screen_type
    if isinstance(raw, str):
        matches = re.findall(r"\d+", raw)
        if len(matches) >= 2 and matches[0] == matches[1]:
            raw = matches[0]
        elif len(matches) == 1:
            raw = matches[0]

    try:
        size = int(raw)
    except (TypeError, ValueError):
        size = 0

    if 2 <= size <= 8:
        return size

    if size > 8:
        root = isqrt(size)
        if root * root == size and 2 <= root <= 8:
            return root

    if screen.cameras:
        highest_index = max((item.index for item in screen.cameras), default=-1)
        if highest_index >= 0:
            slots = highest_index + 1
            root = isqrt(slots)
            if root * root == slots and 2 <= root <= 8:
                return root
            while root * root < slots:
                root += 1
            return max(2, min(8, root))

    return 2


def _screen_camera_names(screen: ScreenResponse, limit: int = 4) -> tuple[list[str], int]:
    names = [
        item.name.strip() if item.name.strip() else f"Camera {item.camera_id}"
        for item in screen.cameras
    ]
    visible = names[:limit]
    hidden = max(0, len(names) - len(visible))
    return visible, hidden


class CameraDragList(QListWidget):
    cameraActivated = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

    def set_cameras(self, cameras: List[Camera]) -> None:
        self.clear()
        for camera in sorted(cameras, key=lambda item: item.name.lower()):
            item = QListWidgetItem(f"{camera.name}   [{_camera_ip(camera)}]")
            item.setData(Qt.ItemDataRole.UserRole, camera.id)
            self.addItem(item)

    def startDrag(self, supported_actions) -> None:  # type: ignore[override]
        item = self.currentItem()
        if item is None:
            return
        camera_id = item.data(Qt.ItemDataRole.UserRole)
        if camera_id is None:
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(str(camera_id))
        drag.setMimeData(mime)

        pixmap = QPixmap(200, 34)
        pixmap.fill(QColor("#1d4ed8"))
        painter = QPainter(pixmap)
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, item.text())
        painter.end()
        drag.setPixmap(pixmap)
        drag.exec(Qt.DropAction.CopyAction)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        camera_id = item.data(Qt.ItemDataRole.UserRole)
        if camera_id is not None:
            self.cameraActivated.emit(int(camera_id))


class ScreenSlotCard(QFrame):
    dropCamera = Signal(int, int)
    swapRequested = Signal(int, int)
    removeRequested = Signal(int)

    def __init__(self, index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.index = index
        self.camera: Optional[Camera] = None
        self._drag_start_pos: Optional[QPoint] = None
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self.slot_label = QLabel(f"Slot {self.index + 1}")
        self.slot_label.setObjectName("slotLabel")
        top.addWidget(self.slot_label)
        top.addStretch()

        self.remove_btn = QToolButton()
        self.remove_btn.setToolTip("Remove camera")
        self.remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_btn.clicked.connect(lambda: self.removeRequested.emit(self.index))
        close_icon = _icon_path("close.svg")
        if os.path.isfile(close_icon):
            from PySide6.QtGui import QIcon

            self.remove_btn.setIcon(QIcon(close_icon))
        else:
            self.remove_btn.setText("X")
        top.addWidget(self.remove_btn)
        root.addLayout(top)

        self.camera_label = QLabel("Drop camera")
        self.camera_label.setObjectName("cameraTitle")
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.camera_label, 1)

        self.meta_label = QLabel("Empty")
        self.meta_label.setObjectName("cameraMeta")
        self.meta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.meta_label)

        self._apply_style()

    def set_camera(self, camera: Optional[Camera]) -> None:
        self.camera = camera
        if camera is None:
            self.camera_label.setText("Drop camera")
            self.meta_label.setText(f"#{self.index + 1}")
        else:
            self.camera_label.setText(camera.name)
            self.meta_label.setText(_camera_ip(camera) or f"Camera #{camera.id}")
        self._apply_style()

    def _apply_style(self) -> None:
        filled = self.camera is not None
        self.remove_btn.setVisible(filled)
        if filled:
            self.setStyleSheet(
                """
                QFrame {
                    background: #182131;
                    border: 1px solid #2f6ff0;
                    border-radius: 12px;
                }
                QLabel#slotLabel {
                    color: #bfdbfe;
                    font-size: 11px;
                    font-weight: 700;
                }
                QLabel#cameraTitle {
                    color: #f8fafc;
                    font-size: 13px;
                    font-weight: 700;
                }
                QLabel#cameraMeta {
                    color: #93c5fd;
                    font-size: 11px;
                }
                QToolButton {
                    background: rgba(15, 23, 42, 0.9);
                    border: 1px solid #3b4a63;
                    border-radius: 8px;
                    color: #e5e7eb;
                    padding: 4px;
                }
                QToolButton:hover {
                    background: #263246;
                }
                """
            )
            return

        self.setStyleSheet(
            """
            QFrame {
                background: #15181c;
                border: 1px dashed #374151;
                border-radius: 12px;
            }
            QLabel#slotLabel {
                color: #9ca3af;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#cameraTitle {
                color: #d1d5db;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#cameraMeta {
                color: #6b7280;
                font-size: 11px;
            }
            QToolButton {
                background: transparent;
                border: none;
                color: transparent;
            }
            """
        )

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self.camera is None or self._drag_start_pos is None:
            super().mouseMoveEvent(event)
            return
        if (event.position().toPoint() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            super().mouseMoveEvent(event)
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-screen-slot-index", str(self.index).encode("utf-8"))
        drag.setMimeData(mime)
        pixmap = QPixmap(180, 34)
        pixmap.fill(QColor("#0f172a"))
        painter = QPainter(pixmap)
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, self.camera.name)
        painter.end()
        drag.setPixmap(pixmap)
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_start_pos = None
        super().mouseMoveEvent(event)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasFormat("application/x-screen-slot-index") or event.mimeData().hasText():
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasFormat("application/x-screen-slot-index"):
            raw = bytes(event.mimeData().data("application/x-screen-slot-index")).decode("utf-8")
            try:
                source_index = int(raw)
            except ValueError:
                event.ignore()
                return
            if source_index != self.index:
                self.swapRequested.emit(source_index, self.index)
            event.acceptProposedAction()
            return

        if event.mimeData().hasText():
            try:
                camera_id = int(event.mimeData().text())
            except ValueError:
                event.ignore()
                return
            self.dropCamera.emit(self.index, camera_id)
            event.acceptProposedAction()
            return

        event.ignore()


class ScreenEditorDialog(PrimeDialog):
    def __init__(
        self,
        cameras: List[Camera],
        screen: Optional[ScreenResponse] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            title="Edit Screen" if screen is not None else "Create Screen",
            parent=parent,
            width=1280,
            height=820,
            show_footer=True,
            ok_text="Update Screen" if screen is not None else "Create Screen",
            cancel_text="Cancel",
        )
        self._screen = screen
        self._cameras = list(cameras)
        self._camera_map: Dict[int, Camera] = {camera.id: camera for camera in self._cameras}
        self._slots: List[ScreenSlotCard] = []
        self.payload: Optional[dict] = None

        self.ok_button.clicked.disconnect()
        self.ok_button.clicked.connect(self._save)

        self.content_widget = QWidget()
        self.content_widget.setObjectName("screenEditorContent")
        root = QVBoxLayout(self.content_widget)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        body = QHBoxLayout()
        body.setSpacing(14)
        root.addLayout(body, 1)

        left_panel = QFrame()
        left_panel.setObjectName("editorPanel")
        left_panel.setMaximumWidth(340)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)

        left_layout.addWidget(QLabel("Screen Type"))
        self.screen_type_combo = QComboBox()
        for size in _SCREEN_SIZES:
            self.screen_type_combo.addItem(f"{size}x{size} Grid", size)
        left_layout.addWidget(self.screen_type_combo)

        self.is_main_checkbox = QCheckBox("Set as main screen")
        is_already_main = screen is not None and bool(screen.is_main)
        self.is_main_checkbox.setChecked(is_already_main or False)
        if is_already_main:
            self.is_main_checkbox.setEnabled(False)
        left_layout.addWidget(self.is_main_checkbox)

        camera_header = QHBoxLayout()
        camera_header.addWidget(QLabel("Available Cameras"))
        camera_header.addStretch()
        self.camera_count = QLabel("0")
        self.camera_count.setObjectName("cameraBadge")
        camera_header.addWidget(self.camera_count)
        left_layout.addLayout(camera_header)

        self.camera_list = CameraDragList()
        self.camera_list.set_cameras(self._cameras)
        self.camera_list.cameraActivated.connect(self._assign_to_first_empty)
        left_layout.addWidget(self.camera_list, 1)
        body.addWidget(left_panel)

        right_panel = QFrame()
        right_panel.setObjectName("editorPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(14, 14, 14, 14)
        right_layout.setSpacing(10)

        top = QHBoxLayout()
        top.addWidget(QLabel("Grid Layout"))
        top.addStretch()
        self.assigned_label = QLabel("0 / 0 assigned")
        self.assigned_label.setObjectName("cameraBadge")
        top.addWidget(self.assigned_label)
        right_layout.addLayout(top)

        info = QLabel("Drag cameras into slots, or double click a camera to place it in the next empty slot.")
        info.setWordWrap(True)
        info.setObjectName("subtleLabel")
        right_layout.addWidget(info)

        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_host = QWidget()
        self.grid_layout = QGridLayout(self.grid_host)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(10)
        self.grid_scroll.setWidget(self.grid_host)
        right_layout.addWidget(self.grid_scroll, 1)
        body.addWidget(right_panel, 1)
        self.set_content(self.content_widget, fill_height=True)

        self._apply_style()
        self.camera_count.setText(str(len(self._cameras)))

        initial_size = _screen_grid_size(screen) if screen is not None else 2
        index = max(0, _SCREEN_SIZES.index(initial_size) if initial_size in _SCREEN_SIZES else 0)
        self.screen_type_combo.setCurrentIndex(index)
        self.screen_type_combo.currentIndexChanged.connect(self._on_screen_size_changed)
        self._rebuild_grid()

        if screen is not None:
            for assignment in screen.cameras:
                if assignment.index < 0 or assignment.index >= len(self._slots):
                    continue
                camera = self._camera_map.get(assignment.camera_id)
                if camera is None:
                    camera = Camera(
                        id=assignment.camera_id,
                        name=assignment.name or f"Camera {assignment.camera_id}",
                        camera_ip=assignment.camera_ip,
                    )
                    self._camera_map[camera.id] = camera
                self._slots[assignment.index].set_camera(camera)
        self._update_assigned_label()

    def _apply_style(self) -> None:
        self.content_widget.setStyleSheet(
            """
            QWidget#screenEditorContent {
                background: transparent;
                color: #f5f7fb;
            }
            QFrame#editorPanel {
                background: #181b1f;
                border: 1px solid #2d333b;
                border-radius: 14px;
            }
            QLabel {
                color: #f5f7fb;
            }
            QLabel#subtleLabel {
                color: #9ca3af;
                font-size: 12px;
            }
            QLabel#cameraBadge {
                background: #111827;
                border: 1px solid #374151;
                border-radius: 10px;
                color: #d1d5db;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 700;
            }
            QComboBox, QListWidget {
                background: #12161a;
                border: 1px solid #2e3742;
                border-radius: 10px;
                color: #f5f7fb;
                padding: 8px;
            }
            QCheckBox {
                color: #f5f7fb;
                spacing: 8px;
                padding: 4px 0 2px 0;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #3b4756;
                background: #12161a;
            }
            QCheckBox::indicator:checked {
                background: #2563eb;
                border: 1px solid #3b82f6;
            }
            QListWidget::item {
                padding: 9px 6px;
                border-bottom: 1px solid #242b33;
            }
            QListWidget::item:selected {
                background: #1d4ed8;
            }
            QPushButton {
                background: #2a3038;
                border: 1px solid #3a4350;
                border-radius: 10px;
                color: #f5f7fb;
                font-weight: 700;
                padding: 10px 16px;
            }
            QPushButton:hover {
                background: #374151;
            }
            QPushButton#primaryButton {
                background: #2563eb;
                border: 1px solid #3b82f6;
            }
            QPushButton#primaryButton:hover {
                background: #1d4ed8;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            """
        )

    def _slot_minimum_width(self) -> int:
        size = self._grid_size()
        if size >= 7:
            return 110
        if size >= 5:
            return 130
        return 170

    def _slot_minimum_height(self) -> int:
        size = self._grid_size()
        if size >= 7:
            return 92
        if size >= 5:
            return 102
        return 118

    def _grid_size(self) -> int:
        return int(self.screen_type_combo.currentData() or 2)

    def _on_screen_size_changed(self) -> None:
        self._rebuild_grid(preserve_existing=True)

    def _rebuild_grid(self, preserve_existing: bool = False) -> None:
        existing_by_index: Dict[int, Optional[Camera]] = {}
        if preserve_existing:
            existing_by_index = {slot.index: slot.camera for slot in self._slots}

        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._slots.clear()
        grid_size = self._grid_size()
        total = grid_size * grid_size

        for index in range(total):
            slot = ScreenSlotCard(index)
            slot.setMinimumSize(self._slot_minimum_width(), self._slot_minimum_height())
            slot.dropCamera.connect(self._drop_camera)
            slot.swapRequested.connect(self._swap_slots)
            slot.removeRequested.connect(self._remove_camera)
            slot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            preserved = existing_by_index.get(index)
            if preserved is not None:
                slot.set_camera(preserved)
            self._slots.append(slot)
            self.grid_layout.addWidget(slot, index // grid_size, index % grid_size)

        self._update_assigned_label()

    def _assign_to_first_empty(self, camera_id: int) -> None:
        for idx, slot in enumerate(self._slots):
            if slot.camera is None:
                self._drop_camera(idx, camera_id)
                return
        show_toast_message(self, "info", "Grid Full", "All grid slots are already assigned.")

    def _remove_existing_camera(self, camera_id: int) -> None:
        for slot in self._slots:
            if slot.camera is not None and slot.camera.id == camera_id:
                slot.set_camera(None)
                break

    def _drop_camera(self, slot_index: int, camera_id: int) -> None:
        if slot_index < 0 or slot_index >= len(self._slots):
            return
        camera = self._camera_map.get(camera_id)
        if camera is None:
            return
        self._remove_existing_camera(camera_id)
        self._slots[slot_index].set_camera(camera)
        self._update_assigned_label()

    def _swap_slots(self, from_index: int, to_index: int) -> None:
        if from_index < 0 or to_index < 0:
            return
        if from_index >= len(self._slots) or to_index >= len(self._slots):
            return
        left = self._slots[from_index].camera
        right = self._slots[to_index].camera
        self._slots[from_index].set_camera(right)
        self._slots[to_index].set_camera(left)
        self._update_assigned_label()

    def _remove_camera(self, slot_index: int) -> None:
        if slot_index < 0 or slot_index >= len(self._slots):
            return
        self._slots[slot_index].set_camera(None)
        self._update_assigned_label()

    def _update_assigned_label(self) -> None:
        assigned = len([slot for slot in self._slots if slot.camera is not None])
        self.assigned_label.setText(f"{assigned} / {len(self._slots)} assigned")

    def _save(self) -> None:
        cameras = [
            {"camera_id": slot.camera.id, "index": index}
            for index, slot in enumerate(self._slots)
            if slot.camera is not None
        ]
        payload = {
            "screen_type": self._grid_size(),
            "is_main": self.is_main_checkbox.isChecked(),
            "cameras": cameras,
        }
        if self._screen is not None:
            payload["screen_id"] = self._screen.id
        self.payload = payload
        self.accept()


class ScreenCard(QFrame):
    loadRequested = Signal(int)
    editRequested = Signal(int)
    deleteRequested = Signal(int)

    def __init__(self, screen: ScreenResponse, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.screen = screen
        self.setObjectName("screenCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(_SCREEN_CARD_WIDTH)
        self.setFixedHeight(_SCREEN_CARD_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        assigned_count = _screen_assigned_count(screen)
        grid_size = _screen_grid_size(screen)
        total_slots = _screen_total_slots(screen)




        hero = QFrame()
        hero.setObjectName("previewHero")
        hero.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(14, 14, 14, 14)
        hero_layout.setSpacing(12)

        hero_top = QHBoxLayout()
        hero_top.setContentsMargins(0, 0, 0, 0)
        hero_top.setSpacing(8)

        occupancy_chip = QLabel(f"{assigned_count}/{total_slots} Occupied")
        occupancy_chip.setObjectName("heroChip")
        hero_top.addWidget(occupancy_chip)

        if screen.is_main:
            main_chip = QLabel("Main Screen")
            main_chip.setObjectName("heroMainChip")
            hero_top.addWidget(main_chip)

        hero_top.addStretch()

        date_chip = QLabel(_screen_created_at(screen))
        date_chip.setObjectName("heroGhostChip")
        hero_top.addWidget(date_chip)
        hero_layout.addLayout(hero_top)

        preview = QFrame()
        preview.setObjectName("previewFrame")
        preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        preview_layout = QGridLayout(preview)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(6 if grid_size <= 4 else 4)
        assigned = {item.index for item in screen.cameras}
        total = total_slots
        cell_size = 40 if grid_size <= 3 else 30 if grid_size <= 5 else 22
        for idx in range(total):
            cell = QLabel(str(idx + 1) if idx in assigned else "")
            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.setMinimumSize(cell_size, cell_size)
            cell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            cell.setStyleSheet(self._preview_cell_style(idx in assigned, grid_size))
            preview_layout.addWidget(cell, idx // grid_size, idx % grid_size)
        for row in range(grid_size):
            preview_layout.setRowStretch(row, 1)
            preview_layout.setColumnStretch(row, 1)
        hero_layout.addWidget(preview, 1)
        root.addWidget(hero, 1)

        chips_row = QHBoxLayout()
        chips_row.setContentsMargins(0, 0, 0, 0)
        chips_row.setSpacing(8)


        camera_section = QVBoxLayout()
        camera_section.setContentsMargins(0, 0, 0, 0)
        camera_section.setSpacing(8)


        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 4, 0, 0)
        buttons.setSpacing(8)

        load_btn = QPushButton("Open")
        load_btn.setObjectName("primaryButton")
        load_btn.clicked.connect(lambda: self.loadRequested.emit(self.screen.id))
        buttons.addWidget(load_btn)

        edit_btn = self._icon_action_button("edit.svg", "Edit screen", "#3578f6", "#4e8cff")
        edit_btn.clicked.connect(lambda: self.editRequested.emit(self.screen.id))
        buttons.addWidget(edit_btn)

        delete_btn = self._icon_action_button("trash.svg", "Delete screen", "#ef4444", "#ff6464")
        delete_btn.clicked.connect(lambda: self.deleteRequested.emit(self.screen.id))
        buttons.addWidget(delete_btn)
        root.addLayout(buttons)

        self.setStyleSheet(
            """
            QFrame#screenCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #161b22, stop:0.55 #11151b, stop:1 #0d1015);
                border: 1px solid #293341;
                border-radius: 20px;
            }
            QFrame#screenCard:hover {
                border: 1px solid #3b82f6;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #18202a, stop:0.55 #121922, stop:1 #0d1218);
            }
            QFrame#previewHero {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(29, 78, 216, 0.18), stop:1 rgba(15, 23, 42, 0.28));
                border: 1px solid #2b3645;
                border-radius: 18px;
            }
            QFrame#previewFrame {
                background: #091019;
                border: 1px solid #263345;
                border-radius: 14px;
                padding: 10px;
            }
            QLabel#cardEyebrow {
                color: #60a5fa;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.18em;
            }
            QLabel#cardIdChip {
                background: rgba(15, 23, 42, 0.95);
                border: 1px solid #334155;
                border-radius: 11px;
                color: #e2e8f0;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 800;
            }
            QLabel#cardTitle {
                color: #f8fafc;
                font-size: 21px;
                font-weight: 800;
            }
            QLabel#cardMeta {
                color: #94a3b8;
                font-size: 12px;
            }
            QLabel#sectionLabel {
                color: #cbd5e1;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.08em;
            }
            QLabel#heroChip {
                background: rgba(37, 99, 235, 0.22);
                border: 1px solid #315996;
                border-radius: 10px;
                color: #bfdbfe;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#heroGhostChip {
                background: rgba(15, 23, 42, 0.72);
                border: 1px solid #334155;
                border-radius: 10px;
                color: #cbd5e1;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#heroMainChip {
                background: rgba(34, 197, 94, 0.16);
                border: 1px solid rgba(74, 222, 128, 0.38);
                border-radius: 10px;
                color: #bbf7d0;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 800;
            }
            QLabel#infoChip {
                background: rgba(15, 23, 42, 0.72);
                border: 1px solid #334155;
                border-radius: 10px;
                color: #dbe4ef;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#cameraChip {
                background: rgba(96, 165, 250, 0.16);
                border: 1px solid #325985;
                border-radius: 10px;
                color: #dbeafe;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#cameraChipMuted {
                background: rgba(15, 23, 42, 0.82);
                border: 1px solid #3a4656;
                border-radius: 10px;
                color: #cbd5e1;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton {
                background: #1f2937;
                border: 1px solid #334155;
                border-radius: 10px;
                color: #f5f7fb;
                font-weight: 700;
                padding: 9px 12px;
            }
            QPushButton:hover {
                background: #304156;
            }
            QPushButton#primaryButton {
                background: #2563eb;
                border: 1px solid #3b82f6;
            }
            QPushButton#primaryButton:hover {
                background: #1d4ed8;
            }
            QPushButton#dangerButton {
                background: #3a1f24;
                border: 1px solid #6f2a34;
            }
            QPushButton#dangerButton:hover {
                background: #51272f;
            }
            """
        )

    def _icon_action_button(self, icon_name: str, tooltip: str, bg: str, border: str, size: int = 34) -> QToolButton:
        btn = QToolButton()
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(size, size)
        btn.setStyleSheet(
            f"""
            QToolButton {{
                background: {bg};
                border: 1px solid {border};
                border-radius: {size // 2}px;
            }}
            QToolButton:hover {{
                border-color: #f8fafc;
            }}
            QToolButton:disabled {{
                background: #2b2d33;
                border-color: #3b3f47;
            }}
            """
        )
        icon_file = _icon_path(icon_name)
        if os.path.isfile(icon_file):
            icon_px = max(12, size - 16)
            btn.setIcon(QIcon(icon_file))
            btn.setIconSize(QSize(icon_px, icon_px))
        return btn

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.loadRequested.emit(self.screen.id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _preview_cell_style(self, active: bool, grid_size: int) -> str:
        if active:
            return (
                "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                "stop:0 #3b82f6, stop:1 #1d4ed8);"
                "border: 1px solid #7dd3fc;"
                "border-radius: 8px;"
                "color: #eff6ff;"
                f"font-size: {'12px' if grid_size <= 4 else '10px'};"
                "font-weight: 800;"
            )
        return (
            "background: rgba(15, 23, 42, 0.9);"
            "border: 1px solid #233040;"
            "border-radius: 8px;"
            "color: transparent;"
        )


class ScreenManagerWidget(QWidget):
    loadRequested = Signal(int)

    def __init__(
        self,
        screen_store: ScreenStore,
        cameras: List[Camera],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.screen_store = screen_store
        self.cameras = list(cameras)
        self._card_columns = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        

        toolbar = QHBoxLayout()
        title = QLabel("Camera Screens")
        title.setObjectName("pageTitle")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search screens...")
        self.search_edit.setMaximumWidth(350)

        self.search_edit.textChanged.connect(self.refresh_cards)
        toolbar.addWidget(self.search_edit)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.reload)
        toolbar.addWidget(refresh_btn)

        new_btn = QPushButton("New Screen")
        new_btn.setObjectName("primaryButton")
        new_btn.clicked.connect(lambda: self._open_editor(None))
        toolbar.addWidget(new_btn)
        root.addLayout(toolbar)

        self.meta_label = QLabel("")
        self.meta_label.setObjectName("metaLabel")
        root.addWidget(self.meta_label)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_host = QWidget()
        self.cards_layout = QGridLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.cards_scroll.setWidget(self.cards_host)
        root.addWidget(self.cards_scroll, 1)

        self.setStyleSheet(
            """
            QWidget {
                color: #f5f7fb;
            }
            QLabel#pageTitle {
                font-size: 20px;
                font-weight: 800;
            }
            QLabel#metaLabel {
                color: #9ca3af;
                font-size: 12px;
            }
            QLineEdit {
                background: #13171b;
                border: 1px solid #2d3743;
                border-radius: 10px;
                color: #f5f7fb;
                padding: 10px 12px;
            }
            QPushButton {
                background: #253041;
                border: 1px solid #394656;
                border-radius: 10px;
                color: #f5f7fb;
                font-weight: 700;
                padding: 10px 14px;
            }
            QPushButton:hover {
                background: #314156;
            }
            QPushButton#primaryButton {
                background: #2563eb;
                border: 1px solid #3b82f6;
            }
            QPushButton#primaryButton:hover {
                background: #1d4ed8;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            """
        )

        self.reload()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.refresh_cards()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        columns = self._column_count()
        if columns != self._card_columns:
            self.refresh_cards()

    def _clear_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _column_count(self) -> int:
        width = self.cards_scroll.viewport().width()
        if width <= 0:
            return 1
        spacing = max(0, self.cards_layout.horizontalSpacing())
        slot_width = _SCREEN_CARD_WIDTH + spacing
        return max(1, min(4, (width + spacing) // slot_width))

    def _filtered_screens(self) -> List[ScreenResponse]:
        query = self.search_edit.text().strip().lower()
        if not query:
            return list(self.screen_store.screens)
        return [
            screen
            for screen in self.screen_store.screens
            if query in str(screen.id).lower() or query in str(screen.screen_type).lower()
        ]

    def reload(self) -> None:
        try:
            self.screen_store.load()
        except Exception as exc:
            show_toast_message(self, "error", "Screen Error", str(exc))
        self.refresh_cards()

    def refresh_cards(self, *_args) -> None:
        columns = self._column_count()
        self._clear_cards()
        screens = self._filtered_screens()
        self.meta_label.setText(f"{len(screens)} screen(s)")
        self._card_columns = columns
        if not screens:
            empty = QLabel("No screens found. Create a screen to save a reusable live view layout.")
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                "background:#14181c;border:1px dashed #334155;border-radius:14px;"
                "color:#9ca3af;padding:32px;font-size:13px;"
            )
            self.cards_layout.addWidget(empty, 0, 0)
            return

        for idx, screen in enumerate(screens):
            card = ScreenCard(screen)
            card.loadRequested.connect(self.loadRequested.emit)
            card.editRequested.connect(self._open_editor_by_id)
            card.deleteRequested.connect(self._delete_screen)
            self.cards_layout.addWidget(card, idx // columns, idx % columns)
        for column in range(columns):
            self.cards_layout.setColumnStretch(column, 0)
            self.cards_layout.setColumnMinimumWidth(column, _SCREEN_CARD_WIDTH)
    def _screen_by_id(self, screen_id: int) -> Optional[ScreenResponse]:
        return self.screen_store.get_screen(screen_id)

    def _open_editor_by_id(self, screen_id: int) -> None:
        self._open_editor(self._screen_by_id(screen_id))

    def _open_editor(self, screen: Optional[ScreenResponse]) -> None:
        dialog = ScreenEditorDialog(self.cameras, screen, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.payload is None:
            return
        try:
            if screen is None:
                created = self.screen_store.create_screen(dialog.payload)
                show_toast_message(self, "success", "Screen Saved", f"Screen #{created.id} created successfully.")
            else:
                updated = self.screen_store.update_screen(dialog.payload)
                show_toast_message(self, "success", "Screen Saved", f"Screen #{updated.id} updated successfully.")
        except Exception as exc:
            show_toast_message(self, "error", "Screen Error", str(exc))
            return
        self.refresh_cards()

    def _delete_screen(self, screen_id: int) -> None:
        screen = self._screen_by_id(screen_id)
        if screen is None:
            return
        confirmed = PrimeConfirmDialog.ask(
            parent=self,
            title="Delete Screen",
            message=f"Delete screen #{screen.id}?",
            ok_text="Delete",
            cancel_text="Cancel",
        )
        if not confirmed:
            return
        try:
            self.screen_store.delete_screen(screen_id)
        except Exception as exc:
            show_toast_message(self, "error", "Screen Error", str(exc))
            return
        self.refresh_cards()


class ScreensManagerDialog(PrimeDialog):
    def __init__(
        self,
        screen_store: ScreenStore,
        cameras: List[Camera],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            title="Camera Screens",
            parent=parent,
            width=1280,
            height=860,
            show_footer=False,
        )
        self.set_header_visible(False)
        self.selected_screen_id: Optional[int] = None

        self.manager = ScreenManagerWidget(screen_store, cameras, self)
        self.manager.loadRequested.connect(self._accept_screen)
        self.set_content(self.manager, fill_height=True)

    def _accept_screen(self, screen_id: int) -> None:
        self.selected_screen_id = screen_id
        self.accept()
