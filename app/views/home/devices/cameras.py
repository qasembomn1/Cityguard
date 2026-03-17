from __future__ import annotations
import base64
import json
import math
import sys
import os
from dataclasses import asdict
from typing import Any, Dict, List, Optional
from app.models.camera import Camera, CameraType
from app.store.home.devices.camera_store import CameraStore
from app.store.home.user.department_store import DepartmentStore
from app.api.api_service import ApiService
from app.utils.list import extract_dict_list
from app.store.home.devices.access_control_store import AccessControlStore
from app.store.home.devices.client_store import ClientStore
from app.store.home.devices.camera_type_store import CameraTypeStore
from app.store.auth import AuthStore

from PySide6.QtCore import QPointF, Qt, QTimer, Signal, QSize,QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from app.ui.button import PrimeButton
from app.ui.table import PrimeDataTable, PrimeTableColumn
from app.constants._init_ import Constants

_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)



if __package__ in (None, ""):
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../"))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)



class MapDialog(QDialog):
    def __init__(self, lat: float = 36.1901, lng: float = 44.0091, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Camera Location")
        self.resize(700, 420)
        self.selected = {"lat": lat, "lng": lng}

        layout = QVBoxLayout(self)
        info = QLabel(
            "Map integration placeholder. In a real app, replace this widget with "
            "QWebEngineView + Leaflet / OpenStreetMap."
        )
        info.setWordWrap(True)
        info.setStyleSheet("padding: 12px; background: #1f2937; border-radius: 8px;")
        layout.addWidget(info)

        form = QFormLayout()
        self.lat_edit = QLineEdit(str(lat))
        self.lng_edit = QLineEdit(str(lng))
        form.addRow("Latitude", self.lat_edit)
        form.addRow("Longitude", self.lng_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        try:
            self.selected = {
                "lat": float(self.lat_edit.text().strip()),
                "lng": float(self.lng_edit.text().strip()),
            }
        except ValueError:
            QMessageBox.warning(self, "Invalid", "Please enter valid coordinates.")
            return
        super().accept()


class TextEditDialog(QDialog):
    def __init__(self, title: str, initial_text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(700, 400)
        self.text_value = initial_text

        layout = QVBoxLayout(self)
        self.editor = QTextEdit()
        self.editor.setPlainText(initial_text)
        layout.addWidget(self.editor)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        self.text_value = self.editor.toPlainText()
        self.accept()


class ScanCameraResultsDialog(QDialog):
    def __init__(self, cameras: List[Dict[str, Any]], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.selected_camera: Optional[Dict[str, Any]] = None
        self._cameras = cameras

        self.setWindowTitle("Scanned Cameras")
        self.resize(760, 480)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        info_label = QLabel(
            f"{len(cameras)} camera(s) found on the network. Choose one to fill the form."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #cbd5e1;")
        root.addWidget(info_label)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by IP address or manufacturer...")
        self.search_edit.textChanged.connect(self._on_search_changed)
        root.addWidget(self.search_edit)

        self.table = PrimeDataTable(page_size=8, page_size_options=[8, 16, 32], row_height=54, show_footer=True)
        self.table.set_columns(
            [
                PrimeTableColumn("ip_address", "IP Address", stretch=True),
                PrimeTableColumn(
                    "port",
                    "Port",
                    searchable=False,
                    width=96,
                    alignment=Qt.AlignmentFlag.AlignCenter,
                ),
                PrimeTableColumn("manufacturer", "Manufacturer", stretch=True),
                PrimeTableColumn(
                    "action",
                    "",
                    sortable=False,
                    searchable=False,
                    width=124,
                    alignment=Qt.AlignmentFlag.AlignCenter,
                    widget_factory=self._build_use_button,
                ),
            ]
        )
        self.table.set_rows(self._cameras)
        root.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addStretch(1)

        close_btn = PrimeButton("Close", "secondary", size="sm")
        close_btn.setFixedWidth(110)
        close_btn.clicked.connect(self.reject)
        footer.addWidget(close_btn)
        root.addLayout(footer)

    def _on_search_changed(self, text: str) -> None:
        self.table.set_filter_text(text)

    def _build_use_button(self, row: Dict[str, Any]) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        button = PrimeButton("Use", "primary", size="sm")
        button.setFixedWidth(92)
        button.clicked.connect(lambda checked=False, current_row=row: self._select_camera(current_row))
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)
        return wrapper

    def _select_camera(self, camera_data: Dict[str, Any]) -> None:
        self.selected_camera = camera_data
        self.accept()


def _load_frame_pixmap(frame_text: str) -> QPixmap:
    text = str(frame_text or "").strip()
    if not text:
        return QPixmap()

    candidates: list[bytes] = []
    if text.startswith("data:image/"):
        try:
            _, encoded = text.split(",", 1)
            candidates.append(base64.b64decode(encoded))
        except Exception:
            pass
    else:
        try:
            candidates.append(base64.b64decode(text))
        except Exception:
            pass

    pixmap = QPixmap()
    for payload in candidates:
        if payload and pixmap.loadFromData(payload):
            return pixmap

    if os.path.isfile(text):
        pixmap = QPixmap(text)
        if not pixmap.isNull():
            return pixmap

    return QPixmap()


def _parse_normalized_points(raw_value: str) -> list[dict[str, float]]:
    text = str(raw_value or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []

    points: list[dict[str, float]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            x = float(item.get("x", 0.0))
            y = float(item.get("y", 0.0))
        except (TypeError, ValueError):
            continue
        points.append(
            {
                "x": round(max(0.0, min(1.0, x)), 6),
                "y": round(max(0.0, min(1.0, y)), 6),
            }
        )
    return points


def _parse_line_points(raw_value: str) -> list[dict[str, float]]:
    text = str(raw_value or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except Exception:
        return []

    def _coords_to_points(values: Any) -> list[dict[str, float]]:
        if not isinstance(values, list) or len(values) != 4:
            return []
        try:
            x1, y1, x2, y2 = [float(value) for value in values]
        except (TypeError, ValueError):
            return []
        return [
            {"x": round(max(0.0, min(1.0, x1)), 6), "y": round(max(0.0, min(1.0, y1)), 6)},
            {"x": round(max(0.0, min(1.0, x2)), 6), "y": round(max(0.0, min(1.0, y2)), 6)},
        ]

    if isinstance(payload, list):
        return _coords_to_points(payload)
    if not isinstance(payload, dict):
        return []

    points: list[dict[str, float]] = []
    points.extend(_coords_to_points(payload.get("count_line")))
    points.extend(_coords_to_points(payload.get("direction_line")))
    return points[:4]


def _serialize_line_points(points: list[dict[str, float]]) -> str:
    count_line: list[float] = []
    direction_line: list[float] = []
    if len(points) >= 2:
        count_line = [
            points[0]["x"],
            points[0]["y"],
            points[1]["x"],
            points[1]["y"],
        ]
    if len(points) >= 4:
        direction_line = [
            points[2]["x"],
            points[2]["y"],
            points[3]["x"],
            points[3]["y"],
        ]
    return json.dumps(
        {
            "count_line": count_line,
            "direction_line": direction_line,
        },
        separators=(",", ":"),
    )


class RoiCanvas(QWidget):
    points_changed = Signal()

    _DEFAULT_SIZE = QSize(640, 360)
    _MAX_SIZE = QSize(800, 600)
    _POINT_RADIUS = 5
    _DRAG_RADIUS = 8

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pixmap = QPixmap()
        self._points: list[dict[str, float]] = []
        self._dragging_index: Optional[int] = None
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(self._DEFAULT_SIZE)

    def has_frame(self) -> bool:
        return not self._pixmap.isNull()

    def set_frame_text(self, frame_text: str) -> None:
        self._pixmap = _load_frame_pixmap(frame_text)
        target_size = self._DEFAULT_SIZE
        if not self._pixmap.isNull():
            target_size = self._pixmap.size().scaled(
                self._MAX_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
            )
        self.setFixedSize(target_size)
        self.setCursor(Qt.CursorShape.CrossCursor if self.has_frame() else Qt.CursorShape.ArrowCursor)
        self.update()

    def set_points(self, points: list[dict[str, float]]) -> None:
        normalized_points: list[dict[str, float]] = []
        for point in points:
            try:
                x = float(point.get("x", 0.0))
                y = float(point.get("y", 0.0))
            except (AttributeError, TypeError, ValueError):
                continue
            normalized_points.append(
                {
                    "x": round(max(0.0, min(1.0, x)), 6),
                    "y": round(max(0.0, min(1.0, y)), 6),
                }
            )
        self._points = normalized_points
        self.points_changed.emit()
        self.update()

    def clear_points(self) -> None:
        if not self._points:
            return
        self._points = []
        self._dragging_index = None
        self.points_changed.emit()
        self.update()

    def points(self) -> list[dict[str, float]]:
        return [dict(point) for point in self._points]

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#111827"))

        if not self._pixmap.isNull():
            painter.drawPixmap(self.rect(), self._pixmap)
        else:
            painter.setPen(QColor("#9ca3af"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Camera frame unavailable.",
            )

        if len(self._points) >= 2:
            path = QPainterPath()
            first = self._point_to_canvas(self._points[0])
            path.moveTo(first)
            for point in self._points[1:]:
                path.lineTo(self._point_to_canvas(point))
            if len(self._points) >= 3:
                path.closeSubpath()
                painter.fillPath(path, QColor(255, 0, 0, 76))
            painter.setPen(QPen(QColor("#ff0000"), 2))
            painter.drawPath(path)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ff0000"))
        for point in self._points:
            painter.drawEllipse(self._point_to_canvas(point), self._POINT_RADIUS, self._POINT_RADIUS)

        border_color = QColor("#475569") if self.has_frame() else QColor("#7f1d1d")
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() != Qt.MouseButton.LeftButton or not self.has_frame():
            return super().mousePressEvent(event)

        canvas_pos = event.position()
        point_index = self._find_point_at(canvas_pos.x(), canvas_pos.y())
        if point_index is not None:
            self._dragging_index = point_index
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        self._points.append(self._canvas_to_point(canvas_pos.x(), canvas_pos.y()))
        self.points_changed.emit()
        self.update()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if not self.has_frame():
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return super().mouseMoveEvent(event)

        canvas_pos = event.position()
        if self._dragging_index is not None:
            self._points[self._dragging_index] = self._canvas_to_point(canvas_pos.x(), canvas_pos.y())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.points_changed.emit()
            self.update()
            event.accept()
            return

        if self._find_point_at(canvas_pos.x(), canvas_pos.y()) is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and self._dragging_index is not None:
            self._dragging_index = None
            canvas_pos = event.position()
            if self._find_point_at(canvas_pos.x(), canvas_pos.y()) is not None:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        if self._dragging_index is None:
            self.setCursor(Qt.CursorShape.CrossCursor if self.has_frame() else Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)

    def _canvas_to_point(self, x: float, y: float) -> dict[str, float]:
        width = max(1, self.width())
        height = max(1, self.height())
        clamped_x = max(0.0, min(float(x), float(width)))
        clamped_y = max(0.0, min(float(y), float(height)))
        return {
            "x": round(clamped_x / width, 6),
            "y": round(clamped_y / height, 6),
        }

    def _point_to_canvas(self, point: dict[str, float]) -> QPointF:
        return QPointF(
            float(point.get("x", 0.0)) * self.width(),
            float(point.get("y", 0.0)) * self.height(),
        )

    def _find_point_at(self, x: float, y: float) -> Optional[int]:
        drag_radius_sq = self._DRAG_RADIUS * self._DRAG_RADIUS
        for index, point in enumerate(self._points):
            canvas_point = self._point_to_canvas(point)
            dx = x - canvas_point.x()
            dy = y - canvas_point.y()
            if (dx * dx) + (dy * dy) <= drag_radius_sq:
                return index
        return None


class CameraRoiDialog(QDialog):
    def __init__(
        self,
        camera: Camera,
        frame_text: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.roi_value = str(camera.roi or "")
        self.setWindowTitle(f"ROI Setting - {camera.name}")
        self.resize(940, 820)
        self.setMinimumSize(900, 760)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel(f"ROI Editor for {camera.name}")
        title.setStyleSheet("color:#f8fafc; font-size:20px; font-weight:700;")
        root.addWidget(title)

        hint = QLabel("Click to add points, drag a point to reposition it, then save the normalized ROI.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#94a3b8; font-size:13px;")
        root.addWidget(hint)

        canvas_frame = QFrame()
        canvas_frame.setObjectName("roiCanvasFrame")
        canvas_layout = QVBoxLayout(canvas_frame)
        canvas_layout.setContentsMargins(12, 12, 12, 12)
        canvas_layout.setSpacing(0)

        self.canvas = RoiCanvas(self)
        self.canvas.set_frame_text(frame_text)
        self.canvas.set_points(_parse_normalized_points(camera.roi))
        self.canvas.points_changed.connect(self._update_status)
        canvas_layout.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignCenter)
        root.addWidget(canvas_frame, 1)

        footer = QHBoxLayout()
        footer.setSpacing(12)
        root.addLayout(footer)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        footer.addWidget(self.status_label, 1)

        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self.canvas.clear_points)
        footer.addWidget(self.reset_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        self.save_btn = QPushButton("Save ROI")
        self.save_btn.clicked.connect(self._save)
        footer.addWidget(self.save_btn)

        self.setStyleSheet(
            """
            QDialog {
                background: #171a1f;
                color: #f1f5f9;
            }
            QFrame#roiCanvasFrame {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 12px;
            }
            QPushButton {
                background: #2b3340;
                border: 1px solid #425062;
                border-radius: 8px;
                color: #f8fafc;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #35507f;
                border-color: #4d76bb;
            }
            QPushButton:disabled {
                background: #232831;
                color: #7c8797;
                border-color: #303744;
            }
            """
        )

        self._update_status()

    def _update_status(self) -> None:
        point_count = len(self.canvas.points())
        if not self.canvas.has_frame():
            self.status_label.setText("Camera frame unavailable for ROI editing.")
            self.status_label.setStyleSheet("color:#fca5a5; font-size:13px; font-weight:600;")
        elif point_count == 0:
            self.status_label.setText("Select points to define ROI area.")
            self.status_label.setStyleSheet("color:#94a3b8; font-size:13px;")
        elif point_count < 3:
            self.status_label.setText(f"Need {3 - point_count} more point(s) to complete the ROI.")
            self.status_label.setStyleSheet("color:#fbbf24; font-size:13px; font-weight:600;")
        else:
            self.status_label.setText(f"ROI area ready ({point_count} points).")
            self.status_label.setStyleSheet("color:#86efac; font-size:13px; font-weight:700;")

        self.reset_btn.setEnabled(point_count > 0)
        self.save_btn.setEnabled(self.canvas.has_frame() and point_count >= 3)

    def _save(self) -> None:
        points = self.canvas.points()
        if len(points) < 3:
            QMessageBox.warning(self, "ROI", "Please select at least 3 points to define an ROI area.")
            return
        self.roi_value = json.dumps(points, separators=(",", ":"))
        self.accept()


class CountLineCanvas(RoiCanvas):
    _MAX_POINTS = 4

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._hover_point: Optional[QPointF] = None

    def set_points(self, points: list[dict[str, float]]) -> None:
        super().set_points(points[: self._MAX_POINTS])

    def clear_points(self) -> None:
        self._hover_point = None
        super().clear_points()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#111827"))

        if not self._pixmap.isNull():
            painter.drawPixmap(self.rect(), self._pixmap)
        else:
            painter.setPen(QColor("#9ca3af"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Camera frame unavailable.",
            )

        if len(self._points) >= 2:
            start = self._point_to_canvas(self._points[0])
            end = self._point_to_canvas(self._points[1])
            painter.setPen(QPen(QColor("#ef4444"), 3))
            painter.drawLine(start, end)
        elif len(self._points) == 1 and self._hover_point is not None:
            painter.setPen(QPen(QColor(239, 68, 68, 160), 2, Qt.PenStyle.DashLine))
            painter.drawLine(self._point_to_canvas(self._points[0]), self._hover_point)

        if len(self._points) >= 4:
            start = self._point_to_canvas(self._points[2])
            end = self._point_to_canvas(self._points[3])
            painter.setPen(QPen(QColor("#3b82f6"), 3))
            painter.drawLine(start, end)
            self._draw_arrow(painter, start, end)
        elif len(self._points) == 3 and self._hover_point is not None:
            painter.setPen(QPen(QColor(59, 130, 246, 160), 2, Qt.PenStyle.DashLine))
            painter.drawLine(self._point_to_canvas(self._points[2]), self._hover_point)

        painter.setPen(Qt.PenStyle.NoPen)
        for index, point in enumerate(self._points):
            painter.setBrush(QColor("#ef4444") if index < 2 else QColor("#3b82f6"))
            painter.drawEllipse(self._point_to_canvas(point), self._POINT_RADIUS, self._POINT_RADIUS)

        if self._hover_point is not None and len(self._points) < self._MAX_POINTS:
            hover_color = QColor(239, 68, 68, 90) if len(self._points) < 2 else QColor(59, 130, 246, 90)
            painter.setBrush(hover_color)
            painter.drawEllipse(self._hover_point, self._DRAG_RADIUS, self._DRAG_RADIUS)

        border_color = QColor("#475569") if self.has_frame() else QColor("#7f1d1d")
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() != Qt.MouseButton.LeftButton or not self.has_frame():
            return super().mousePressEvent(event)

        canvas_pos = event.position()
        point_index = self._find_point_at(canvas_pos.x(), canvas_pos.y())
        if point_index is not None:
            self._dragging_index = point_index
            self._hover_point = None
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if len(self._points) >= self._MAX_POINTS:
            event.accept()
            return

        self._points.append(self._canvas_to_point(canvas_pos.x(), canvas_pos.y()))
        self._hover_point = None
        self.points_changed.emit()
        self.update()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if not self.has_frame():
            self._hover_point = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return super().mouseMoveEvent(event)

        canvas_pos = event.position()
        if self._dragging_index is not None:
            self._points[self._dragging_index] = self._canvas_to_point(canvas_pos.x(), canvas_pos.y())
            self._hover_point = None
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.points_changed.emit()
            self.update()
            event.accept()
            return

        self._hover_point = None
        if len(self._points) < self._MAX_POINTS:
            self._hover_point = QPointF(
                max(0.0, min(canvas_pos.x(), self.width())),
                max(0.0, min(canvas_pos.y(), self.height())),
            )

        if self._find_point_at(canvas_pos.x(), canvas_pos.y()) is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and self._dragging_index is not None:
            self._dragging_index = None
            canvas_pos = event.position()
            if self._find_point_at(canvas_pos.x(), canvas_pos.y()) is not None:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._hover_point = None
        super().leaveEvent(event)
        self.update()

    def _draw_arrow(self, painter: QPainter, start: QPointF, end: QPointF) -> None:
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        arrow_length = 15
        painter.drawLine(
            end,
            QPointF(
                end.x() - arrow_length * math.cos(angle - math.pi / 6.0),
                end.y() - arrow_length * math.sin(angle - math.pi / 6.0),
            ),
        )
        painter.drawLine(
            end,
            QPointF(
                end.x() - arrow_length * math.cos(angle + math.pi / 6.0),
                end.y() - arrow_length * math.sin(angle + math.pi / 6.0),
            ),
        )


class CameraCountLineDialog(QDialog):
    def __init__(
        self,
        camera: Camera,
        frame_text: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.line_value = str(camera.face_count_line or "")
        self.setWindowTitle(f"Count Line Setting - {camera.name}")
        self.resize(940, 820)
        self.setMinimumSize(900, 760)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel(f"Count Line Editor for {camera.name}")
        title.setStyleSheet("color:#f8fafc; font-size:20px; font-weight:700;")
        root.addWidget(title)

        hint = QLabel("Select 2 points for the count line, then optionally 2 points for the direction line.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#94a3b8; font-size:13px;")
        root.addWidget(hint)

        canvas_frame = QFrame()
        canvas_frame.setObjectName("countLineCanvasFrame")
        canvas_layout = QVBoxLayout(canvas_frame)
        canvas_layout.setContentsMargins(12, 12, 12, 12)
        canvas_layout.setSpacing(0)

        self.canvas = CountLineCanvas(self)
        self.canvas.set_frame_text(frame_text)
        self.canvas.set_points(_parse_line_points(camera.face_count_line))
        self.canvas.points_changed.connect(self._update_status)
        canvas_layout.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignCenter)
        root.addWidget(canvas_frame, 1)

        footer = QHBoxLayout()
        footer.setSpacing(12)
        root.addLayout(footer)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        footer.addWidget(self.status_label, 1)

        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self.canvas.clear_points)
        footer.addWidget(self.reset_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        self.save_btn = QPushButton("Save Count Line")
        self.save_btn.clicked.connect(self._save)
        footer.addWidget(self.save_btn)

        self.setStyleSheet(
            """
            QDialog {
                background: #171a1f;
                color: #f1f5f9;
            }
            QFrame#countLineCanvasFrame {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 12px;
            }
            QPushButton {
                background: #2b3340;
                border: 1px solid #425062;
                border-radius: 8px;
                color: #f8fafc;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #35507f;
                border-color: #4d76bb;
            }
            QPushButton:disabled {
                background: #232831;
                color: #7c8797;
                border-color: #303744;
            }
            """
        )

        self._update_status()

    def _update_status(self) -> None:
        point_count = len(self.canvas.points())
        if not self.canvas.has_frame():
            self.status_label.setText("Camera frame unavailable for count line editing.")
            self.status_label.setStyleSheet("color:#fca5a5; font-size:13px; font-weight:600;")
        elif point_count == 0:
            self.status_label.setText("Select 2 points for Count Line, then 2 for Direction Line.")
            self.status_label.setStyleSheet("color:#94a3b8; font-size:13px;")
        elif point_count < 2:
            self.status_label.setText(f"Need {2 - point_count} more point(s) for the Count Line.")
            self.status_label.setStyleSheet("color:#fbbf24; font-size:13px; font-weight:600;")
        elif point_count == 3:
            self.status_label.setText("Add 1 more point to complete the Direction Line, or reset to save only the Count Line.")
            self.status_label.setStyleSheet("color:#60a5fa; font-size:13px; font-weight:600;")
        elif point_count < 4:
            self.status_label.setText(f"Need {4 - point_count} more point(s) for the Direction Line.")
            self.status_label.setStyleSheet("color:#60a5fa; font-size:13px; font-weight:600;")
        else:
            self.status_label.setText("Count Line and Direction Line are ready (4 points).")
            self.status_label.setStyleSheet("color:#86efac; font-size:13px; font-weight:700;")

        self.reset_btn.setEnabled(point_count > 0)
        self.save_btn.setEnabled(self.canvas.has_frame() and point_count in {2, 4})

    def _save(self) -> None:
        points = self.canvas.points()
        if len(points) not in {2, 4}:
            QMessageBox.warning(
                self,
                "Count Line",
                "Please select 2 points for the count line, and optionally 2 more for the direction line.",
            )
            return
        self.line_value = _serialize_line_points(points)
        self.accept()


class CameraSettingsDialog(QDialog):
    def __init__(self, camera: Camera, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Camera Setting")
        self.resize(700, 500)

        layout = QVBoxLayout(self)
        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(json.dumps(asdict(camera), indent=2))
        layout.addWidget(editor)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class CameraTypeFormDialog(QDialog):
    submitted = Signal(dict, bool)

    def __init__(
        self,
        camera_type: Optional[CameraType] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.camera_type = camera_type
        self.is_edit_mode = camera_type is not None

        self.setWindowTitle("Edit Camera Type" if self.is_edit_mode else "Add Camera Type")
        self.resize(920, 520)
        self.setMinimumSize(860, 480)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        root.addLayout(form)

        self.name_edit = QLineEdit()
        self.protocol_edit = QLineEdit()
        self.main_url_edit = QLineEdit()
        self.sub_url_edit = QLineEdit()
        self.ptz_url_edit = QLineEdit()
        self.network_url_edit = QLineEdit()

        self.protocol_edit.setPlaceholderText("rtsp")
        self.main_url_edit.setPlaceholderText("/Streaming/Channels/101")
        self.sub_url_edit.setPlaceholderText("/Streaming/Channels/102")
        self.ptz_url_edit.setPlaceholderText("/ISAPI/PTZCtrl/channels/1/continuous")
        self.network_url_edit.setPlaceholderText("/ISAPI/System/Network/interfaces/1")

        form.addRow("Name *", self.name_edit)
        form.addRow("Protocol", self.protocol_edit)
        form.addRow("Main URL", self.main_url_edit)
        form.addRow("Sub URL", self.sub_url_edit)
        form.addRow("PTZ URL", self.ptz_url_edit)
        form.addRow("Network URL", self.network_url_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        save_btn = QPushButton("Update Type" if self.is_edit_mode else "Create Type")
        buttons.addButton(save_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.rejected.connect(self.reject)
        save_btn.clicked.connect(self._submit)
        root.addWidget(buttons)

        self.setStyleSheet(
            """
            QDialog {
                background: #171a1f;
                color: #f1f5f9;
            }
            QLineEdit {
                background: #232831;
                border: 1px solid #3a424f;
                border-radius: 8px;
                color: #f8fafc;
                padding: 8px 10px;
                min-height: 24px;
            }
            QLabel {
                color: #dbe4f3;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton {
                background: #2b3340;
                border: 1px solid #425062;
                border-radius: 8px;
                color: #f8fafc;
                padding: 7px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #35507f;
                border-color: #4d76bb;
            }
            """
        )

        if self.camera_type is not None:
            self._load_camera_type(self.camera_type)

    def _load_camera_type(self, camera_type: CameraType) -> None:
        self.name_edit.setText(camera_type.name)
        self.protocol_edit.setText(camera_type.protocol)
        self.main_url_edit.setText(camera_type.main_url)
        self.sub_url_edit.setText(camera_type.sub_url)
        self.ptz_url_edit.setText(camera_type.ptz_url)
        self.network_url_edit.setText(camera_type.network_url)

    def payload(self) -> Dict[str, Any]:
        payload = {
            "name": self.name_edit.text().strip(),
            "protocol": self.protocol_edit.text().strip(),
            "main_url": self.main_url_edit.text().strip(),
            "sub_url": self.sub_url_edit.text().strip(),
            "ptz_url": self.ptz_url_edit.text().strip(),
            "network_url": self.network_url_edit.text().strip(),
        }
        if self.camera_type is not None:
            payload["id"] = self.camera_type.id
        return payload

    def _submit(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Camera type name is required.")
            return
        self.submitted.emit(self.payload(), self.is_edit_mode)


class CameraTypeManagerDialog(QDialog):
    def __init__(
        self,
        camera_type_store: CameraTypeStore,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.camera_type_store = camera_type_store

        self.setWindowTitle("Camera Types")
        self.resize(1380, 840)
        self.setMinimumSize(1240, 760)

        self.camera_type_store.changed.connect(self._populate_table)
        self.camera_type_store.error.connect(self._show_error)
        self.camera_type_store.success.connect(self._show_info)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        root.addLayout(toolbar)

        self.new_btn = QPushButton("+ New Type")
        self.new_btn.clicked.connect(self.open_create_dialog)
        toolbar.addWidget(self.new_btn)

        toolbar.addStretch(1)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search camera types...")
        self.search_edit.setMaximumWidth(320)
        self.search_edit.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_edit)

        self.table = PrimeDataTable(page_size=10, row_height=54, show_footer=True)
        self.table.set_columns(
            [
                PrimeTableColumn("name", "Name", width=160),
                PrimeTableColumn("protocol", "Protocol", width=110),
                PrimeTableColumn("main_url", "Main URL", width=180),
                PrimeTableColumn("sub_url", "Sub URL", width=180),
                PrimeTableColumn("ptz_url", "PTZ URL", width=180),
                PrimeTableColumn("network_url", "Network URL", stretch=True),
                PrimeTableColumn(
                    "actions",
                    "Actions",
                    sortable=False,
                    searchable=False,
                    width=134,
                    alignment=Qt.AlignLeft | Qt.AlignVCenter,
                ),
            ]
        )
        self.table.set_cell_widget_factory("actions", self._camera_type_action_cell)
        root.addWidget(self.table, 1)

        controls = QHBoxLayout()
        controls.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        controls.addWidget(close_btn)
        root.addLayout(controls)

        self.setStyleSheet(
            """
            QDialog {
                background: #171a1f;
                color: #f1f5f9;
            }
            QLineEdit {
                background: #232831;
                border: 1px solid #3a424f;
                border-radius: 8px;
                color: #f8fafc;
                padding: 8px 10px;
                min-height: 24px;
            }
            QPushButton {
                background: #2b3340;
                border: 1px solid #425062;
                border-radius: 8px;
                color: #f8fafc;
                padding: 7px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #35507f;
                border-color: #4d76bb;
            }
            """
        )

        self.camera_type_store.load()

    def _rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for item in self.camera_type_store.camera_types:
            if not self._is_real_camera_type(item):
                continue
            rows.append(
                {
                    "name": item.name,
                    "protocol": item.protocol or "Unset",
                    "main_url": item.main_url or "Unset",
                    "sub_url": item.sub_url or "Unset",
                    "ptz_url": item.ptz_url or "Unset",
                    "network_url": item.network_url or "Unset",
                    "actions": "",
                    "_camera_type": item,
                }
            )
        return rows

    def _populate_table(self) -> None:
        self.table.set_rows(self._rows())

    def _on_search_changed(self, text: str) -> None:
        self.table.set_filter_text(text)

    def _action_button(self, text: str, bg: str, border: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(28)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 8px;
                color: #f8fafc;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                border-color: #f8fafc;
            }}
            """
        )
        return btn

    def _action_widget(self, camera_type: CameraType) -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)

        edit_btn = self._action_button("Edit", "#35507f", "#4d76bb")
        edit_btn.clicked.connect(lambda: self.open_edit_dialog(camera_type))
        layout.addWidget(edit_btn)

        delete_btn = self._action_button("Delete", "#8b2f3f", "#bb4d62")
        delete_btn.clicked.connect(lambda: self.handle_delete(camera_type))
        layout.addWidget(delete_btn)
        return box

    def _is_real_camera_type(self, camera_type: CameraType) -> bool:
        return bool(
            camera_type.id
            or camera_type.name.strip()
            or camera_type.protocol.strip()
            or camera_type.main_url.strip()
            or camera_type.sub_url.strip()
            or camera_type.ptz_url.strip()
            or camera_type.network_url.strip()
        )

    def _camera_type_action_cell(self, row: Dict[str, Any]) -> QWidget:
        camera_type = row.get("_camera_type")
        if not isinstance(camera_type, CameraType) or not self._is_real_camera_type(camera_type):
            return QWidget()
        return self._action_widget(camera_type)

    def open_create_dialog(self) -> None:
        self._open_form_dialog()

    def open_edit_dialog(self, camera_type: CameraType) -> None:
        self._open_form_dialog(camera_type)

    def _open_form_dialog(self, camera_type: Optional[CameraType] = None) -> None:
        dialog = CameraTypeFormDialog(camera_type=camera_type, parent=self)
        dialog.submitted.connect(
            lambda payload, is_edit_mode, current_dialog=dialog: self._handle_submit(
                current_dialog,
                payload,
                is_edit_mode,
            )
        )
        dialog.exec()

    def _handle_submit(
        self,
        dialog: CameraTypeFormDialog,
        payload: Dict[str, Any],
        is_edit_mode: bool,
    ) -> None:
        if is_edit_mode:
            camera_type_id = int(payload.get("id") or 0)
            if not camera_type_id:
                self._show_error("Camera type id is missing.")
                return
            success = self.camera_type_store.update_camera_type(camera_type_id, payload)
        else:
            success = self.camera_type_store.create_camera_type(payload)

        if success:
            dialog.accept()

    def handle_delete(self, camera_type: CameraType) -> None:
        result = QMessageBox.question(
            self,
            "Delete Camera Type",
            f"Are you sure you want to delete '{camera_type.name}'?",
        )
        if result == QMessageBox.Yes:
            self.camera_type_store.delete_camera_type(camera_type.id)

    def _show_info(self, text: str) -> None:
        QMessageBox.information(self, "Camera Types", text)

    def _show_error(self, text: str) -> None:
        QMessageBox.critical(self, "Camera Types", text)


class CameraFormDialog(QDialog):
    submitted = Signal(dict, bool)
    open_roi = Signal(int)
    open_count_line = Signal(int)

    def __init__(
        self,
        auth_store: AuthStore,
        client_store: ClientStore,
        camera_type_store: CameraTypeStore,
        access_control_store: AccessControlStore,
        camera: Optional[Camera] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.auth_store = auth_store
        self.client_store = client_store
        self.camera_type_store = camera_type_store
        self.access_control_store = access_control_store
        self.camera = camera
        self.is_edit_mode = camera is not None
        self.setObjectName("cameraFormDialog")
        self.setWindowTitle("Edit Camera" if self.is_edit_mode else "Add New Camera")
        self.resize(1100, 780)
        self.setStyleSheet(
            """
            QDialog#cameraFormDialog {
                background: #222222;
                color: #f1f5f9;
            }
            QGroupBox {
                background: #222222;
                color: #f8fafc;
                border: 1px solid #3a424f;
                border-radius: 10px;
                margin-top: 14px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #f8fafc;
                background: #222222;
            }
            QLabel {
                color: #dbe4f3;
                font-size: 13px;
                font-weight: 600;
            }
            QLineEdit,
            QComboBox,
            QAbstractSpinBox {
                background: #222222;
                border: 1px solid #4a5563;
                border-radius: 8px;
                color: #f8fafc;
                padding: 8px 10px;
                min-height: 24px;
            }
            QLineEdit:read-only {
                color: #cbd5e1;
            }
            QLineEdit:focus,
            QComboBox:focus,
            QAbstractSpinBox:focus {
                border: 1px solid #60a5fa;
            }
            QComboBox::drop-down {
                border: none;
                width: 28px;
            }
            QComboBox QAbstractItemView {
                background: #222222;
                border: 1px solid #4a5563;
                color: #f8fafc;
                selection-background-color: #35507f;
                selection-color: #f8fafc;
            }
            """
        )

        root = QVBoxLayout(self)

        top_box = QGroupBox("General")
        top_layout = QGridLayout(top_box)
        root.addWidget(top_box)

        self.name_edit = QLineEdit()
        self.ai_combo = self._bool_combo()
        self.process_type_combo = QComboBox()
        self.process_type_combo.addItem("Face Recognition", "face")
        self.process_type_combo.addItem("License Plate Recognition", "lpr")
        self.process_type_combo.currentIndexChanged.connect(self._toggle_type_fields)

        top_layout.addWidget(QLabel("Camera Name *"), 0, 0)
        top_layout.addWidget(self.name_edit, 1, 0)
        top_layout.addWidget(QLabel("AI Support *"), 0, 1)
        top_layout.addWidget(self.ai_combo, 1, 1)
        top_layout.addWidget(QLabel("Camera Type *"), 0, 2)
        top_layout.addWidget(self.process_type_combo, 1, 2)

        body = QHBoxLayout()
        root.addLayout(body, 1)

        # Left column
        left_box = QGroupBox("Camera Connection")
        left = QFormLayout(left_box)
        body.addWidget(left_box, 1)

        self.camera_ip_edit = QLineEdit()
        self.camera_port_spin = QSpinBox()
        self.camera_port_spin.setMaximum(65535)
        self.camera_port_spin.setValue(554)
        self.camera_username_edit = QLineEdit()
        self.camera_password_edit = QLineEdit()
        self.camera_password_edit.setEchoMode(QLineEdit.Password)
        self.camera_type_combo = QComboBox()
        self.camera_type_combo.addItem("", None)
        for item in self.camera_type_store.camera_types:
            self.camera_type_combo.addItem(item.name, item.id)

        self.access_control_combo = QComboBox()
        self.access_control_combo.addItem("", None)
        for item in self.access_control_store.access_controls:
            self.access_control_combo.addItem(item.name, item.id)
        self.access_control_combo.currentIndexChanged.connect(self._refresh_doors)

        self.door_combo = QComboBox()
        self.map_pos_edit = QLineEdit()
        self.map_pos_edit.setReadOnly(True)
        self.latitude_edit = QLineEdit()
        self.latitude_edit.setReadOnly(True)
        self.longitude_edit = QLineEdit()
        self.longitude_edit.setReadOnly(True)
        map_btn = QPushButton("Select Location")
        map_btn.clicked.connect(self._select_location)

        left.addRow("Camera IP *", self.camera_ip_edit)
        left.addRow("Camera Port", self.camera_port_spin)
        left.addRow("Username", self.camera_username_edit)
        left.addRow("Password", self.camera_password_edit)
        left.addRow("Camera Brand", self.camera_type_combo)
        left.addRow("Access Control", self.access_control_combo)
        left.addRow("Door Number", self.door_combo)
        left.addRow("Map Position", self.map_pos_edit)
        left.addRow("Latitude", self.latitude_edit)
        left.addRow("Longitude", self.longitude_edit)
        left.addRow("", map_btn)

        # Right column
        right_box = QGroupBox("Processing & Clients")
        right = QFormLayout(right_box)
        body.addWidget(right_box, 1)

        self.client_1_combo = QComboBox()
        self.client_2_combo = QComboBox()
        self.client_3_combo = QComboBox()
        self._fill_client_combo(self.client_1_combo, "process")
        self._fill_client_combo(self.client_2_combo, "process")
        self._fill_client_combo(self.client_3_combo, "record")

        self.is_process_combo = self._bool_combo()
        self.is_live_combo = self._bool_combo(default=True)
        self.is_record_combo = self._bool_combo()
        self.is_ptz_combo = self._bool_combo()
        self.forward_stream_combo = self._bool_combo()
        self.fps_delay_spin = QSpinBox()
        self.fps_delay_spin.setMaximum(1000)
        self.fps_delay_spin.setValue(5)

        right.addRow("Processing Client *", self.client_1_combo)
        right.addRow("Failover Client", self.client_2_combo)
        right.addRow("Recording Client", self.client_3_combo)
        right.addRow("Enable Processing", self.is_process_combo)
        right.addRow("Enable Live Stream", self.is_live_combo)
        right.addRow("Enable Recording", self.is_record_combo)
        right.addRow("PTZ", self.is_ptz_combo)
        right.addRow("FPS Delay", self.fps_delay_spin)
        right.addRow("Forward to Server", self.forward_stream_combo)

        self.face_box = QGroupBox("Face Recognition Settings")
        face_form = QFormLayout(self.face_box)
        self.face_person_count_combo = self._bool_combo()
        self.face_color_detection_combo = self._bool_combo()
        self.face_min_size_spin = QSpinBox()
        self.face_min_size_spin.setMaximum(10000)
        self.face_min_size_spin.setValue(5)
        self.face_max_size_spin = QSpinBox()
        self.face_max_size_spin.setMaximum(10000)
        self.face_max_size_spin.setValue(40)
        self.face_show_rect_combo = self._bool_combo()
        face_form.addRow("Person Counting", self.face_person_count_combo)
        face_form.addRow("Color Detection", self.face_color_detection_combo)
        face_form.addRow("Min Face Size", self.face_min_size_spin)
        face_form.addRow("Max Face Size", self.face_max_size_spin)
        face_form.addRow("Show Total Faces", self.face_show_rect_combo)
        root.addWidget(self.face_box)

        action_bar = QHBoxLayout()
        root.addLayout(action_bar)
        action_bar.addStretch(1)

        self.scan_btn = QPushButton("Scan Network")
        self.scan_btn.clicked.connect(self._scan_network)
        self.roi_btn = QPushButton("ROI")
        self.countline_btn = QPushButton("Count Line")
        self.roi_btn.clicked.connect(self._emit_roi)
        self.countline_btn.clicked.connect(self._emit_count_line)
        cancel_btn = QPushButton("Cancel")
        save_btn = QPushButton("Update Camera" if self.is_edit_mode else "Add Camera")
        cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self._submit)

        if not self.is_edit_mode:
            self.roi_btn.hide()
            self.countline_btn.hide()
        action_bar.addWidget(self.scan_btn)
        action_bar.addWidget(self.countline_btn)
        action_bar.addWidget(self.roi_btn)
        action_bar.addWidget(cancel_btn)
        action_bar.addWidget(save_btn)

        if self.camera:
            self._load_camera(self.camera)
        else:
            self._write_map_pos(json.dumps({"lat": 36.1901, "lng": 44.0091}))
        self._toggle_type_fields()
        self._refresh_doors()

    def _bool_combo(self, default: bool = False) -> QComboBox:
        combo = QComboBox()
        combo.addItem("Yes", True)
        combo.addItem("No", False)
        combo.setCurrentIndex(0 if default else 1)
        return combo

    def _fill_client_combo(self, combo: QComboBox, client_type: str) -> None:
        combo.addItem("", None)
        for item in self.client_store.clients:
            item_type = (item.type or "").strip().lower()
            if item_type == client_type or item_type not in {"process", "record"}:
                combo.addItem(f"{item.name} ({item.ip})", item.id)

    def _set_combo_value(self, combo: QComboBox, value: Any) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _toggle_type_fields(self) -> None:
        self.face_box.setVisible(self.process_type_combo.currentData() == "face")
        self.countline_btn.setVisible(self.is_edit_mode and self.process_type_combo.currentData() == "face")

    def _refresh_doors(self) -> None:
        self.door_combo.clear()
        self.door_combo.addItem("", None)
        selected_id = self.access_control_combo.currentData()
        for ac in self.access_control_store.access_controls:
            if ac.id == selected_id:
                for idx in range(ac.ac_type.num_of_relay):
                    self.door_combo.addItem(f"Door {idx + 1}", idx + 1)
                break

    def _select_location(self) -> None:
        lat = 36.1901
        lng = 44.0091
        if self.map_pos_edit.text().strip():
            try:
                pos = json.loads(self.map_pos_edit.text().strip())
                lat = float(pos.get("lat", lat))
                lng = float(pos.get("lng", lng))
            except Exception:
                pass
        dialog = MapDialog(lat, lng, self)
        if dialog.exec():
            self._write_map_pos(json.dumps(dialog.selected))

    def _write_map_pos(self, text: str) -> None:
        self.map_pos_edit.setText(text)
        try:
            pos = json.loads(text)
            self.latitude_edit.setText(str(pos.get("lat", "")))
            self.longitude_edit.setText(str(pos.get("lng", "")))
        except Exception:
            self.latitude_edit.clear()
            self.longitude_edit.clear()

    def _normalize_scanned_camera(self, item: Dict[str, Any]) -> Dict[str, Any]:
        ip_address = str(
            item.get("camera_ip")
            or item.get("ip_address")
            or item.get("ip")
            or item.get("host")
            or ""
        ).strip()

        port_value = item.get("camera_port")
        if port_value in (None, ""):
            port_value = item.get("port")
        try:
            port = int(port_value)
        except (TypeError, ValueError):
            port = 80

        manufacturer = str(
            item.get("manufacturer")
            or item.get("brand")
            or item.get("camera_type")
            or item.get("title")
            or item.get("name")
            or "Unknown"
        ).strip() or "Unknown"

        username = str(item.get("camera_username") or item.get("username") or "").strip()
        password = str(item.get("camera_password") or item.get("password") or "")

        display_name = str(item.get("name") or "").strip()
        if not display_name:
            display_name = manufacturer if manufacturer.lower() != "unknown" else f"Camera {ip_address}"

        return {
            "ip_address": ip_address,
            "port": max(1, min(port, 65535)),
            "manufacturer": manufacturer,
            "username": username,
            "password": password,
            "name": display_name,
        }

    def _apply_scanned_camera(self, item: Dict[str, Any]) -> None:
        ip_address = str(item.get("ip_address") or "").strip()
        if ip_address:
            self.camera_ip_edit.setText(ip_address)

        port_value = item.get("port")
        if isinstance(port_value, int):
            self.camera_port_spin.setValue(max(1, min(port_value, 65535)))

        username = str(item.get("username") or "").strip()
        password = str(item.get("password") or "")
        if username:
            self.camera_username_edit.setText(username)
        if password:
            self.camera_password_edit.setText(password)

        manufacturer = str(item.get("manufacturer") or "").strip()
        if manufacturer and manufacturer.lower() != "unknown":
            self._select_camera_type_from_scan(manufacturer)

        if not self.name_edit.text().strip():
            guessed_name = str(item.get("name") or "").strip() or f"Camera {ip_address}"
            self.name_edit.setText(guessed_name)

    def _select_camera_type_from_scan(self, manufacturer: str) -> None:
        normalized_manufacturer = manufacturer.strip().lower()
        if not normalized_manufacturer:
            return

        for index in range(self.camera_type_combo.count()):
            label = self.camera_type_combo.itemText(index).strip().lower()
            if not label:
                continue
            if normalized_manufacturer in label or label in normalized_manufacturer:
                self.camera_type_combo.setCurrentIndex(index)
                return

    def _scan_network(self) -> None:
        try:
            payload = ApiService(os.getenv("Base_URL"))._api_request_json(
                "/api/v1/cameras/scan_cameras",
                params={"timeout": 10},
                auth=True,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Scan Network", str(exc))
            return

        results = extract_dict_list(payload, keys=("items", "data", "results", "cameras"))
        scanned_cameras: List[Dict[str, Any]] = []
        for item in results:
            normalized = self._normalize_scanned_camera(item)
            if normalized.get("ip_address"):
                scanned_cameras.append(normalized)

        if not scanned_cameras:
            QMessageBox.information(self, "Scan Network", "No cameras were found on the network.")
            return

        dialog = ScanCameraResultsDialog(scanned_cameras, self)
        if dialog.exec() and dialog.selected_camera:
            self._apply_scanned_camera(dialog.selected_camera)

    def _emit_roi(self) -> None:
        if self.camera:
            self.open_roi.emit(self.camera.id)

    def _emit_count_line(self) -> None:
        if self.camera:
            self.open_count_line.emit(self.camera.id)

    def _load_camera(self, cam: Camera) -> None:
        self.name_edit.setText(cam.name)
        self._set_combo_value(self.ai_combo, cam.is_ai_cam)
        self._set_combo_value(self.process_type_combo, cam.process_type)
        self.camera_ip_edit.setText(cam.camera_ip)
        self.camera_port_spin.setValue(cam.camera_port)
        self.camera_username_edit.setText(cam.camera_username)
        self.camera_password_edit.setText(cam.camera_password)
        self._set_combo_value(self.camera_type_combo, cam.camera_type_id)
        self._set_combo_value(self.access_control_combo, cam.access_control_id)
        self._refresh_doors()
        self._set_combo_value(self.door_combo, cam.door_number)
        self._write_map_pos(cam.map_pos or json.dumps({"lat": 36.1901, "lng": 44.0091}))
        self._set_combo_value(self.client_1_combo, cam.client_id_1)
        self._set_combo_value(self.client_2_combo, cam.client_id_2)
        self._set_combo_value(self.client_3_combo, cam.client_id_3)
        self._set_combo_value(self.is_process_combo, cam.is_process)
        self._set_combo_value(self.is_live_combo, cam.is_live)
        self._set_combo_value(self.is_record_combo, cam.is_record)
        self._set_combo_value(self.is_ptz_combo, cam.is_ptz)
        self._set_combo_value(self.forward_stream_combo, cam.forward_stream)
        self.fps_delay_spin.setValue(cam.fps_delay)
        self._set_combo_value(self.face_person_count_combo, cam.face_person_count)
        self._set_combo_value(self.face_color_detection_combo, cam.face_color_detection)
        self.face_min_size_spin.setValue(cam.face_min_size)
        self.face_max_size_spin.setValue(cam.face_max_size)
        self._set_combo_value(self.face_show_rect_combo, cam.face_show_rect)

    def _submit(self) -> None:
        if not self.name_edit.text().strip() or not self.camera_ip_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Camera name and camera IP are required.")
            return

        payload = {
            "name": self.name_edit.text().strip(),
            "client_id_1": self.client_1_combo.currentData(),
            "client_id_2": self.client_2_combo.currentData(),
            "client_id_3": self.client_3_combo.currentData(),
            "access_control_id": self.access_control_combo.currentData(),
            "door_number": self.door_combo.currentData(),
            "roi": self.camera.roi if self.camera else "",
            "map_pos": self.map_pos_edit.text().strip(),
            "is_record": self.is_record_combo.currentData(),
            "is_process": self.is_process_combo.currentData(),
            "is_live": self.is_live_combo.currentData(),
            "is_ptz": self.is_ptz_combo.currentData(),
            "forward_stream": self.forward_stream_combo.currentData(),
            "is_ai_cam": self.ai_combo.currentData(),
            "fps_delay": self.fps_delay_spin.value(),
            "process_type": self.process_type_combo.currentData(),
            "camera_type_id": self.camera_type_combo.currentData(),
            "camera_ip": self.camera_ip_edit.text().strip(),
            "camera_username": self.camera_username_edit.text().strip(),
            "camera_password": self.camera_password_edit.text(),
            "camera_port": self.camera_port_spin.value(),
            "face_person_count": self.face_person_count_combo.currentData(),
            "face_color_detection": self.face_color_detection_combo.currentData(),
            "face_min_size": self.face_min_size_spin.value(),
            "face_max_size": self.face_max_size_spin.value(),
            "face_show_rect": self.face_show_rect_combo.currentData(),
            "face_count_line": self.camera.face_count_line if self.camera else "",
            "online": self.camera.online if self.camera else False,
        }
        if self.camera:
            payload["id"] = self.camera.id
        self.submitted.emit(payload, self.is_edit_mode)
        self.accept()


class CameraPage(QWidget):
    navigate = Signal(str)

    def __init__(
        self,
        auth_store: AuthStore,
        client_store: ClientStore,
        camera_type_store: CameraTypeStore,
        access_control_store: AccessControlStore,
        department_store: DepartmentStore,
        camera_store: CameraStore,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.auth_store = auth_store
        self.client_store = client_store
        self.camera_type_store = camera_type_store
        self.access_control_store = access_control_store
        self.department_store = department_store
        self.camera_store = camera_store
        self.search_text = ""
        self._visible_password_camera_ids: set[int] = set()

        self.camera_store.success.connect(self._show_info)
        self.camera_store.error.connect(self._show_error)
        self.client_store.changed.connect(self.refresh)
        self.client_store.error.connect(self._show_error)
        self.department_store.error.connect(self._show_error)
        self.department_store.changed.connect(self.refresh)
        self.auth_store.changed.connect(self.refresh)

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("cameraSideNav")
        self.sidebar.setFixedWidth(96)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(8, 12, 8, 12)
        sidebar_layout.setSpacing(10)
        sidebar_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        nav_items = [
            ("Clients", "user_management.svg", "/device/clients"),
            ("Cameras", "devices.svg", "/device/cameras"),
            # ("GPS", "gps.svg", "/device/gps"),
            # ("Bodycam", "bodycam.svg", "/device/body-cam"),
            ("Access", "activation.svg", "/device/access-control"),
        ]
        current_path = "/device/cameras"
        for label, icon_name, path in nav_items:
            is_active = path == current_path
            btn = QToolButton()
            btn.setText(label)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setFixedSize(72, 72)
            icon_file = _icon_path(icon_name)
            if os.path.isfile(icon_file):
                btn.setIcon(QIcon(icon_file))
                btn.setIconSize(QSize(22, 22))
            btn.setObjectName("cameraSideBtnActive" if is_active else "cameraSideBtn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, p=path: self.navigate.emit(p))
            sidebar_layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
        sidebar_layout.addStretch(1)
        root.addWidget(self.sidebar)

        main = QFrame()
        main.setObjectName("cameraMainPanel")
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(18, 14, 18, 18)
        main_layout.setSpacing(14)
        root.addWidget(main, 1)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        main_layout.addLayout(toolbar)

        self.new_btn = QPushButton("+ New")
        self.new_btn.setObjectName("cameraNewBtn")
        self.new_btn.clicked.connect(self.toggle_add)
        toolbar.addWidget(self.new_btn)

        self.camera_types_btn = QPushButton("☰ Camera Types")
        self.camera_types_btn.setObjectName("cameraTypeBtn")
        self.camera_types_btn.clicked.connect(self.show_camera_types)
        toolbar.addWidget(self.camera_types_btn)

        toolbar.addStretch(1)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search...")
        self.search_edit.textChanged.connect(self._on_search_changed)
        self.search_edit.setMaximumWidth(280)
        self.search_edit.setObjectName("cameraSearchInput")
        toolbar.addWidget(self.search_edit)

        # Table view
        self.table = PrimeDataTable(page_size=20, row_height=58, show_footer=False)
        self.table.set_columns(
            [
                PrimeTableColumn("name", "Name", width=150),
                PrimeTableColumn("client", "Clients", width=220),
                PrimeTableColumn("recorder", "Recorder", width=170),
                PrimeTableColumn("type", "Type", width=84, alignment=Qt.AlignLeft | Qt.AlignVCenter),
                PrimeTableColumn("camera_ip", "Camera IP", width=132),
                PrimeTableColumn("username", "Username", width=120),
                PrimeTableColumn("password", "Password", sortable=False, searchable=False, width=140),
                PrimeTableColumn("record", "Record", width=80, alignment=Qt.AlignLeft | Qt.AlignVCenter),
                PrimeTableColumn("process", "Process", width=86, alignment=Qt.AlignLeft | Qt.AlignVCenter),
                PrimeTableColumn("live", "Live", width=72, alignment=Qt.AlignLeft | Qt.AlignVCenter),
                PrimeTableColumn("status", "Status", width=80, alignment=Qt.AlignLeft | Qt.AlignVCenter),
                PrimeTableColumn("fps_delay", "FPS Delay", width=90, alignment=Qt.AlignLeft | Qt.AlignVCenter),
                PrimeTableColumn(
                    "actions",
                    "Actions",
                    sortable=False,
                    searchable=False,
                    width=168,
                    alignment=Qt.AlignLeft | Qt.AlignVCenter,
                ),
            ]
        )
        # Fill available horizontal space in this screen by stretching the last column.
        self.table.table.horizontalHeader().setStretchLastSection(True)
        self.table.set_cell_widget_factory("client", self._client_cell_widget)
        self.table.set_cell_widget_factory("recorder", self._recorder_cell_widget)
        self.table.set_cell_widget_factory("type", self._type_cell_widget)
        self.table.set_cell_widget_factory("password", self._password_cell_widget)
        self.table.set_cell_widget_factory("record", self._record_cell_widget)
        self.table.set_cell_widget_factory("process", self._process_cell_widget)
        self.table.set_cell_widget_factory("live", self._live_cell_widget)
        self.table.set_cell_widget_factory("status", self._status_cell_widget)
        self.table.set_cell_widget_factory("actions", lambda row: self._action_widget(row["_camera"]))
        main_layout.addWidget(self.table, 1)

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._poll_updates)
        self.status_timer.start(10000)

        self.setStyleSheet(
            """
            QWidget { color: #f5f7fb; }
            QFrame#cameraMainPanel {
                background: #1f2024;
                border: 1px solid #2e3138;
                border-radius: 12px;
            }
            QFrame#cameraSideNav {
                background: #1b1c20;
                border: 1px solid #2e3138;
                border-radius: 12px;
            }
            QLabel#cameraSideTitle {
                color: #e7ebf3;
                font-size: 16px;
                font-weight: 700;
                padding: 8px 0 10px 0;
            }
            QToolButton#cameraSideBtn, QToolButton#cameraSideBtnActive {
                min-width: 72px;
                max-width: 72px;
                min-height: 72px;
                max-height: 72px;
                border-radius: 14px;
                border: 1px solid transparent;
                font-size: 11px;
                font-weight: 600;
                text-align: center;
                padding: 5px 2px;
            }
            QToolButton#cameraSideBtn {
                background: #23272e;
                color: #8f98a8;
                border-color: #2f3742;
            }
            QToolButton#cameraSideBtn:hover {
                background: #2b3038;
                color: #f3f6fc;
                border-color: #4b5563;
            }
            QToolButton#cameraSideBtnActive {
                background: #2f6ff0;
                color: white;
                border-color: #5f92ff;
            }
            QPushButton#cameraNewBtn {
                background: #3b82f6;
                border: none;
                border-radius: 10px;
                color: white;
                font-size: 14px;
                font-weight: 700;
                padding: 9px 18px;
            }
            QPushButton#cameraNewBtn:hover { background: #2f6ce3; }
            QPushButton#cameraTypeBtn {
                background: #0d1833;
                border: 1px solid #1d2c54;
                border-radius: 10px;
                color: #f3f7ff;
                font-size: 14px;
                font-weight: 600;
                padding: 9px 14px;
            }
            QPushButton#cameraTypeBtn:hover { background: #122247; }
            QLineEdit#cameraSearchInput {
                background: #2b2e34;
                border: 1px solid #3a3e46;
                border-radius: 10px;
                color: #f5f7fb;
                padding: 9px 12px;
                font-size: 14px;
                min-height: 24px;
            }
            QToolButton#cameraViewBtnActive {
                background: #2b2e34;
                border: 1px solid #3a3e46;
                border-radius: 10px;
                color: #f5f7fb;
                min-width: 44px;
                min-height: 42px;
                font-size: 17px;
            }
            """
        )

        self.refresh()

    def has_permission(self, permission: str) -> bool:
        return self.auth_store.has_permission(permission)

    def is_limited(self) -> bool:
        info = self.auth_store.server_activation_info
        return bool(info and info.camera_limit >= 0 and len(self.department_store.cameras) >= info.camera_limit)

    def filtered_cameras(self) -> List[Camera]:
        term = self.search_text.lower().strip()
        if not term:
            return list(self.department_store.cameras)
        return [
            c for c in self.department_store.cameras
            if term in c.name.lower() or term in c.camera_ip.lower()
        ]

    def refresh(self) -> None:
        self.new_btn.setEnabled(self.has_permission("add_camera") and not self.is_limited())
        self.camera_types_btn.setEnabled(self.has_permission("camera_type"))
        self._populate_table()

    def showEvent(self, event) -> None:  # type: ignore[override]
        self.client_store.load()
        super().showEvent(event)

    def _on_search_changed(self, text: str) -> None:
        self.search_text = text
        self.refresh()

    def _populate_table(self) -> None:
        items = self.filtered_cameras()
        rows: List[Dict[str, Any]] = []
        for cam in items:
            client_name, client_ip = self._client_meta(cam.client_id_1, getattr(cam, "client_1", None))
            failover_name, failover_ip = self._client_meta(cam.client_id_2, getattr(cam, "client_2", None))
            recorder_name, recorder_ip = self._client_meta(cam.client_id_3, getattr(cam, "client_3", None))
            rows.append(
                {
                    "name": cam.name,
                    "client": {
                        "name": client_name,
                        "ip": client_ip,
                        "failover_name": failover_name if cam.client_id_2 is not None else "",
                        "failover_ip": failover_ip if cam.client_id_2 is not None else "",
                    },
                    "recorder": {"name": recorder_name, "ip": recorder_ip},
                    "type": cam.process_type,
                    "camera_ip": cam.camera_ip,
                    "username": cam.camera_username or "Unset",
                    "password": cam.camera_password or "",
                    "record": cam.is_record,
                    "process": cam.is_process,
                    "live": cam.is_live,
                    "status": cam.online,
                    "fps_delay": cam.fps_delay,
                    "actions": "",
                    "_camera": cam,
                }
            )
        self.table.set_rows(rows)

    def _text_action_button(
        self,
        text: str,
        bg: str,
        fg: str = "#f8fafc",
        border: str = "#4b5565",
        size: int = 34,
        svg_icon: str = "",
    ) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(size, size)
        btn.setStyleSheet(
            f"""
            QToolButton {{
                background: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: {size // 2}px;
                font-size: 15px;
                font-weight: 700;
            }}
            QToolButton:hover {{
                border-color: #f8fafc;
            }}
            QToolButton:disabled {{
                color: #7b8090;
                border-color: #3b3f47;
                background: #2b2d33;
            }}
            """
        )
        if svg_icon:
            icon_file = _icon_path(svg_icon)
            if os.path.isfile(icon_file):
                icon_px = max(12, size - 16)
                btn.setIcon(QIcon(icon_file))
                btn.setIconSize(QSize(icon_px, icon_px))
                btn.setText("")
        return btn

    def _client_meta(
        self,
        client_id: Optional[int],
        client_data: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, str]:
        if isinstance(client_data, dict):
            name = str(
                client_data.get("name")
                or client_data.get("host_name")
                or client_data.get("client_name")
                or ""
            ).strip()
            ip = str(
                client_data.get("ip")
                or client_data.get("client_ip")
                or client_data.get("server_ip")
                or ""
            ).strip()
            if name or ip:
                return (name or (f"Client #{client_id}" if client_id is not None else "Unset"), ip)
        if client_id is None:
            return ("Unset", "")
        for client in self.client_store.clients:
            if client.id == client_id:
                return (client.name, client.ip)
        return (f"Client #{client_id}", "")

    def _two_line_cell(self, title: str, subtitle: str = "") -> QWidget:
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(box)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(0)

        text_wrap = QVBoxLayout()
        text_wrap.setContentsMargins(0, 0, 0, 0)
        text_wrap.setSpacing(2)

        top = QLabel(title)
        top.setWordWrap(False)
        top.setTextFormat(Qt.TextFormat.PlainText)
        top.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        top.setStyleSheet("background: transparent; color:#f8fafc; font-size:14px; font-weight:600;")
        text_wrap.addWidget(top)
        if subtitle:
            bottom = QLabel(subtitle)
            bottom.setWordWrap(False)
            bottom.setTextFormat(Qt.TextFormat.PlainText)
            bottom.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            bottom.setStyleSheet("background: transparent; color:#94a3b8; font-size:12px;")
            text_wrap.addWidget(bottom)
        else:
            spacer = QLabel("")
            spacer.setStyleSheet("background: transparent; font-size:12px;")
            text_wrap.addWidget(spacer)

        layout.addLayout(text_wrap, 1)
        return box

    def _status_chip(self, text: str, bg: str, fg: str = "#0b0f17") -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        chip = QLabel(text)
        chip.setAlignment(Qt.AlignCenter)
        chip.setMinimumWidth(38)
        chip.setMinimumHeight(24)
        chip.setMaximumHeight(24)
        chip.setStyleSheet(
            f"background:{bg}; color:{fg}; border:1px solid rgba(255,255,255,0.12); border-radius:7px; padding:2px 8px; font-size:11px; font-weight:700;"
        )
        layout.addWidget(chip)
        return box

    def _state_icon_cell(self, active: bool, icon: str, active_bg: str, inactive_bg: str) -> QWidget:
        fg = "#0f172a" if active else "#3f3f46"
        return self._status_chip(icon, active_bg if active else inactive_bg, fg)

    def _client_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        client = row.get("client") or {}
        primary_name = client.get("name") or "Unset"
        primary_ip = client.get("ip") or ""
        failover_name = client.get("failover_name") or ""
        failover_ip = client.get("failover_ip") or ""
        if failover_name:
            ips = [value for value in (primary_ip, failover_ip) if value]
            return self._two_line_cell(
                f"{primary_name} | {failover_name}",
                " | ".join(ips),
            )
        return self._two_line_cell(primary_name, primary_ip)

    def _recorder_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        recorder = row.get("recorder") or {}
        return self._two_line_cell(recorder.get("name") or "Unset", recorder.get("ip") or "")

    def _type_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        process_type = str(row.get("type") or "lpr").lower()
        if process_type == "face":
            return self._status_chip("Face", "#9ec5ff", "#0b1f47")
        return self._status_chip("LPR", "#9af0b6", "#0b3b1f")

    def _password_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        cam = row["_camera"]
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        masked = "•" * min(len(cam.camera_password), 8) if cam.camera_password else "Unset"
        text = cam.camera_password if cam.id in self._visible_password_camera_ids else masked

        label = QLabel(text)
        label.setStyleSheet("color:#f8fafc; font-size:13px; font-weight:600;")
        layout.addWidget(label)
        layout.addStretch(1)

        eye_btn = self._text_action_button(
            "◉",
            "#262a31",
            "#89b4ff",
            "#3f4550",
            size=24,
            svg_icon="view.svg",
        )
        eye_btn.setToolTip("Show/Hide Password")
        eye_btn.clicked.connect(lambda: self.toggle_password(cam))
        layout.addWidget(eye_btn)
        return box

    def _record_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        return self._state_icon_cell(bool(row.get("record")), "R", "#bdf3d1", "#d2d6de")

    def _process_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        return self._state_icon_cell(bool(row.get("process")), "P", "#ffe0c7", "#d2d6de")

    def _live_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        return self._state_icon_cell(bool(row.get("live")), "L", "#bbf7d0", "#d2d6de")

    def _status_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        return self._state_icon_cell(bool(row.get("status")), "S", "#b7f7cf", "#f1c6c6")

    def _action_widget(self, cam: Camera) -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignCenter)

        open_btn = self._text_action_button(
            "◌", "#24282f", "#f8fafc", "#616777", svg_icon="browser.svg"
        )
        open_btn.setToolTip("Open Camera Browser")
        open_btn.clicked.connect(lambda: self._show_info(f"Open http://{cam.camera_ip} in browser."))
        layout.addWidget(open_btn)

        settings_btn = self._text_action_button(
            "⚙", "#374151", "#ffffff", "#4b5563", svg_icon="settings.svg"
        )
        settings_btn.setToolTip("Camera Settings")
        settings_btn.clicked.connect(lambda: self.show_camera_settings(cam))
        layout.addWidget(settings_btn)

        edit_btn = self._text_action_button(
            "✎", "#3578f6", "#ffffff", "#4e8cff", svg_icon="edit.svg"
        )
        edit_btn.setToolTip("Edit Camera")
        edit_btn.clicked.connect(lambda: self.handle_edit_mode(cam))
        edit_btn.setEnabled(self.has_permission("edit_camera"))
        layout.addWidget(edit_btn)

        delete_btn = self._text_action_button(
            "⌫", "#ef4444", "#ffffff", "#ff6464", svg_icon="trash.svg"
        )
        delete_btn.setToolTip("Delete Camera")
        delete_btn.clicked.connect(lambda: self.handle_delete_camera(cam))
        delete_btn.setEnabled(self.has_permission("delete_camera"))
        layout.addWidget(delete_btn)
        return box

    def toggle_add(self) -> None:
        self._reload_dialog_dependencies()
        dialog = CameraFormDialog(
            self.auth_store,
            self.client_store,
            self.camera_type_store,
            self.access_control_store,
            camera=None,
            parent=self,
        )
        dialog.submitted.connect(self.handle_submit_form)
        dialog.exec()

    def handle_edit_mode(self, cam: Camera) -> None:
        self._reload_dialog_dependencies()
        dialog = CameraFormDialog(
            self.auth_store,
            self.client_store,
            self.camera_type_store,
            self.access_control_store,
            camera=cam,
            parent=self,
        )
        dialog.submitted.connect(self.handle_submit_form)
        dialog.open_roi.connect(self.open_roi_dialog)
        dialog.open_count_line.connect(self.open_countline_dialog)
        dialog.exec()

    def _reload_dialog_dependencies(self) -> None:
        self.client_store.load()
        self.camera_type_store.load()
        self.access_control_store.load()

    def handle_submit_form(self, payload: Dict[str, Any], is_edit_mode: bool) -> None:
        try:
            if is_edit_mode:
                self.camera_store.update_camera(payload)
            else:
                self.camera_store.add_new_camera(payload)
        except Exception as exc:
            self._show_error(str(exc))

    def handle_delete_camera(self, cam: Camera) -> None:
        result = QMessageBox.question(self, "Delete Record", f"Are you sure to delete '{cam.name}'?")
        if result == QMessageBox.Yes:
            try:
                self.camera_store.delete_camera(cam.id)
            except Exception as exc:
                self._show_error(str(exc))

    def load_camera_frame(self, camera_id: int) -> None:
        try:
            frame_text = self.camera_store.get_camera_frame(camera_id)
            cam = next((c for c in self.department_store.cameras if c.id == camera_id), None)
            if cam:
                cam.image = frame_text
                self.refresh()
        except Exception as exc:
            self._show_error(str(exc))

    def open_roi_dialog(self, camera_id: int) -> None:
        cam = next((c for c in self.department_store.cameras if c.id == camera_id), None)
        if not cam:
            return
        frame_text = str(cam.image or "")
        try:
            latest_frame = self.camera_store.service.get_camera_frame(camera_id)
            if latest_frame:
                frame_text = latest_frame
                cam.image = latest_frame
        except Exception as exc:
            if not frame_text:
                self._show_error(str(exc))
                return
        dialog = CameraRoiDialog(cam, frame_text, self)
        if dialog.exec():
            try:
                self.camera_store.update_camera_roi(camera_id, dialog.roi_value)
            except Exception as exc:
                self._show_error(str(exc))

    def open_countline_dialog(self, camera_id: int) -> None:
        cam = next((c for c in self.department_store.cameras if c.id == camera_id), None)
        if not cam:
            return
        frame_text = str(cam.image or "")
        try:
            latest_frame = self.camera_store.service.get_camera_frame(camera_id)
            if latest_frame:
                frame_text = latest_frame
                cam.image = latest_frame
        except Exception as exc:
            if not frame_text:
                self._show_error(str(exc))
                return
        dialog = CameraCountLineDialog(cam, frame_text, self)
        if dialog.exec():
            try:
                self.camera_store.update_camera_countline(camera_id, dialog.line_value)
            except Exception as exc:
                self._show_error(str(exc))

    def show_camera_settings(self, cam: Camera) -> None:
        CameraSettingsDialog(cam, self).exec()

    def show_camera_types(self) -> None:
        CameraTypeManagerDialog(self.camera_type_store, self).exec()

    def toggle_password(self, cam: Camera) -> None:
        if cam.id in self._visible_password_camera_ids:
            self._visible_password_camera_ids.discard(cam.id)
        else:
            self._visible_password_camera_ids.add(cam.id)
        self.refresh()

    def _show_info(self, text: str) -> None:
        QMessageBox.information(self, "Info", text)

    def _show_error(self, text: str) -> None:
        QMessageBox.critical(self, "Error", text)

    def _poll_updates(self) -> None:
        if not self.auth_store.current_user:
            return
        self.department_store.get_camera_for_user(self.auth_store.current_user.department_id, silent=True)
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        p.fillPath(path, QColor(Constants.DARK_BG))   # dark bg — cards float above it
        super().paintEvent(event)
