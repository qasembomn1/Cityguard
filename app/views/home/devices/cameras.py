from __future__ import annotations
import base64
import json
import math
import sys
import os
import urllib.parse
from dataclasses import asdict
from typing import Any, Dict, List, Optional
from app.models.camera import Camera, CameraType
from app.store.home.devices.camera_store import CameraStore
from app.store.home.user.department_store import DepartmentStore
from app.store.home.devices.access_control_store import AccessControlStore
from app.store.home.devices.client_store import ClientStore
from app.store.home.devices.camera_type_store import CameraTypeStore
from app.store.auth import AuthStore
from app.utils.env import resolve_http_base_url

from PySide6.QtCore import QObject, QPointF, Qt, QThread, QTimer, Signal, QSize, QRectF, QUrl
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QBoxLayout,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from app.ui.button import PrimeButton
from app.ui.confirm_dialog import PrimeConfirmDialog
from app.ui.dialog import PrimeDialog
from app.ui.input import PrimeInput

from app.ui.select import PrimeSelect
from app.ui.table import PrimeDataTable, PrimeTableColumn
from app.ui.toast import show_toast_message
from app.constants._init_ import Constants
try:
    from PySide6.QtWebSockets import QWebSocket
except Exception:
    QWebSocket = None

_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)



if __package__ in (None, ""):
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../"))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)



def _base_http_url() -> str:
    return resolve_http_base_url()


class _ScanThread(QThread):
    scan_done = Signal(list)
    scan_error = Signal(str)

    def __init__(self, service) -> None:
        super().__init__()
        self._service = service

    def run(self) -> None:
        try:
            results = self._service.scan_network()
            self.scan_done.emit(results)
        except Exception as exc:
            self.scan_error.emit(str(exc))


def _monitor_ws_url() -> str:
    raw = os.getenv("MONITOR_WS_URL", "").strip()
    if raw:
        return raw
    parsed = urllib.parse.urlparse(_base_http_url())
    host = parsed.netloc or parsed.path
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{host}/api/v1/monitor/ws"


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on", "online", "connected", "up", "alive"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", "offline", "down", "disconnected", "dead"}:
            return False
    return default


def _pick_case_insensitive(container: Dict[str, Any], name: str) -> Any:
    lowered = name.lower()
    for key, value in container.items():
        if str(key).strip().lower() == lowered:
            return value
    return None


def _extract_camera_online(update: Dict[str, Any]) -> Optional[bool]:
    nested = update.get("data") if isinstance(update.get("data"), dict) else {}
    for key in ("online", "is_online", "connected", "alive", "status", "state", "is_live"):
        for container in (update, nested):
            if key in container:
                return _as_bool(container.get(key))
            value = _pick_case_insensitive(container, key)
            if value is not None:
                return _as_bool(value)
    return None


class CameraStatusWsClient(QObject):
    statusUpdate = Signal(dict)
    connectionChanged = Signal(bool)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._url = _monitor_ws_url()
        self._ws = QWebSocket() if QWebSocket is not None else None
        self._closing = False
        self._reconnect = QTimer(self)
        self._reconnect.setSingleShot(True)
        self._reconnect.setInterval(3000)
        self._reconnect.timeout.connect(self.connect_socket)

        if self._ws is not None:
            self._ws.connected.connect(self._on_connected)
            self._ws.disconnected.connect(self._on_disconnected)
            self._ws.textMessageReceived.connect(self._on_message)

    def connect_socket(self) -> None:
        if self._ws is None:
            self.connectionChanged.emit(False)
            return
        self._closing = False
        self._ws.open(QUrl(self._url))

    def close(self) -> None:
        self._closing = True
        self._reconnect.stop()
        if self._ws is not None:
            self._ws.close()

    def _on_connected(self) -> None:
        self.connectionChanged.emit(True)

    def _on_disconnected(self) -> None:
        self.connectionChanged.emit(False)
        if not self._closing and not self._reconnect.isActive():
            self._reconnect.start()

    def _on_message(self, raw: str) -> None:
        try:
            message = json.loads(raw)
        except Exception:
            return
        if str(message.get("type") or "").strip().lower() != "status_update":
            return
        payload = message.get("payload")
        if isinstance(payload, dict):
            self.statusUpdate.emit(payload)


class _Spinner(QWidget):
    def __init__(self, size: int = 44, color: str = "#60a5fa", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._angle = 0
        self._color = QColor(color)
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._advance)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
        self.show()
        self.update()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _advance(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.rect().center())

        outer_radius = max(8, (min(self.width(), self.height()) // 2) - 2)
        inner_radius = max(4, outer_radius - 10)
        steps = 12
        for index in range(steps):
            painter.save()
            painter.rotate(self._angle - (index * (360 / steps)))
            color = QColor(self._color)
            color.setAlpha(int(35 + (220 * (steps - index) / steps)))
            painter.setPen(QPen(color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(0, -inner_radius, 0, -outer_radius)
            painter.restore()


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
            show_toast_message(self, "warn", "Invalid", "Please enter valid coordinates.")
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


class ScanCameraResultsDialog(PrimeDialog):
    def __init__(self, cameras: List[Dict[str, Any]], parent: Optional[QWidget] = None) -> None:
        super().__init__(
            title="Scanned Cameras",
            parent=parent,
            width=760,
            height=520,
            show_footer=True,
            cancel_text="Close",
        )
        self.ok_button.hide()
        self.selected_camera: Optional[Dict[str, Any]] = None
        self._cameras = cameras

        info_label = QLabel(
            f"{len(cameras)} camera(s) found on the network. Choose one to fill the form."
        )
        info_label.setWordWrap(True)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by IP address or manufacturer...")
        self.search_edit.textChanged.connect(self._on_search_changed)

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

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        content_layout.addWidget(info_label)
        content_layout.addWidget(self.search_edit)
        content_layout.addWidget(self.table, 1)
        self.set_content(content)

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


class CameraRoiDialog(PrimeDialog):
    def __init__(
        self,
        camera: Camera,
        frame_text: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            title=f"ROI Setting - {camera.name}",
            parent=parent,
            width=940,
            height=640,
            show_footer=True,
            ok_text="Save ROI",
            cancel_text="Cancel",
        )
        self.setMinimumWidth(900)
        self.roi_value = str(camera.roi or "")

        self.ok_button.clicked.disconnect()
        self.ok_button.clicked.connect(self._save)

        # Add status label and Reset button to the footer
        footer_layout = self.footer_widget.layout()
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.reset_btn = PrimeButton("Reset", variant="warning", mode="outline", size="sm")
        # footer_layout: [stretch(0), cancel(1), ok(2)]
        footer_layout.insertWidget(0, self.status_label, 1)
        footer_layout.insertWidget(2, self.reset_btn)

        self.hint_label = QLabel("Click to add points, drag a point to reposition it, then save the normalized ROI.")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color:#94a3b8; font-size:13px;")

        self.canvas_frame = QFrame()
        self.canvas_frame.setObjectName("roiCanvasFrame")
        self.canvas_frame.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        canvas_layout = QVBoxLayout(self.canvas_frame)
        canvas_layout.setContentsMargins(4, 4, 4, 4)
        canvas_layout.setSpacing(0)

        self.canvas = RoiCanvas(self)
        self.canvas.set_frame_text(frame_text)
        self.canvas.set_points(_parse_normalized_points(camera.roi))
        self.canvas.points_changed.connect(self._update_status)
        self.reset_btn.clicked.connect(self.canvas.clear_points)
        canvas_layout.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignCenter)

        self.content_widget = QWidget()
        self.content_body_layout = QVBoxLayout(self.content_widget)
        self.content_body_layout.setContentsMargins(0, 0, 0, 0)
        self.content_body_layout.setSpacing(12)
        self.content_body_layout.addWidget(self.hint_label)
        self.content_body_layout.addWidget(self.canvas_frame, 0, Qt.AlignmentFlag.AlignHCenter)
        self.set_content(self.content_widget)

        self.setStyleSheet(
            self.styleSheet()
            + """
            QFrame#roiCanvasFrame {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 12px;
            }
            """
        )

        self._update_status()
        self._fit_to_image_height()

    def _fit_to_image_height(self) -> None:
        content_margins = self.content_layout.contentsMargins()
        target_height = (
            self.header_widget.sizeHint().height()
            + self.footer_widget.sizeHint().height()
            + content_margins.top()
            + content_margins.bottom()
            + self.hint_label.sizeHint().height()
            + self.content_body_layout.spacing()
            + self.canvas_frame.sizeHint().height()
        )
        self.set_dialog_size(self._preferred_width, target_height)

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
        self.ok_button.setEnabled(self.canvas.has_frame() and point_count >= 3)

    def _save(self) -> None:
        points = self.canvas.points()
        if len(points) < 3:
            show_toast_message(self, "warn", "ROI", "Please select at least 3 points to define an ROI area.")
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


class CameraCountLineDialog(PrimeDialog):
    def __init__(
        self,
        camera: Camera,
        frame_text: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            title=f"Count Line Setting - {camera.name}",
            parent=parent,
            width=940,
            height=820,
            show_footer=True,
            ok_text="Save Count Line",
            cancel_text="Cancel",
        )
        self.setMinimumSize(900, 760)
        self.line_value = str(camera.face_count_line or "")

        self.ok_button.clicked.disconnect()
        self.ok_button.clicked.connect(self._save)

        # Add status label and Reset button to the footer
        footer_layout = self.footer_widget.layout()
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.reset_btn = PrimeButton("Reset", variant="warning", mode="outline", size="sm")
        # footer_layout: [stretch(0), cancel(1), ok(2)]
        footer_layout.insertWidget(0, self.status_label, 1)
        footer_layout.insertWidget(2, self.reset_btn)

        hint = QLabel("Select 2 points for the count line, then optionally 2 points for the direction line.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#94a3b8; font-size:13px;")

        canvas_frame = QFrame()
        canvas_frame.setObjectName("countLineCanvasFrame")
        canvas_layout = QVBoxLayout(canvas_frame)
        canvas_layout.setContentsMargins(12, 12, 12, 12)
        canvas_layout.setSpacing(0)

        self.canvas = CountLineCanvas(self)
        self.canvas.set_frame_text(frame_text)
        self.canvas.set_points(_parse_line_points(camera.face_count_line))
        self.canvas.points_changed.connect(self._update_status)
        self.reset_btn.clicked.connect(self.canvas.clear_points)
        canvas_layout.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignCenter)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        content_layout.addWidget(hint)
        content_layout.addWidget(canvas_frame, 1)
        self.set_content(content)

        self.setStyleSheet(
            self.styleSheet()
            + """
            QFrame#countLineCanvasFrame {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 12px;
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
        self.ok_button.setEnabled(self.canvas.has_frame() and point_count in {2, 4})

    def _save(self) -> None:
        points = self.canvas.points()
        if len(points) not in {2, 4}:
            show_toast_message(
                self,
                "warn",
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


class CameraTypeFormDialog(PrimeDialog):
    submitted = Signal(dict, bool)

    def __init__(
        self,
        camera_type: Optional[CameraType] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        self.camera_type = camera_type
        self.is_edit_mode = camera_type is not None
        title = "Edit Camera Type" if self.is_edit_mode else "Add Camera Type"
        ok_text = "Update Type" if self.is_edit_mode else "Create Type"

        super().__init__(
            title=title,
            parent=parent,
            width=600,
            height=520,
            show_footer=True,
            ok_text=ok_text,
            cancel_text="Cancel",
        )
        self.setMinimumSize(860, 480)

        self.ok_button.clicked.disconnect()
        self.ok_button.clicked.connect(self._submit)

        self.name_edit = PrimeInput(placeholder_text="Camera type name")
        self.protocol_edit = PrimeInput(placeholder_text="rtsp")
        self.main_url_edit = PrimeInput(placeholder_text="/Streaming/Channels/101")
        self.sub_url_edit = PrimeInput(placeholder_text="/Streaming/Channels/102")
        self.ptz_url_edit = PrimeInput(placeholder_text="/ISAPI/PTZCtrl/channels/1/continuous")
        self.network_url_edit = PrimeInput(placeholder_text="/ISAPI/System/Network/interfaces/1")

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        form.addRow("Name *", self.name_edit)
        form.addRow("Protocol", self.protocol_edit)
        form.addRow("Main URL", self.main_url_edit)
        form.addRow("Sub URL", self.sub_url_edit)
        form.addRow("PTZ URL", self.ptz_url_edit)
        form.addRow("Network URL", self.network_url_edit)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)
        content_layout.addLayout(form)
        self.set_content(content)

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
            show_toast_message(self, "warn", "Validation", "Camera type name is required.")
            return
        self.submitted.emit(self.payload(), self.is_edit_mode)


class CameraTypeManagerDialog(PrimeDialog):
    def __init__(
        self,
        camera_type_store: CameraTypeStore,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            title="Camera Types",
            parent=parent,
            width=1380,
            height=840,
            show_footer=True,
            cancel_text="Close",
        )
        self.ok_button.hide()
        self.setMinimumSize(1240, 760)
        self.camera_type_store = camera_type_store

        self.camera_type_store.changed.connect(self._populate_table)
        self.camera_type_store.error.connect(self._show_error)
        self.camera_type_store.success.connect(self._show_info)

        self.new_btn = PrimeButton("+ New Type", variant="primary", size="sm")
        self.new_btn.clicked.connect(self.open_create_dialog)

        self.search_edit = PrimeInput(placeholder_text="Search camera types...")
        self.search_edit.setMaximumWidth(320)
        self.search_edit.textChanged.connect(self._on_search_changed)

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(10)
        toolbar_layout.addWidget(self.new_btn)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.search_edit)

        self.table = PrimeDataTable(page_size=10, row_height=54, show_footer=True)
        self.table.set_columns(
            [
                PrimeTableColumn("name", "Name", width=180),
                PrimeTableColumn("protocol", "Protocol", width=100),
                PrimeTableColumn("main_url", "Main URL", width=240),
                PrimeTableColumn("sub_url", "Sub URL", width=240),
                PrimeTableColumn("ptz_url", "PTZ URL", width=240),
                PrimeTableColumn("network_url", "Network URL", width=240),
                PrimeTableColumn(
                    "actions",
                    "Actions",
                    sortable=False,
                    searchable=False,
                    width=96,
                    alignment=Qt.AlignCenter,
                ),
            ]
        )
        self.table.set_cell_widget_factory("actions", self._camera_type_action_cell)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)
        content_layout.addWidget(toolbar)
        content_layout.addWidget(self.table, 1)
        self.set_content(content, fill_height=True)

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

    def _icon_tool_btn(
        self,
        icon_name: str,
        tooltip: str,
        bg: str,
        border: str,
        size: int = 34,
        fallback_text: str = "",
    ) -> QToolButton:
        btn = QToolButton()
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(size, size)
        icon_path = os.path.join(_ICONS_DIR, icon_name)
        if os.path.exists(icon_path):
            btn.setIcon(QIcon(icon_path))
            icon_px = max(12, size - 16)
            btn.setIconSize(QSize(icon_px, icon_px))
        else:
            btn.setText(fallback_text)
        btn.setStyleSheet(f"""
            QToolButton {{
                background: {bg};
                color: #f8fafc;
                border: 1px solid {border};
                border-radius: {size // 2}px;
                font-size: 15px;
                font-weight: 700;
            }}
            QToolButton:hover {{
                border-color: #f8fafc;
            }}
            QToolButton:pressed {{
                background: {border};
            }}
            QToolButton:disabled {{
                color: #7b8090;
                border-color: #3b3f47;
                background: #2b2d33;
            }}
        """)
        return btn

    def _action_widget(self, camera_type: CameraType) -> QWidget:
        box = QWidget()
        box.setFixedWidth(72)
        box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)

        edit_btn = self._icon_tool_btn(
            "edit.svg",
            "Edit Camera Type",
            "#3578f6",
            "#4e8cff",
            fallback_text="✎",
        )
        edit_btn.clicked.connect(lambda: self.open_edit_dialog(camera_type))
        layout.addWidget(edit_btn)

        delete_btn = self._icon_tool_btn(
            "trash.svg",
            "Delete Camera Type",
            "#ef4444",
            "#ff6464",
            fallback_text="⌫",
        )
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
        confirmed = PrimeConfirmDialog.ask(
            parent=self,
            title="Delete Camera Type",
            message=f"Are you sure you want to delete '{camera_type.name}'?",
            ok_text="Delete",
            cancel_text="Cancel",
        )
        if confirmed:
            self.camera_type_store.delete_camera_type(camera_type.id)

    def _show_info(self, text: str) -> None:
        show_toast_message(self, "info", "Camera Types", text)

    def _show_error(self, text: str) -> None:
        show_toast_message(self, "error", "Camera Types", text)


class CameraFormDialog(PrimeDialog):
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
        super().__init__(
            title="Edit Camera" if camera is not None else "Add New Camera",
            parent=parent,
            width=1100,
            height=780,
            ok_text="Update Camera" if camera is not None else "Add Camera",
            cancel_text="Cancel",
        )
        self.auth_store = auth_store
        self.client_store = client_store
        self.camera_type_store = camera_type_store
        self.access_control_store = access_control_store
        self.camera = camera
        self.is_edit_mode = camera is not None
        self._default_dialog_size = (1100, 780)
        self._recorder_dialog_size = (820, 640)
        self._layout_mode_key: Optional[str] = None
        self.setObjectName("cameraFormDialog")
        self.setStyleSheet(
            self.styleSheet()
            + """
            QWidget#cameraFormBody {
                background: transparent;
            }
            QGroupBox#cameraSectionBox {
                background: #222222;
                border: 1px solid #3a424f;
                border-radius: 10px;
                padding: 0;
            }
            QLabel#cameraSectionLabel {
                color: #dbe4f3;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel {
                color: #dbe4f3;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#cameraFieldLabel {
                color: #94a3b8;
                font-size: 12px;
                font-weight: 500;
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
        try:
            self.ok_button.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.ok_button.clicked.connect(self._submit)
        self.ok_button.setFixedWidth(140)
        self.cancel_button.setFixedWidth(110)

        body_widget = QWidget()
        body_widget.setObjectName("cameraFormBody")
        root = QVBoxLayout(body_widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        self.set_content(body_widget)

        top_box, top_container = self._create_section_box("General")
        top_layout = QGridLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setHorizontalSpacing(12)
        top_layout.setVerticalSpacing(10)
        top_container.addLayout(top_layout)
        self.top_layout = top_layout
        root.addWidget(top_box)

        self.name_edit = PrimeInput()
        self.name_edit.setPlaceholderText("Enter camera name")
        self.ai_combo = self._bool_combo()
        self.process_type_combo = PrimeSelect(
            options=self._process_type_options(),
            placeholder="Select camera type",
        )
        self.process_type_combo.set_value(self._initial_process_type())
        self.process_type_combo.value_changed.connect(lambda _value: self._toggle_type_fields())

        self.name_label = QLabel("Camera Name *")
        self.ai_label = QLabel("AI Support *")
        self.process_type_label = QLabel("Camera Type *")
        top_layout.addWidget(self.name_label, 0, 0)
        top_layout.addWidget(self.name_edit, 1, 0)
        top_layout.addWidget(self.ai_label, 0, 1)
        top_layout.addWidget(self.ai_combo, 1, 1)
        top_layout.addWidget(self.process_type_label, 0, 2)
        top_layout.addWidget(self.process_type_combo, 1, 2)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(14)
        self.body_layout = body
        root.addLayout(body, 1)

        # Left column
        self.left_box, left_container = self._create_section_box("Camera Connection")
        left_fields = QVBoxLayout()
        left_fields.setContentsMargins(0, 0, 0, 0)
        left_fields.setSpacing(10)
        left_container.addLayout(left_fields)
        body.addWidget(self.left_box, 1)

        self.camera_ip_edit = PrimeInput()
        self.camera_ip_edit.setPlaceholderText("Enter camera IP")
        self.camera_port_spin = PrimeInput(
            type="number",
            minimum=1,
            maximum=65535,
            decimals=0,
            value=554,
            placeholder_text="Enter port",
        )
        self.camera_username_edit = PrimeInput()
        self.camera_username_edit.setPlaceholderText("Enter username")
        self.camera_password_edit = PrimeInput()
        self.camera_password_edit.setPlaceholderText("Enter password")
        self.camera_password_edit.setEchoMode(QLineEdit.Password)
        self.camera_type_combo = PrimeSelect(placeholder="Select camera brand")
        self.camera_type_combo.set_options(
            [{"label": item.name, "value": item.id} for item in self.camera_type_store.camera_types]
        )

        self.access_control_combo = PrimeSelect(placeholder="Select access control")
        self.access_control_combo.set_options(
            [{"label": item.name, "value": item.id} for item in self.access_control_store.access_controls]
        )
        self.access_control_combo.value_changed.connect(lambda _value: self._refresh_doors())

        self.door_combo = PrimeSelect(placeholder="Select door")

        self.camera_ip_field = self._field_block("Camera IP *", self.camera_ip_edit)
        self.camera_port_field = self._field_block("Camera Port", self.camera_port_spin)
        self.camera_username_field = self._field_block("Username", self.camera_username_edit)
        self.camera_password_field = self._field_block("Password", self.camera_password_edit)
        self.camera_type_field = self._field_block("Camera Brand", self.camera_type_combo)
        self.access_control_field = self._field_block("Access Control", self.access_control_combo)
        self.door_field = self._field_block("Door Number", self.door_combo)

        left_fields.addWidget(self.camera_ip_field)
        left_fields.addWidget(self.camera_port_field)
        left_fields.addWidget(self.camera_username_field)
        left_fields.addWidget(self.camera_password_field)
        left_fields.addWidget(self.camera_type_field)
        left_fields.addWidget(self.access_control_field)
        left_fields.addWidget(self.door_field)

        self.right_box, right_container = self._create_section_box("Processing & Clients")
        right_fields = QVBoxLayout()
        right_fields.setContentsMargins(0, 0, 0, 0)
        right_fields.setSpacing(10)
        right_container.addLayout(right_fields)
        body.addWidget(self.right_box, 1)

        self.client_1_combo = PrimeSelect(placeholder="Select Processing Client")
        self.client_2_combo = PrimeSelect(placeholder="Select Failover Client")
        self.client_3_combo = PrimeSelect(placeholder="Select Recording Client")
        self._fill_client_combo(self.client_1_combo, "process")
        self._fill_client_combo(self.client_2_combo, "process")
        self._fill_client_combo(self.client_3_combo, "record")

        self.is_process_combo = self._bool_combo()
        self.is_live_combo = self._bool_combo(default=True)
        self.is_record_combo = self._bool_combo(default=True)
        self.is_ptz_combo = self._bool_combo()
        self.forward_stream_combo = self._bool_combo()
        self.fps_delay_spin = PrimeInput(
            type="number",
            minimum=0,
            maximum=1000,
            decimals=0,
            value=5,
            placeholder_text="FPS delay",
        )

        self.client_1_field = self._field_block("Processing Client *", self.client_1_combo)
        self.client_2_field = self._field_block("Failover Client", self.client_2_combo)
        self.client_3_field = self._field_block("Recording Client", self.client_3_combo)
        self.is_process_field = self._field_block("Enable Processing", self.is_process_combo)
        self.is_live_field = self._field_block("Enable Live Stream", self.is_live_combo)
        self.is_record_field = self._field_block("Enable Recording", self.is_record_combo)
        self.is_ptz_field = self._field_block("Is Support PTZ", self.is_ptz_combo)
        self.fps_delay_field = self._field_block("FPS Delay", self.fps_delay_spin)
        self.forward_stream_field = self._field_block("Forward to Server", self.forward_stream_combo)

        right_fields.addWidget(self.client_1_field)
        right_fields.addWidget(self.client_2_field)
        right_fields.addWidget(self.client_3_field)
        right_fields.addWidget(self.is_process_field)
        right_fields.addWidget(self.is_live_field)
        right_fields.addWidget(self.is_record_field)
        right_fields.addWidget(self.is_ptz_field)
        right_fields.addWidget(self.fps_delay_field)
        right_fields.addWidget(self.forward_stream_field)

        self.face_box, face_container = self._create_section_box("Face Recognition Settings")
        face_grid = QGridLayout()
        face_grid.setContentsMargins(0, 0, 0, 0)
        face_grid.setHorizontalSpacing(12)
        face_grid.setVerticalSpacing(10)
        face_container.addLayout(face_grid)
        self.face_person_count_combo = self._bool_combo()
        self.face_color_detection_combo = self._bool_combo()
        self.face_min_size_spin = PrimeInput(
            type="number",
            minimum=0,
            maximum=10000,
            decimals=0,
            value=5,
            placeholder_text="Min face size",
        )
        self.face_max_size_spin = PrimeInput(
            type="number",
            minimum=0,
            maximum=10000,
            decimals=0,
            value=40,
            placeholder_text="Max face size",
        )
        self.face_show_rect_combo = self._bool_combo()
        face_grid.addWidget(self._field_block("Person Counting", self.face_person_count_combo), 0, 0)
        face_grid.addWidget(self._field_block("Color Detection", self.face_color_detection_combo), 0, 1)
        face_grid.addWidget(self._field_block("Min Face Size", self.face_min_size_spin), 1, 0)
        face_grid.addWidget(self._field_block("Max Face Size", self.face_max_size_spin), 1, 1)
        face_grid.addWidget(self._field_block("Show Total Faces", self.face_show_rect_combo), 2, 0)
        root.addWidget(self.face_box)

        action_bar = QHBoxLayout()
        root.addLayout(action_bar)
        action_bar.addStretch(1)

        self.roi_btn = PrimeButton("ROI", variant="secondary", mode="filled", size="sm")
        self.countline_btn = PrimeButton("Count Line", variant="secondary", mode="filled", size="sm")
        self.roi_btn.clicked.connect(self._emit_roi)
        self.countline_btn.clicked.connect(self._emit_count_line)

        if not self.is_edit_mode:
            self.roi_btn.hide()
            self.countline_btn.hide()
        action_bar.addWidget(self.countline_btn)
        action_bar.addWidget(self.roi_btn)

        if self.camera:
            self._load_camera(self.camera)
        else:
            self.camera_username_edit.setText("admin")
            self.camera_password_edit.setText("bomn1234")
            self._set_combo_value(self.client_3_combo, self._default_recorder_client_id())

        self._toggle_type_fields()
        self._refresh_doors()

    def _create_section_box(self, title: str) -> tuple[QGroupBox, QVBoxLayout]:
        box = QGroupBox()
        box.setObjectName("cameraSectionBox")
        box.setFlat(True)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        label = QLabel(title)
        label.setObjectName("cameraSectionLabel")
        layout.addWidget(label)
        return box, layout

    def _field_block(self, label_text: str, field: QWidget) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label = QLabel(label_text)
        label.setObjectName("cameraFieldLabel")
        layout.addWidget(label)
        layout.addWidget(field)
        return wrapper

    def _process_type_options(self) -> List[Dict[str, str]]:
        return [
            {"label": "License Plate Recognition", "value": "lpr"},
            {"label": "Face Recognition", "value": "face"},
            {"label": "Recorder Camera", "value": "recorder"},
        ]

    def _initial_process_type(self) -> str:
        process_type = str(getattr(self.camera, "process_type", "") or "").strip().lower()
        if process_type in {"face", "lpr", "recorder"}:
            return process_type
        if self.camera is None:
            return "recorder"
        return "lpr"

    def _set_field_label(self, field_block: QWidget, text: str) -> None:
        label = field_block.findChild(QLabel)
        if label is not None:
            label.setText(text)

    def _default_recorder_client_id(self) -> Optional[int]:
        for item in self.client_store.clients:
            if (item.type or "").strip().lower() == "record":
                return item.id
        current_value = self.client_3_combo.value()
        if current_value is not None:
            return current_value
        for option in self.client_3_combo.options:
            _label, value = PrimeSelect.normalize_option(option)
            if value is not None:
                return value
        return None

    def _recorder_name(self, camera_ip: str) -> str:
        if self.camera and self.camera.name.strip():
            return self.camera.name.strip()
        if camera_ip:
            return f"Recorder {camera_ip}"
        return "Recorder Camera"

    def _bool_combo(self, default: bool = False) -> PrimeSelect:
        combo = PrimeSelect(
            options=[
                {"label": "Yes", "value": True},
                {"label": "No", "value": False},
            ],
            placeholder="Select status",
        )
        combo.set_value(default)
        return combo

    def _fill_client_combo(self, combo: PrimeSelect, client_type: str) -> None:
        options: List[Dict[str, Any]] = []
        for item in self.client_store.clients:
            item_type = (item.type or "").strip().lower()
            if item_type == client_type or item_type not in {"process", "record"}:
                options.append({"label": f"{item.name} ({item.ip})", "value": item.id})
        combo.set_options(options)

    def _set_combo_value(self, combo: PrimeSelect, value: Any) -> None:
        combo.set_value(value)

    def _clear_layout_widgets(self, layout: QGridLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()

    def _rebuild_top_layout(self, is_recorder: bool) -> None:
        self._clear_layout_widgets(self.top_layout)
        for col in range(3):
            self.top_layout.setColumnStretch(col, 0)

        if is_recorder:
            placements = [
                (self.name_label, 0, 0),
                (self.name_edit, 1, 0),
                (self.process_type_label, 2, 0),
                (self.process_type_combo, 3, 0),
            ]
            self.top_layout.setColumnStretch(0, 1)
        else:
            placements = [
                (self.name_label, 0, 0),
                (self.ai_label, 0, 1),
                (self.process_type_label, 0, 2),
                (self.name_edit, 1, 0),
                (self.ai_combo, 1, 1),
                (self.process_type_combo, 1, 2),
            ]
            for col in range(3):
                self.top_layout.setColumnStretch(col, 1)

        for widget, row, col in placements:
            widget.show()
            self.top_layout.addWidget(widget, row, col)

    def _update_dialog_layout_mode(self, is_recorder: bool) -> None:
        layout_mode = "recorder" if is_recorder else "default"
        width, height = self._recorder_dialog_size if is_recorder else self._default_dialog_size
        if self._layout_mode_key == layout_mode:
            return
        self._layout_mode_key = layout_mode
        self._rebuild_top_layout(is_recorder)
        self.body_layout.setDirection(
            QBoxLayout.Direction.TopToBottom if is_recorder else QBoxLayout.Direction.LeftToRight
        )
        if self.isVisible():
            self.set_dialog_size(width, height)
            return
        self._preferred_width = max(360, width)
        self._preferred_height = max(220, height)

    def _toggle_type_fields(self) -> None:
        process_type = str(self.process_type_combo.value() or self._initial_process_type()).strip().lower()
        is_face = process_type == "face"
        is_recorder = process_type == "recorder"
        uses_processing_clients = process_type in {"lpr", "face"}
        shows_recording_client = process_type in {"lpr", "face", "recorder"}
        self._update_dialog_layout_mode(is_recorder)

        self.name_label.setVisible(True)
        self.name_edit.setVisible(True)
        self.ai_label.setVisible(not is_recorder)
        self.ai_combo.setVisible(not is_recorder)
        self.access_control_field.setVisible(not is_recorder)
        self.door_field.setVisible(not is_recorder)
        self.client_1_field.setVisible(uses_processing_clients)
        self.client_2_field.setVisible(uses_processing_clients)
        self.client_3_field.setVisible(shows_recording_client)
        self.is_process_field.setVisible(uses_processing_clients)
        self.is_live_field.setVisible(uses_processing_clients)
        self.is_record_field.setVisible(shows_recording_client)
        self.is_ptz_field.setVisible(uses_processing_clients)
        self.fps_delay_field.setVisible(uses_processing_clients)
        self.forward_stream_field.setVisible(False)
        self.right_box.setVisible(
            any(
                not field.isHidden()
                for field in (
                    self.client_1_field,
                    self.client_2_field,
                    self.client_3_field,
                    self.is_process_field,
                    self.is_live_field,
                    self.is_record_field,
                    self.is_ptz_field,
                    self.fps_delay_field,
                    self.forward_stream_field,
                )
            )
        )
        self.face_box.setVisible(is_face)
        self.roi_btn.setVisible(self.is_edit_mode and not is_recorder)
        self.countline_btn.setVisible(self.is_edit_mode and is_face)

        self._set_field_label(self.camera_port_field, "Camera Port *" if is_recorder else "Camera Port")
        self._set_field_label(self.camera_username_field, "Username *" if is_recorder else "Username")
        self._set_field_label(self.camera_password_field, "Password *" if is_recorder else "Password")
        self._set_field_label(self.camera_type_field, "Camera Brand *" if is_recorder else "Camera Brand")

    def _refresh_doors(self) -> None:
        selected_id = self.access_control_combo.value()
        current_door = self.door_combo.value()
        options: List[Dict[str, Any]] = []
        for ac in self.access_control_store.access_controls:
            if ac.id == selected_id:
                for idx in range(ac.ac_type.num_of_relay):
                    options.append({"label": f"Door {idx + 1}", "value": idx + 1})
                break
        self.door_combo.set_options(options)
        self.door_combo.set_value(current_door)

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
            port = 554

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
            "port": 554 if port <= 0 else max(1, min(port, 65535)),
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

        for option in self.camera_type_combo.options:
            label, value = PrimeSelect.normalize_option(option)
            label = label.strip().lower()
            if not label:
                continue
            if normalized_manufacturer in label or label in normalized_manufacturer:
                self.camera_type_combo.set_value(value)
                return

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
        process_type = str(self.process_type_combo.value() or self._initial_process_type()).strip().lower()
        is_recorder = process_type == "recorder"
        current_camera = self.camera
        camera_ip = self.camera_ip_edit.text().strip()
        camera_name = self.name_edit.text().strip()
        camera_username = self.camera_username_edit.text().strip()
        camera_password = self.camera_password_edit.text()
        camera_type_id = self.camera_type_combo.value()
        recorder_client_id = self.client_3_combo.value()
        if recorder_client_id is None:
            recorder_client_id = self._default_recorder_client_id()

        if not camera_name or not camera_ip or not camera_username or not camera_password or camera_type_id is None:
            show_toast_message(
                self,
                "warn",
                "Validation",
                "Name, camera type, username, password, and camera IP are required.",
            )
            return

        payload = {
            "name": camera_name,
            "client_id_1": None if is_recorder else self.client_1_combo.value(),
            "client_id_2": None if is_recorder else self.client_2_combo.value(),
            "client_id_3": recorder_client_id,
            "access_control_id": None if is_recorder else self.access_control_combo.value(),
            "door_number": None if is_recorder else self.door_combo.value(),
            "roi": current_camera.roi if current_camera else "",
            "is_record": self.is_record_combo.value(),
            "is_process": False if is_recorder else self.is_process_combo.value(),
            "is_live": current_camera.is_live if is_recorder and current_camera else self.is_live_combo.value(),
            "is_ptz": current_camera.is_ptz if is_recorder and current_camera else self.is_ptz_combo.value(),
            "forward_stream": current_camera.forward_stream if current_camera else False,
            "is_ai_cam": False if is_recorder else self.ai_combo.value(),
            "fps_delay": 0 if is_recorder else int(self.fps_delay_spin.value()),
            "process_type": process_type,
            "camera_type_id": camera_type_id,
            "camera_ip": camera_ip,
            "camera_username": camera_username,
            "camera_password": camera_password,
            "camera_port": int(self.camera_port_spin.value()),
            "face_person_count": self.face_person_count_combo.value(),
            "face_color_detection": self.face_color_detection_combo.value(),
            "face_min_size": int(self.face_min_size_spin.value()),
            "face_max_size": int(self.face_max_size_spin.value()),
            "face_show_rect": self.face_show_rect_combo.value(),
            "face_count_line": current_camera.face_count_line if current_camera else "",
            "online": current_camera.online if current_camera else False,
        }
        if is_recorder:
            payload.update(
                {
                    "client_id_1": None,
                    "client_id_2": None,
                    "access_control_id": None,
                    "door_number": None,
                    "is_process": False,
                    "is_ai_cam": False,
                    "face_person_count": False,
                    "face_color_detection": False,
                    "face_show_rect": False,
                    "face_count_line": "",
                }
            )
        if current_camera:
            payload["id"] = current_camera.id
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
        self._ws_connected = False
        self._ws_camera_online_by_id: Dict[int, bool] = {}
        self._scan_thread: Optional[_ScanThread] = None
        self._scanned_cameras: List[Dict[str, Any]] = []
        self._scan_loading = False
        self._status_ws = CameraStatusWsClient(self)

        self.camera_store.success.connect(self._show_info)
        self.camera_store.error.connect(self._show_error)
        self.client_store.changed.connect(self.refresh)
        self.client_store.error.connect(self._show_error)
        self.department_store.error.connect(self._show_error)
        self.department_store.changed.connect(self.refresh)
        self.auth_store.changed.connect(self.refresh)
        self._status_ws.connectionChanged.connect(self._on_ws_connection)
        self._status_ws.statusUpdate.connect(self._on_ws_status_update)

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
            ("Clients", "client.svg", "/device/clients"),
            ("Cameras", "camera.svg", "/device/cameras"),
            # ("GPS", "gps.svg", "/device/gps"),
            # ("Bodycam", "bodycam.svg", "/device/body-cam"),
            # ("Access", "activation.svg", "/device/access-control"),
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

        self.sections_splitter = QSplitter(Qt.Orientation.Vertical)
        self.sections_splitter.setChildrenCollapsible(False)
        self.sections_splitter.setHandleWidth(10)
        main_layout.addWidget(self.sections_splitter, 1)

        self.camera_section = QFrame()
        self.camera_section.setObjectName("cameraPageSectionPanel")
        camera_section_layout = QVBoxLayout(self.camera_section)
        camera_section_layout.setContentsMargins(16, 16, 16, 16)
        camera_section_layout.setSpacing(12)
        self.sections_splitter.addWidget(self.camera_section)

        camera_header = QHBoxLayout()
        camera_header.setContentsMargins(0, 0, 0, 0)
        camera_header.setSpacing(10)
        camera_section_layout.addLayout(camera_header)

        camera_title_wrap = QVBoxLayout()
        camera_title_wrap.setContentsMargins(0, 0, 0, 0)
        camera_title_wrap.setSpacing(2)
        self.camera_section_title = QLabel("Cameras")
        self.camera_section_title.setObjectName("cameraPageSectionTitle")
        self.camera_section_subtitle = QLabel("Configured cameras and their live connection settings.")
        self.camera_section_subtitle.setObjectName("cameraPageSectionSubtitle")
        camera_title_wrap.addWidget(self.camera_section_title)
        camera_title_wrap.addWidget(self.camera_section_subtitle)
        camera_header.addLayout(camera_title_wrap, 1)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(10)
        camera_section_layout.addLayout(toolbar)

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

        self.table = PrimeDataTable(page_size=20, row_height=58, show_footer=False)
        self.table.set_columns(
            [
                PrimeTableColumn("name", "Name", stretch=True),
                PrimeTableColumn("recorder", "Recorder", width=200,),
                PrimeTableColumn("type", "Type", width=112, alignment=Qt.AlignLeft | Qt.AlignVCenter),
                PrimeTableColumn("camera_ip", "Camera IP", stretch=True),
                PrimeTableColumn("username", "Username",stretch=True),
                PrimeTableColumn("password", "Password", sortable=False, searchable=False, stretch=True),
                PrimeTableColumn("record", "Record", stretch=True, alignment=Qt.AlignLeft | Qt.AlignVCenter),
                PrimeTableColumn("process", "Process", stretch=True, alignment=Qt.AlignLeft | Qt.AlignVCenter),
                PrimeTableColumn("live", "Live", stretch=True, alignment=Qt.AlignLeft | Qt.AlignVCenter),
                PrimeTableColumn("status", "Status", stretch=True, alignment=Qt.AlignLeft | Qt.AlignVCenter),
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
        camera_section_layout.addWidget(self.table, 1)

        self.scan_section = QFrame()
        self.scan_section.setObjectName("cameraPageSectionPanel")
        scan_section_layout = QVBoxLayout(self.scan_section)
        scan_section_layout.setContentsMargins(16, 16, 16, 16)
        scan_section_layout.setSpacing(12)
        self.sections_splitter.addWidget(self.scan_section)

        scan_header = QHBoxLayout()
        scan_header.setContentsMargins(0, 0, 0, 0)
        scan_header.setSpacing(10)
        scan_section_layout.addLayout(scan_header)

        scan_title_wrap = QVBoxLayout()
        scan_title_wrap.setContentsMargins(0, 0, 0, 0)
        scan_title_wrap.setSpacing(2)
        self.scan_section_title = QLabel("Scanned Cameras")
        self.scan_section_title.setObjectName("cameraPageSectionTitle")
        self.scan_section_subtitle = QLabel("Network scan results appear here. Use one row to open the add camera form.")
        self.scan_section_subtitle.setObjectName("cameraPageSectionSubtitle")
        scan_title_wrap.addWidget(self.scan_section_title)
        scan_title_wrap.addWidget(self.scan_section_subtitle)
        scan_header.addLayout(scan_title_wrap, 1)

        self.scan_count_label = QLabel("No scan results")
        self.scan_count_label.setObjectName("cameraPageSectionMeta")
        scan_header.addWidget(self.scan_count_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self.scan_btn = PrimeButton("Scan Network", variant="contrast", mode="filled", size="sm", width=100)
        self.scan_btn.clicked.connect(self._start_scan)
        scan_header.addWidget(self.scan_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self.scan_search_edit = QLineEdit()
        self.scan_search_edit.setPlaceholderText("Search scanned cameras...")
        self.scan_search_edit.textChanged.connect(self._on_scan_search_changed)
        self.scan_search_edit.setMaximumWidth(280)
        self.scan_search_edit.setObjectName("cameraSearchInput")
        scan_header.addWidget(self.scan_search_edit, 0, Qt.AlignmentFlag.AlignVCenter)

        self.scan_empty_label = QLabel("Run Scan Network to show discovered cameras here.")
        self.scan_empty_label.setObjectName("cameraScanEmpty")
        self.scan_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scan_section_layout.addWidget(self.scan_empty_label)

        self.scan_loading_wrap = QWidget()
        self.scan_loading_wrap.setMinimumHeight(150)
        scan_loading_layout = QVBoxLayout(self.scan_loading_wrap)
        scan_loading_layout.setContentsMargins(0, 0, 0, 0)
        scan_loading_layout.setSpacing(0)
        scan_loading_layout.addStretch(1)
        self.scan_spinner = _Spinner(parent=self.scan_loading_wrap)
        self.scan_spinner.hide()
        scan_loading_layout.addWidget(self.scan_spinner, 0, Qt.AlignmentFlag.AlignCenter)
        scan_loading_layout.addStretch(1)
        scan_section_layout.addWidget(self.scan_loading_wrap, 0, Qt.AlignmentFlag.AlignCenter)

        self.scan_table = PrimeDataTable(page_size=8, page_size_options=[8, 16, 32], row_height=54, show_footer=True)
        self.scan_table.set_columns(
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
                    widget_factory=self._build_scan_use_button,
                ),
            ]
        )
        scan_section_layout.addWidget(self.scan_table, 1)
        self.sections_splitter.setStretchFactor(0, 3)
        self.sections_splitter.setStretchFactor(1, 2)
        self.sections_splitter.setSizes([460, 260])

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._poll_updates)
        self.status_timer.start(10000)
        self._status_ws.connect_socket()

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
            QFrame#cameraPageSectionPanel {
                background: #222428;
                border: 1px solid #2e3138;
                border-radius: 12px;
            }
            QLabel#cameraPageSectionTitle {
                color: #f5f7fb;
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#cameraPageSectionSubtitle {
                color: #8f98a8;
                font-size: 12px;
                font-weight: 500;
            }
            QLabel#cameraPageSectionMeta {
                color: #dbe4f3;
                background: #28303a;
                border: 1px solid #36404d;
                border-radius: 9px;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#cameraScanEmpty {
                color: #8f98a8;
                font-size: 13px;
                font-weight: 500;
                padding: 18px 12px 8px 12px;
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
            QSplitter::handle:vertical {
                background: #313741;
                border-radius: 5px;
                height: 10px;
                margin: 0 140px;
            }
            QSplitter::handle:vertical:hover {
                background: #46505f;
            }
            """
        )

        self._set_scan_results([])
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

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.status_timer.stop()
        self._status_ws.close()
        return super().closeEvent(event)

    def _on_search_changed(self, text: str) -> None:
        self.search_text = text
        self.refresh()

    def _on_scan_search_changed(self, text: str) -> None:
        self.scan_table.set_filter_text(text)

    def _camera_status_value(self, cam: Camera) -> bool:
        if not self._ws_connected:
            return False
        return bool(self._ws_camera_online_by_id.get(cam.id, False))

    def _on_ws_connection(self, connected: bool) -> None:
        was_connected = self._ws_connected
        self._ws_connected = connected
        if connected:
            return
        if was_connected or self._ws_camera_online_by_id:
            self._ws_camera_online_by_id.clear()
            self._populate_table()

    def _on_ws_status_update(self, payload: Dict[str, Any]) -> None:
        camera_list = payload.get("cameras")
        if not isinstance(camera_list, list):
            return

        changed = False
        camera_by_id = {cam.id: cam for cam in self.department_store.cameras}
        for updated in camera_list:
            if not isinstance(updated, dict):
                continue
            camera_id = _as_int(updated.get("id") or updated.get("camera_id") or updated.get("cam_id"), 0)
            if camera_id <= 0:
                continue
            online = _extract_camera_online(updated)
            if online is None:
                continue
            if self._ws_camera_online_by_id.get(camera_id) != online:
                self._ws_camera_online_by_id[camera_id] = online
                changed = True
            cam = camera_by_id.get(camera_id)
            if cam is not None:
                cam.online = online

        if changed:
            self._populate_table()

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
                    "status": self._camera_status_value(cam),
                    "fps_delay": cam.fps_delay,
                    "actions": "",
                    "_camera": cam,
                }
            )
        self.table.set_rows(rows)

    def _set_scan_results(self, cameras: List[Dict[str, Any]]) -> None:
        self._scanned_cameras = list(cameras)
        self.scan_table.set_rows(self._scanned_cameras)
        self.scan_table.set_filter_text(self.scan_search_edit.text())
        self._refresh_scan_panel()

    def _refresh_scan_panel(self) -> None:
        has_results = bool(self._scanned_cameras)
        self.scan_loading_wrap.setVisible(self._scan_loading)
        self.scan_table.setVisible(has_results and not self._scan_loading)
        self.scan_empty_label.setVisible(not has_results and not self._scan_loading)
        self.scan_search_edit.setEnabled(has_results and not self._scan_loading)
        self.scan_btn.setEnabled(not self._scan_loading)
        self.scan_count_label.setVisible(not self._scan_loading)
        if self._scan_loading:
            return
        if has_results:
            self.scan_count_label.setText(f"{len(self._scanned_cameras)} found")
        else:
            self.scan_count_label.setText("No scan results")

    def _set_scan_loading(self, loading: bool) -> None:
        if self._scan_loading == loading:
            return
        self._scan_loading = loading
        if loading:
            self.scan_spinner.start()
        else:
            self.scan_spinner.stop()
        self._refresh_scan_panel()

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

    def _status_chip(self, text: str, bg: str, fg: str = "#ffffff") -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        chip = QLabel(text)
        metrics = QFontMetrics(chip.font())
        chip.setAlignment(Qt.AlignCenter)
        chip.setMinimumWidth(max(38, metrics.horizontalAdvance(text) + 22))
        chip.setMinimumHeight(24)
        chip.setMaximumHeight(24)
        chip.setStyleSheet(
            f"background:{bg}; color:{fg}; border:1px solid rgba(255,255,255,0.12); border-radius:7px; padding:2px 8px; font-size:11px; font-weight:700;"
        )
        layout.addWidget(chip)
        return box

    def _state_icon_cell(self, active: bool, icon_name: str, fallback_text: str) -> QWidget:
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignCenter)

        chip = QFrame()
        chip.setFixedSize(35,35)
        chip.setStyleSheet(
            f"""
            QFrame {{
                background: { Constants.SUCCESS if active else Constants.ERROR};
                border: none;
                border-radius: 14px;
            }}
            """
        )
        chip_layout = QHBoxLayout(chip)
        chip_layout.setContentsMargins(0, 0, 0, 0)
        chip_layout.setSpacing(0)
        chip_layout.setAlignment(Qt.AlignCenter)

        icon_label = QLabel()
        icon_label.setFixedSize(20, 20)
        icon_label.setStyleSheet("background: transparent; border: none;")
        icon_file = _icon_path(icon_name)
        if os.path.isfile(icon_file):
            icon_label.setPixmap(QIcon(icon_file).pixmap(QSize(20, 20)))
        else:
            icon_label.setText(fallback_text)
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setStyleSheet(
                "background: transparent; color:#ffffff; font-size:10px; font-weight:800;"
            )
        chip_layout.addWidget(icon_label)

        chip.setToolTip("Enabled" if active else "Disabled")
        layout.addWidget(chip)
        return box

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

    def _build_scan_use_button(self, row: Dict[str, Any]) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        button = PrimeButton("Use", "primary", size="sm")
        button.setFixedWidth(92)
        button.clicked.connect(lambda checked=False, current_row=row: self._open_add_with_scan(current_row))
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)
        return wrapper

    def _type_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        process_type = str(row.get("type") or "lpr").lower()
        if process_type == "face":
            return self._status_chip("Face", Constants.PRIMARY)
        if process_type == "recorder":
            return self._status_chip("Recorder", "#475569")
        return self._status_chip("LPR", Constants.SUCCESS)

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
        return self._state_icon_cell(bool(row.get("record")), "record.svg", "R")

    def _process_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        return self._state_icon_cell(bool(row.get("process")), "process.svg", "P")

    def _live_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        return self._state_icon_cell(bool(row.get("live")), "live.svg", "L")

    def _status_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        return self._state_icon_cell(bool(row.get("status")), "status.svg", "S")

    def _action_widget(self, cam: Camera) -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignCenter)



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
        confirmed = PrimeConfirmDialog.ask(
            parent=self,
            title="Delete Record",
            message=f"Are you sure you want to delete '{cam.name}'?",
            ok_text="Delete",
            cancel_text="Cancel",
        )
        if confirmed:
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

    def _start_scan(self) -> None:
        if self._scan_thread is not None and self._scan_thread.isRunning():
            return
        self._set_scan_loading(True)
        self._scan_thread = _ScanThread(self.camera_store.service)
        self._scan_thread.scan_done.connect(self._on_scan_done)
        self._scan_thread.scan_error.connect(self._on_scan_error)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.finished.connect(self._on_scan_finished)
        self._scan_thread.start()

    def _on_scan_done(self, cameras: List[Dict[str, Any]]) -> None:
        self._set_scan_loading(False)
        existing_ips = {
            str(getattr(camera, "camera_ip", "") or "").strip()
            for camera in self.department_store.cameras
            if str(getattr(camera, "camera_ip", "") or "").strip()
        }
        filtered_cameras = [
            camera
            for camera in cameras
            if str(camera.get("ip_address") or "").strip() not in existing_ips
        ]
        self._set_scan_results(filtered_cameras)
        if not filtered_cameras:
            message = "All scanned cameras are already added." if cameras else "No cameras found on the network."
            show_toast_message(self, "warn", "Scan", message)
            return

    def _on_scan_error(self, message: str) -> None:
        self._set_scan_loading(False)
        show_toast_message(self, "error", "Scan Error", message)

    def _on_scan_finished(self) -> None:
        self._scan_thread = None

    def _open_add_with_scan(self, scanned_camera: Dict[str, Any]) -> None:
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
        dialog._apply_scanned_camera(scanned_camera)
        dialog.exec()

    def toggle_password(self, cam: Camera) -> None:
        if cam.id in self._visible_password_camera_ids:
            self._visible_password_camera_ids.discard(cam.id)
        else:
            self._visible_password_camera_ids.add(cam.id)
        self.refresh()

    def _show_info(self, text: str) -> None:
        show_toast_message(self, "info", "Info", text)

    def _show_error(self, text: str) -> None:
        show_toast_message(self, "error", "Error", text)

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
