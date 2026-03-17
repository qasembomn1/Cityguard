from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from PySide6.QtCore import QDate, QObject, QPoint, QRunnable, QSignalBlocker, QSize, Qt, QThreadPool, QTimer, Signal,QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPaintEvent, QPen, QPixmap,QPainterPath
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCalendarWidget,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from app.models.camera import Camera
from app.services.auth.auth_service import AuthService
from app.services.home.devices.camera_service import CameraService
from app.services.home.stream.playback_service import PlaybackService
from app.ui.checkbox import PrimeCheckBox
from app.ui.select import PrimeSelect
from app.ui.toast import PrimeToastHost
from app.constants._init_ import Constants

PLAYER_COLORS = ["#16a34a", "#1e40af", "#ea580c", "#312e81"]
MPV_EMBED_PANSCAN = 1.0
_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)

MPV_PLAYBACK_ARGS = [
    "--idle=yes",
    "--keep-open=yes",
    "--no-osc",
    "--audio=no",
    "--hwdec=auto-safe",
    "--profile=sw-fast",
    "--hr-seek=yes",
    "--cache=yes",
    "--cache-pause=no",
    "--network-timeout=10",
    "--keepaspect=yes",
    "--video-unscaled=no",
    f"--panscan={MPV_EMBED_PANSCAN}",
]

RANGE_PRESETS = {
    "24h": 24 * 3600,
    "12h": 12 * 3600,
    "6h": 6 * 3600,
    "1h": 1 * 3600,
    "5m": 5 * 60,
}

RANGE_SELECT_OPTIONS = [
    {"label": "24 Hours", "value": "24h"},
    {"label": "12 Hours", "value": "12h"},
    {"label": "6 Hours", "value": "6h"},
    {"label": "1 Hour", "value": "1h"},
    {"label": "5 Minutes", "value": "5m"},
]

SPEED_SELECT_OPTIONS = [
    {"label": "1x", "value": 1.0},
    {"label": "2x", "value": 2.0},
    {"label": "3x", "value": 3.0},
    {"label": "4x", "value": 4.0},
    {"label": "5x", "value": 5.0},
    {"label": "6x", "value": 6.0},
    {"label": "7x", "value": 7.0},
    {"label": "8x", "value": 8.0},
]


def _time_to_seconds(value: str) -> int:
    parts = str(value or "").strip().split(":")
    if len(parts) != 3:
        return 0
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
    except (TypeError, ValueError):
        return 0
    return max(0, min(86399, (hours * 3600) + (minutes * 60) + seconds))


def _seconds_to_hms(value: int) -> str:
    total = max(0, min(86399, int(value or 0)))
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _format_label_time(value: int) -> str:
    total = max(0, min(86399, int(value or 0)))
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _format_day_label(day_text: str) -> str:
    date = QDate.fromString(day_text, "yyyy-MM-dd")
    if not date.isValid():
        return day_text
    return f"{day_text}  {date.toString('dddd')}"


def _segment_contains(segments: Iterable[Tuple[int, int]], value: int) -> bool:
    target = int(value or 0)
    return any(start <= target < end for start, end in segments)


def _flatten_segments(segments_by_camera: Dict[int, List[Tuple[int, int]]]) -> List[Tuple[int, int]]:
    merged: list[Tuple[int, int]] = []
    for segments in segments_by_camera.values():
        merged.extend(segments)
    merged.sort(key=lambda item: (item[0], item[1]))
    return merged

def _next_segment(segments_by_camera: Dict[int, List[Tuple[int, int]]], value: int) -> Optional[Tuple[int, int]]:
    target = int(value or 0)
    next_range: Optional[Tuple[int, int]] = None
    for segments in segments_by_camera.values():
        for start, end in segments:
            if start < target:
                continue
            if next_range is None or start < next_range[0]:
                next_range = (start, end)
    return next_range


def _segment_seek_target(start: int, end: int) -> int:
    safe_start = max(0, int(start or 0))
    safe_end = max(safe_start, int(end or safe_start))
    if safe_end - safe_start > 1:
        return safe_start + 1
    return safe_start


def _active_segment_end(segments_by_camera: Dict[int, List[Tuple[int, int]]], value: int) -> Optional[int]:
    target = int(value or 0)
    active_end: Optional[int] = None
    for segments in segments_by_camera.values():
        for start, end in segments:
            if not (start <= target < end):
                continue
            if active_end is None or end > active_end:
                active_end = end
    return active_end


class _TaskSignals(QObject):
    result = Signal(object)
    error = Signal(str)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _TaskSignals()

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:
            self.signals.error.emit(str(exc))
            return
        self.signals.result.emit(result)


class PlaybackTimeline(QWidget):
    seekRequested = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._segments_by_camera: Dict[int, List[Tuple[int, int]]] = {}
        self._camera_ids: list[int] = []
        self._camera_names: Dict[int, str] = {}
        self._visible_start = 0
        self._visible_end = 86400
        self._current_time = 0
        self.setMinimumHeight(68)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(800, 72)

    def set_data(
        self,
        camera_ids: List[int],
        camera_names: Dict[int, str],
        segments_by_camera: Dict[int, List[Tuple[int, int]]],
    ) -> None:
        self._camera_ids = list(camera_ids)
        self._camera_names = dict(camera_names)
        self._segments_by_camera = {int(key): list(value) for key, value in segments_by_camera.items()}
        self.update()

    def set_window(self, start: int, end: int) -> None:
        self._visible_start = max(0, min(86399, int(start or 0)))
        self._visible_end = max(self._visible_start + 1, min(86400, int(end or 86400)))
        self.update()

    def set_current_time(self, value: int) -> None:
        self._current_time = max(0, min(86399, int(value or 0)))
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            target = self._x_to_time(event.position().x())
            self.seekRequested.emit(target)
        super().mousePressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#222222"))

        outer = self._outer_rect()
        if outer.width() <= 0 or outer.height() <= 0:
            return

        painter.setPen(QPen(QColor("rgba(255,255,255,0.08)"), 1))
        painter.setBrush(QColor("#222222"))
        painter.drawRoundedRect(outer, 8, 8)

        plot = self._plot_rect()
        if plot.width() <= 0 or plot.height() <= 0:
            return

        if self._visible_end <= self._visible_start:
            return

        step = self._label_step(self._visible_end - self._visible_start)
        self._draw_grid(painter, plot, step)

        if not self._camera_ids:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "Select up to 4 cameras to view playback.")
            return

        row_gap = 2
        row_count = max(1, len(self._camera_ids))
        available_height = plot.height() - ((row_count - 1) * row_gap)
        row_height = max(3, min(6, available_height // row_count))
        for row_index, camera_id in enumerate(self._camera_ids):
            row_top = plot.top() + row_index * (row_height + row_gap)
            row_rect = plot.adjusted(0, row_top - plot.top(), 0, -(plot.bottom() - (row_top + row_height)))
            self._draw_row(painter, row_rect, row_index, camera_id)

        if self._visible_start <= self._current_time <= self._visible_end:
            xpos = self._time_to_x(plot, self._current_time)
            painter.setPen(QPen(QColor("#ef4444"), 1))
            painter.drawLine(xpos, plot.top() - 1, xpos, plot.bottom() + 3)

    def _draw_grid(self, painter: QPainter, plot: "QRect", step: int) -> None:
        painter.save()
        axis_font = painter.font()
        axis_font.setPointSize(7)
        painter.setFont(axis_font)
        painter.setPen(QPen(QColor("rgba(148,163,184,0.16)"), 1))
        start = self._visible_start - (self._visible_start % step)
        if start < self._visible_start:
            start += step

        for marker in range(start, self._visible_end + 1, step):
            xpos = self._time_to_x(plot, marker)
            painter.drawLine(xpos, plot.top(), xpos, plot.bottom())
            if marker != self._visible_start:
                label = _format_label_time(marker)
                painter.setPen(QColor("#94a3b8"))
                painter.drawText(xpos - 14, plot.bottom() + 9, 40, 8, Qt.AlignmentFlag.AlignLeft, label)
            painter.setPen(QPen(QColor("rgba(148,163,184,0.16)"), 1))

        xpos = self._time_to_x(plot, self._visible_end)
        painter.setPen(QColor("#cbd5e1"))
        painter.drawText(
            xpos - 14,
            plot.bottom() + 9,
            48,
            8,
            Qt.AlignmentFlag.AlignLeft,
            _format_label_time(self._visible_end),
        )
        painter.restore()

    def _draw_row(self, painter: QPainter, row_rect: "QRect", row_index: int, camera_id: int) -> None:
        base_color = QColor("rgba(255,255,255,0.12)")
        color = QColor(PLAYER_COLORS[row_index % len(PLAYER_COLORS)])
        center_y = row_rect.center().y()
        painter.setPen(QPen(base_color, 2))
        painter.drawLine(row_rect.left(), center_y, row_rect.right(), center_y)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        segment_height = min(4, max(3, row_rect.height()))
        for start, end in self._segments_by_camera.get(camera_id, []):
            if end < self._visible_start or start > self._visible_end:
                continue
            clipped_start = max(start, self._visible_start)
            clipped_end = min(end, self._visible_end)
            left = self._time_to_x(row_rect, clipped_start)
            right = self._time_to_x(row_rect, clipped_end)
            if right <= left:
                right = left + 2
            painter.drawRoundedRect(left, center_y - (segment_height // 2), max(2, right - left), segment_height, 2, 2)

    def _label_step(self, visible_span: int) -> int:
        if visible_span <= 5 * 60:
            return 30
        if visible_span <= 1 * 3600:
            return 5 * 60
        if visible_span <= 6 * 3600:
            return 15 * 60
        if visible_span <= 12 * 3600:
            return 30 * 60
        return 60 * 60

    def _time_to_x(self, rect: "QRect", value: int) -> int:
        span = max(1, self._visible_end - self._visible_start)
        ratio = (int(value) - self._visible_start) / span
        ratio = max(0.0, min(1.0, ratio))
        return rect.left() + int(rect.width() * ratio)

    def _x_to_time(self, xpos: float) -> int:
        rect = self._plot_rect()
        if rect.width() <= 0:
            return self._visible_start
        relative = (xpos - rect.left()) / rect.width()
        relative = max(0.0, min(1.0, relative))
        value = self._visible_start + int(relative * (self._visible_end - self._visible_start))
        return max(0, min(86399, value))

    def _outer_rect(self):
        return self.rect().adjusted(8, 6, -8, -6)

    def _plot_rect(self):
        return self._outer_rect().adjusted(8, 6, -8, -12)


class PlaybackMonthEdit(QDateEdit):
    clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setReadOnly(True)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space, Qt.Key.Key_Down):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class MpvPlaybackSurface(QFrame):
    playbackError = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._mpv_proc: Optional[subprocess.Popen] = None
        self._mpv_ipc = ""
        self._current_url = ""
        self._pending_url = ""
        self._reported_missing = False
        self._fit_retry_attempts = 0
        self._playback_speed = 1.0

        self.setObjectName("playbackPlayerFrame")
        self.setFrameShape(QFrame.Shape.NoFrame)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.surface = QLabel("Select a camera and a day to start playback.")
        self.surface.setObjectName("playbackPlayerSurface")
        self.surface.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.surface.setWordWrap(True)
        self.surface.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.surface.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.surface.setMinimumHeight(240)
        self.surface.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.surface, 1)

        self.placeholder_overlay = QWidget(self.surface)
        self.placeholder_overlay.setObjectName("playbackTilePlaceholder")
        self.placeholder_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.placeholder_layout = QVBoxLayout(self.placeholder_overlay)
        self.placeholder_layout.setContentsMargins(20, 20, 20, 20)
        self.placeholder_layout.setSpacing(10)
        self.placeholder_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.placeholder_icon = QLabel()
        self.placeholder_icon.setObjectName("playbackTilePlaceholderIcon")
        self.placeholder_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_layout.addWidget(self.placeholder_icon, 0, Qt.AlignmentFlag.AlignCenter)

        self.placeholder_title = QLabel("No Camera")
        self.placeholder_title.setObjectName("playbackTilePlaceholderTitle")
        self.placeholder_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_layout.addWidget(self.placeholder_title, 0, Qt.AlignmentFlag.AlignCenter)

        self.placeholder_detail = QLabel("")
        self.placeholder_detail.setObjectName("playbackTilePlaceholderDetail")
        self.placeholder_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_detail.setWordWrap(True)
        self.placeholder_layout.addWidget(self.placeholder_detail, 0, Qt.AlignmentFlag.AlignCenter)

        self._restart_timer = QTimer(self)
        self._restart_timer.setSingleShot(True)
        self._restart_timer.timeout.connect(self._start_pending)
        self._fit_retry_timer = QTimer(self)
        self._fit_retry_timer.setSingleShot(True)
        self._fit_retry_timer.timeout.connect(self._fit_stream)
        self.clear("Select a camera and a day to start playback.")

    def _sync_placeholder_geometry(self) -> None:
        self.placeholder_overlay.setGeometry(0, 0, self.surface.width(), self.surface.height())

    def _placeholder_message(self, message: str) -> tuple[str, str, str]:
        text = str(message or "").strip()
        lower = text.lower()
        if "select camera" in lower or "select cameras" in lower:
            return ("No Camera", text, "monitor.svg")
        if "loading" in lower:
            return ("Loading Video", text, "playback.svg")
        return ("No Video", text or "Playback unavailable.", "playback.svg")

    def _set_placeholder_state(self, title: str, detail: str = "", icon_name: str = "monitor.svg") -> None:
        icon_file = _icon_path(icon_name)
        if os.path.isfile(icon_file):
            self.placeholder_icon.setPixmap(QIcon(icon_file).pixmap(QSize(48, 48)))
            self.placeholder_icon.setText("")
        else:
            self.placeholder_icon.setPixmap(QPixmap())
            self.placeholder_icon.setText("[]")
        self.placeholder_title.setText(title)
        self.placeholder_detail.setText(detail)
        self.placeholder_detail.setVisible(bool(detail))
        self.surface.setText("")
        self._sync_placeholder_geometry()
        self.placeholder_overlay.show()
        self.placeholder_overlay.raise_()

    def _clear_placeholder_state(self) -> None:
        self.surface.setText("")
        self.placeholder_overlay.hide()

    def clear(self, message: str = "No playback loaded.") -> None:
        self._pending_url = ""
        self._current_url = ""
        self._stop()
        title, detail, icon_name = self._placeholder_message(message)
        self._set_placeholder_state(title, detail, icon_name)

    def load_url(self, url: str, title: str) -> None:
        self.surface.setToolTip(title or "Playback")
        if not url:
            self.clear("No record at the selected time.")
            return

        self._pending_url = url
        self._set_placeholder_state("Loading Video", "Preparing playback...", "playback.svg")

        if self._mpv_proc and self._mpv_proc.poll() is None and self._send_command(["loadfile", url, "replace"]):
            self._current_url = url
            self._send_command(["set_property", "pause", False])
            self._clear_placeholder_state()
            self._schedule_fit_stream(60, attempts=2)
            return

        self._start_pending()

    def set_paused(self, paused: bool) -> None:
        self._send_command(["set_property", "pause", bool(paused)])

    def toggle_pause(self) -> None:
        self._send_command(["cycle", "pause"])

    def set_speed(self, speed: float) -> None:
        next_speed = max(1.0, min(8.0, float(speed or 1.0)))
        self._playback_speed = next_speed
        if self._mpv_proc and self._mpv_proc.poll() is None and self._send_command(["set_property", "speed", next_speed]):
            return
        if self._pending_url:
            self._schedule_fit_stream(0, attempts=2)

    def time_pos(self) -> Optional[float]:
        value = self._request_property("time-pos")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def is_paused(self) -> Optional[bool]:
        value = self._request_property("pause")
        if value is None:
            return None
        return bool(value)

    def eof_reached(self) -> Optional[bool]:
        value = self._request_property("eof-reached")
        if value is None:
            return None
        return bool(value)

    def closeEvent(self, event) -> None:
        self._stop()
        super().closeEvent(event)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if not self.isVisible():
            self._stop()

    def _start_pending(self) -> None:
        url = self._pending_url
        if not url:
            return

        wid = int(self.surface.winId())
        if wid <= 0:
            self._restart_timer.start(80)
            return

        self._stop()
        ipc_path = os.path.join(tempfile.gettempdir(), f"mpv-playback-{wid}.sock")
        self._mpv_ipc = ipc_path
        try:
            if os.path.exists(ipc_path):
                os.unlink(ipc_path)
        except OSError:
            pass

        try:
            self._mpv_proc = subprocess.Popen(
                [
                    "mpv",
                    *MPV_PLAYBACK_ARGS,
                    f"--wid={wid}",
                    f"--input-ipc-server={ipc_path}",
                    url,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._current_url = url
            self._clear_placeholder_state()
            self._schedule_fit_stream()
        except FileNotFoundError:
            self._mpv_proc = None
            self._current_url = ""
            self._set_placeholder_state("No Video", "mpv is not installed on this system.", "playback.svg")
            if not self._reported_missing:
                self._reported_missing = True
                self.playbackError.emit("mpv is not installed on this system.")
        except Exception as exc:
            self._mpv_proc = None
            self._current_url = ""
            self._set_placeholder_state("No Video", "Unable to start playback.", "playback.svg")
            self.playbackError.emit(str(exc))

    def _stop(self) -> None:
        self._restart_timer.stop()
        self._fit_retry_timer.stop()
        self._fit_retry_attempts = 0
        if self._mpv_proc:
            try:
                self._mpv_proc.terminate()
            except Exception:
                pass
            try:
                self._mpv_proc.wait(timeout=0.4)
            except Exception:
                try:
                    self._mpv_proc.kill()
                    self._mpv_proc.wait(timeout=0.2)
                except Exception:
                    pass
            self._mpv_proc = None
        if self._mpv_ipc:
            try:
                if os.path.exists(self._mpv_ipc):
                    os.unlink(self._mpv_ipc)
            except OSError:
                pass
        self._mpv_ipc = ""

    def _send_command(self, command: List[object]) -> bool:
        if not self._mpv_ipc:
            return False
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(0.35)
            sock.connect(self._mpv_ipc)
            payload = json.dumps({"command": command}).encode("utf-8") + b"\n"
            sock.sendall(payload)
            sock.close()
            return True
        except Exception:
            return False

    def _request_property(self, name: str) -> object | None:
        if not self._mpv_ipc:
            return None
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(0.35)
            sock.connect(self._mpv_ipc)
            payload = json.dumps({"command": ["get_property", name]}).encode("utf-8") + b"\n"
            sock.sendall(payload)
            chunks: list[bytes] = []
            while True:
                part = sock.recv(4096)
                if not part:
                    break
                chunks.append(part)
                if b"\n" in part:
                    break
            sock.close()
            raw = b"".join(chunks).splitlines()
            if not raw:
                return None
            response = json.loads(raw[0].decode("utf-8", errors="ignore"))
            if response.get("error") != "success":
                return None
            return response.get("data")
        except Exception:
            return None

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_placeholder_geometry()
        if self.isVisible() and self._mpv_proc and self._mpv_proc.poll() is None:
            self._schedule_fit_stream(60, attempts=1)

    def _schedule_fit_stream(self, delay_ms: int = 120, attempts: int = 5) -> None:
        if self._mpv_proc is None or self._mpv_proc.poll() is not None:
            return
        self._fit_retry_attempts = max(self._fit_retry_attempts, attempts)
        self._fit_retry_timer.start(max(0, delay_ms))

    def _fit_stream(self) -> None:
        if self._mpv_proc is None or self._mpv_proc.poll() is not None:
            self._fit_retry_attempts = 0
            return
        applied = False
        for command in (
            ["set_property", "keepaspect", True],
            ["set_property", "video-unscaled", False],
            ["set_property", "speed", self._playback_speed],
            ["set_property", "video-zoom", 0.0],
            ["set_property", "video-pan-x", 0.0],
            ["set_property", "video-pan-y", 0.0],
            ["set_property", "panscan", MPV_EMBED_PANSCAN],
        ):
            applied = self._send_command(command) or applied
        if applied:
            self._fit_retry_attempts = 0
            return
        if self._fit_retry_attempts <= 0:
            return
        self._fit_retry_attempts -= 1
        self._fit_retry_timer.start(120)


class PlaybackPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.toast = PrimeToastHost(self)
        self.thread_pool = QThreadPool.globalInstance()
        self.playback_service = PlaybackService()

        self.current_user_name = "User"
        self.cameras: list[Camera] = []
        self.cameras_by_id: dict[int, Camera] = {}
        self.selected_camera_ids: list[int] = []
        self.available_days: list[str] = []
        self.selected_date = ""
        self.segments_by_camera: dict[int, list[tuple[int, int]]] = {}
        self.current_time = 0
        self.visible_start = 0
        self.visible_end = 86400
        self.window_key = "24h"
        self.stream_seek_offset = 0
        self._last_polled_time: Optional[int] = None
        self._stalled_poll_count = 0
        self.playback_speed = 1.0
        self._camera_item_guard = False
        self.camera_checkboxes: dict[int, PrimeCheckBox] = {}
        self._day_request_token = 0
        self._range_request_token = 0

        self._build_ui()
        self._apply_styles()

        self.player_poll_timer = QTimer(self)
        self.player_poll_timer.setInterval(1000)
        self.player_poll_timer.timeout.connect(self._sync_from_players)

        QTimer.singleShot(0, self._load_initial_data)

    def closeEvent(self, event) -> None:
        self.player_poll_timer.stop()
        for player in self.players:
            player.clear("Playback stopped.")
        super().closeEvent(event)

    def _build_ui(self) -> None:
        self.setObjectName("playbackPage")

        root = QHBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(2)

        sidebar = QFrame()
        sidebar.setObjectName("playbackSidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 14, 14, 14)
        sidebar_layout.setSpacing(12)
        sidebar.setFixedWidth(320)
        root.addWidget(sidebar, 0)

        sidebar_title = QLabel("Camera Playback")
        sidebar_title.setObjectName("playbackSidebarTitle")
        sidebar_layout.addWidget(sidebar_title)

        sidebar_copy = QLabel("Select up to 4 cameras, choose a month, then open a recorded day.")
        sidebar_copy.setObjectName("playbackSidebarCopy")
        sidebar_copy.setWordWrap(True)
        sidebar_layout.addWidget(sidebar_copy)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search camera by name or IP")
        self.search_edit.textChanged.connect(self._filter_camera_list)
        sidebar_layout.addWidget(self.search_edit)

        self.selection_label = QLabel("Selected: 0 / 4")
        self.selection_label.setObjectName("playbackSidebarMeta")
        sidebar_layout.addWidget(self.selection_label)

        self.camera_list = QListWidget()
        self.camera_list.setObjectName("playbackCameraList")
        self.camera_list.setAlternatingRowColors(False)
        self.camera_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.camera_list.setSpacing(4)
        sidebar_layout.addWidget(self.camera_list, 1)

        month_row = QHBoxLayout()
        month_row.setSpacing(8)
        sidebar_layout.addLayout(month_row)

        month_label = QLabel("Month")
        month_label.setObjectName("playbackSectionLabel")
        month_row.addWidget(month_label)

        self.month_edit = PlaybackMonthEdit()
        self.month_edit.setObjectName("playbackMonthEdit")
        self.month_edit.setDisplayFormat("yyyy-MM")
        self.month_edit.setDate(QDate.currentDate())
        self.month_edit.dateChanged.connect(self._on_month_changed)
        self.month_calendar = QCalendarWidget()
        self.month_calendar.setObjectName("playbackMonthCalendar")
        self.month_calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.month_calendar.setGridVisible(False)
        self.month_calendar.clicked.connect(self._on_month_calendar_selected)
        self.month_popup = QFrame(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.month_popup.setObjectName("playbackMonthPopup")
        month_popup_layout = QVBoxLayout(self.month_popup)
        month_popup_layout.setContentsMargins(10, 10, 10, 10)
        month_popup_layout.setSpacing(0)
        month_popup_layout.addWidget(self.month_calendar)
        self.month_edit.clicked.connect(self._toggle_month_popup)
        self._apply_month_calendar_style()
        month_row.addWidget(self.month_edit, 1)

        self.days_status_label = QLabel("Available days will appear here.")
        self.days_status_label.setObjectName("playbackSidebarMeta")
        self.days_status_label.setWordWrap(True)
        sidebar_layout.addWidget(self.days_status_label)

        self.days_list = QListWidget()
        self.days_list.setObjectName("playbackDaysList")
        self.days_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.days_list.currentItemChanged.connect(self._on_day_selected)
        sidebar_layout.addWidget(self.days_list, 1)

        content = QFrame()
        content.setObjectName("playbackContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        root.addWidget(content, 1)

        players_frame = QFrame()
        players_frame.setObjectName("playbackPlayersFrame")
        players_layout = QVBoxLayout(players_frame)
        players_layout.setContentsMargins(5, 5, 5, 5)
        players_layout.setSpacing(0)
        content_layout.addWidget(players_frame, 1)

        self.players_grid = QGridLayout()
        self.players_grid.setContentsMargins(0, 0, 0, 0)
        self.players_grid.setHorizontalSpacing(0)
        self.players_grid.setVerticalSpacing(0)
        players_layout.addLayout(self.players_grid, 1)

        self.players: list[MpvPlaybackSurface] = []
        for _ in range(4):
            player = MpvPlaybackSurface(self)
            player.playbackError.connect(self._on_player_error)
            self.players.append(player)

        timeline_card = QFrame()
        timeline_card.setObjectName("playbackTimelineCard")
        timeline_layout = QVBoxLayout(timeline_card)
        timeline_layout.setContentsMargins(5, 5, 5, 5)
        timeline_layout.setSpacing(4)
        content_layout.addWidget(timeline_card)

        timeline_top = QHBoxLayout()
        timeline_top.setContentsMargins(0, 0, 0, 0)
        timeline_top.setSpacing(8)
        timeline_layout.addLayout(timeline_top)

        timeline_top_left = QHBoxLayout()
        timeline_top_left.setContentsMargins(0, 0, 0, 0)
        timeline_top_left.setSpacing(8)
        timeline_top.addLayout(timeline_top_left, 1)

        self.segment_summary = QLabel("No ranges loaded.")
        self.segment_summary.setObjectName("playbackTimelineSummary")
        self.segment_summary.hide()
        timeline_top_left.addStretch(1)

        timeline_top_center = QHBoxLayout()
        timeline_top_center.setContentsMargins(0, 0, 0, 0)
        timeline_top_center.setSpacing(0)
        timeline_top.addLayout(timeline_top_center, 0)

        self.play_pause_btn = QPushButton("")
        self.play_pause_btn.setObjectName("playbackTimelineIconButton")
        self.play_pause_btn.setFixedSize(34, 34)
        self.play_pause_btn.clicked.connect(self._toggle_playback)
        timeline_top_center.addWidget(self.play_pause_btn, 0, Qt.AlignmentFlag.AlignCenter)
        self._update_play_pause_button(True)

        timeline_top_right = QHBoxLayout()
        timeline_top_right.setContentsMargins(0, 0, 0, 0)
        timeline_top_right.setSpacing(8)
        timeline_top.addLayout(timeline_top_right, 1)
        timeline_top_right.addStretch(1)

        self.date_chip = QLabel("No day selected")
        self.date_chip.setObjectName("playbackDateChip")
        timeline_top_right.addWidget(self.date_chip, 0, Qt.AlignmentFlag.AlignVCenter)

        self.range_select_label = QLabel("Timeline")
        self.range_select_label.setObjectName("playbackSectionLabel")
        timeline_top_right.addWidget(self.range_select_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self.range_select = PrimeSelect(RANGE_SELECT_OPTIONS, placeholder="Timeline")
        self.range_select.setMinimumWidth(148)
        self.range_select.setMaximumWidth(148)
        self.range_select.setMaximumHeight(34)
        self.range_select.button.setFixedHeight(34)
        self.range_select.value_changed.connect(self._on_range_mode_changed)
        self.range_select.set_value("24h")
        timeline_top_right.addWidget(self.range_select, 0, Qt.AlignmentFlag.AlignVCenter)

        self.speed_select_label = QLabel("Speed")
        self.speed_select_label.setObjectName("playbackSectionLabel")
        timeline_top_right.addWidget(self.speed_select_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self.speed_select = PrimeSelect(SPEED_SELECT_OPTIONS, placeholder="Speed")
        self.speed_select.setMinimumWidth(82)
        self.speed_select.setMaximumWidth(82)
        self.speed_select.setMaximumHeight(34)
        self.speed_select.button.setFixedHeight(34)
        self.speed_select.value_changed.connect(self._on_speed_changed)
        self.speed_select.set_value(self.playback_speed)
        timeline_top_right.addWidget(self.speed_select, 0, Qt.AlignmentFlag.AlignVCenter)

        self.current_time_label = QLabel("00:00:00")
        self.current_time_label.setObjectName("playbackCurrentTime")
        timeline_top_right.addWidget(self.current_time_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self.timeline = PlaybackTimeline()
        self.timeline.seekRequested.connect(self._seek_to_time)
        timeline_layout.addWidget(self.timeline)

        window_row = QHBoxLayout()
        window_row.setContentsMargins(0, 0, 0, 0)
        window_row.setSpacing(8)
        timeline_layout.addLayout(window_row)

        self.window_label = QLabel("Window: 00:00:00 - 24:00:00")
        self.window_label.setObjectName("playbackSidebarMeta")
        self.window_label.hide()

        self._rebuild_players_grid([])
        self._sync_window_widgets()

    def _apply_month_calendar_style(self) -> None:
        self.month_popup.setStyleSheet(
            """
            QFrame#playbackMonthPopup {
                background: #1b1c1f;
                border: 1px solid #101114;
                border-radius: 10px;
            }
            """
        )
        self.month_calendar.setStyleSheet(
            """
            QCalendarWidget#playbackMonthCalendar {
                background: transparent;
                border: none;
            }
            QCalendarWidget#playbackMonthCalendar QWidget#qt_calendar_navigationbar {
                background: transparent;
                min-height: 36px;
            }
            QCalendarWidget#playbackMonthCalendar QToolButton {
                color: #f5f5f5;
                background: transparent;
                border: none;
                min-width: 28px;
                min-height: 28px;
                font-weight: 700;
            }
            QCalendarWidget#playbackMonthCalendar QToolButton:hover {
                background: #2a2d31;
                border-radius: 6px;
            }
            QCalendarWidget#playbackMonthCalendar QMenu {
                background: #1b1c1f;
                color: #f5f5f5;
                border: 1px solid #101114;
            }
            QCalendarWidget#playbackMonthCalendar QSpinBox {
                background: #2a2d31;
                color: #f5f5f5;
                border: 1px solid #2f3338;
                border-radius: 8px;
                min-height: 28px;
                padding: 0 8px;
            }
            QCalendarWidget#playbackMonthCalendar QAbstractItemView:enabled {
                background: #1b1c1f;
                color: #f5f5f5;
                selection-background-color: #e7e7e7;
                selection-color: #111111;
                outline: 0;
                border: none;
            }
            """
        )

    def _month_popup_position(self) -> QPoint:
        popup_size = self.month_popup.sizeHint()
        popup_width = max(self.month_edit.width(), popup_size.width())
        popup_height = popup_size.height()
        top_left = self.month_edit.mapToGlobal(QPoint(0, self.month_edit.height() + 6))
        screen = QApplication.screenAt(top_left) or QApplication.primaryScreen()
        if screen is None:
            self.month_popup.resize(popup_width, popup_height)
            return top_left

        available = screen.availableGeometry()
        x = max(available.left(), min(top_left.x(), available.right() - popup_width + 1))
        y = top_left.y()
        if y + popup_height - 1 > available.bottom():
            above = self.month_edit.mapToGlobal(QPoint(0, -popup_height - 6))
            y = max(available.top(), above.y())
        self.month_popup.resize(popup_width, popup_height)
        return QPoint(x, y)

    def _toggle_month_popup(self) -> None:
        if self.month_popup.isVisible():
            self.month_popup.hide()
            return
        self.month_calendar.setSelectedDate(self.month_edit.date())
        self.month_popup.move(self._month_popup_position())
        self.month_popup.show()
        self.month_popup.raise_()
        self.month_calendar.setFocus()

    def _on_month_calendar_selected(self, date: QDate) -> None:
        self.month_popup.hide()
        self.month_edit.setDate(QDate(date.year(), date.month(), 1))

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget#playbackPage {
                background: #222222;
            }
            QFrame#playbackSidebar,
            QFrame#playbackContent,
            QFrame#playbackTimelineCard,
            QFrame#playbackPlayersFrame,
            QFrame#playbackPlayerFrame {
                background: #222222;
                border: 1px solid rgba(148, 163, 184, 0.14);
                border-radius: 16px;
            }
            QFrame#playbackPlayersFrame {
                background: #000000;
            }
            QFrame#playbackPlayerFrame {
                border-radius: 0px;
            }
            QLabel#playbackSidebarTitle,
            QLabel#playbackPageTitle {
                color: #f8fafc;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#playbackSidebarCopy,
            QLabel#playbackStatus,
            QLabel#playbackTimelineSummary,
            QLabel#playbackSidebarMeta {
                color: #94a3b8;
                font-size: 11px;
            }
            QLabel#playbackDateChip {
                background: rgba(30, 64, 175, 0.22);
                color: #dbeafe;
                border: 1px solid rgba(59, 130, 246, 0.30);
                border-radius: 12px;
                padding: 4px 8px;
                font-size: 10px;
                font-weight: 600;
            }
            QLabel#playbackCurrentTime {
                color: #f8fafc;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#playbackPlayerSurface {
                background: #000000;
                color: #94a3b8;
                border-radius: 0px;
                padding: 10px;
            }
            QWidget#playbackTilePlaceholder {
                background: transparent;
            }
            QLabel#playbackTilePlaceholderIcon {
                background: transparent;
            }
            QLabel#playbackTilePlaceholderTitle {
                background: transparent;
                color: #f8fafc;
                font-size: 17px;
                font-weight: 700;
            }
            QLabel#playbackTilePlaceholderDetail {
                background: transparent;
                color: #94a3b8;
                font-size: 12px;
            }
            QLabel#playbackSectionLabel {
                color: #cbd5e1;
                font-size: 12px;
                font-weight: 600;
            }
            QLineEdit,
            QDateEdit,
            QListWidget {
                background: #222222;
                color: #f8fafc;
                border: 1px solid rgba(148, 163, 184, 0.18);
                border-radius: 12px;
                padding: 10px 12px;
                selection-background-color: rgba(37, 99, 235, 0.28);
            }
            QLineEdit:focus,
            QDateEdit:focus,
            QListWidget:focus {
                border: 1px solid rgba(59, 130, 246, 0.55);
            }
            QDateEdit#playbackMonthEdit {
                background: #2a2d31;
                color: #d6d6d6;
                border: 1px solid #2f3338;
                border-radius: 10px;
                padding: 0 36px 0 16px;
                min-height: 40px;
                font-size: 14px;
            }
            QDateEdit#playbackMonthEdit:hover {
                background: #30343a;
                border: 1px solid #3a3f45;
            }
            QDateEdit#playbackMonthEdit:focus {
                background: #30343a;
                border: 1px solid #3a3f45;
            }
            QDateEdit#playbackMonthEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border: none;
                margin: 6px 8px 6px 0;
            }
            QPushButton,
            QToolButton {
                background: #222222;
                color: #f8fafc;
                border: 1px solid rgba(148, 163, 184, 0.20);
                border-radius: 12px;
                padding: 9px 14px;
                font-weight: 600;
            }
            QPushButton:hover,
            QToolButton:hover {
                background: #2a2a2a;
            }
            QPushButton#playbackTimelineIconButton {
                min-width: 34px;
                max-width: 34px;
                min-height: 34px;
                max-height: 34px;
                padding: 0;
            }
            """
        )

    def _load_initial_data(self) -> None:
        self._set_page_status("Loading cameras...")

        def job() -> object:
            auth_service = AuthService()
            user = auth_service.get_current_user()
            camera_service = CameraService()
            cameras = camera_service.list_cameras(getattr(user, "department_id", None))
            return {
                "user_name": str(getattr(user, "name", "") or "User"),
                "cameras": cameras,
            }

        task = _Task(job)
        task.signals.result.connect(self._on_initial_data_loaded)
        task.signals.error.connect(self._on_initial_data_error)
        self.thread_pool.start(task)

    def _on_initial_data_loaded(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        self.current_user_name = str(data.get("user_name") or "User")
        cameras = data.get("cameras")
        self.cameras = list(cameras) if isinstance(cameras, list) else []
        self.cameras_by_id = {int(camera.id): camera for camera in self.cameras}
        self._populate_camera_list()
        self._set_page_status(f"{len(self.cameras)} cameras loaded for {self.current_user_name}.")

    def _on_initial_data_error(self, text: str) -> None:
        self._set_page_status("Unable to load cameras.")
        self._toast_error("Playback", text or "Failed to load cameras.")

    def _populate_camera_list(self) -> None:
        with QSignalBlocker(self.camera_list):
            self.camera_list.clear()
            self.camera_checkboxes = {}
            for camera in self.cameras:
                camera_id = int(camera.id)
                item = QListWidgetItem()
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                item.setData(Qt.ItemDataRole.UserRole, int(camera.id))
                checkbox = PrimeCheckBox(f"{camera.name}  •  {camera.camera_ip or 'No IP'}")
                checkbox.toggled.connect(
                    lambda checked, current_camera_id=camera_id: self._on_camera_checkbox_toggled(
                        current_camera_id,
                        checked,
                    )
                )
                with QSignalBlocker(checkbox):
                    checkbox.setChecked(camera_id in self.selected_camera_ids)
                item.setSizeHint(checkbox.sizeHint())
                self.camera_list.addItem(item)
                self.camera_list.setItemWidget(item, checkbox)
                self.camera_checkboxes[camera_id] = checkbox
        self._filter_camera_list(self.search_edit.text())
        self._sync_camera_selection_ui()

    def _filter_camera_list(self, text: str) -> None:
        needle = str(text or "").strip().lower()
        for index in range(self.camera_list.count()):
            item = self.camera_list.item(index)
            camera_id = int(item.data(Qt.ItemDataRole.UserRole) or 0)
            camera = self.cameras_by_id.get(camera_id)
            haystack = " ".join(
                part for part in (
                    str(getattr(camera, "name", "") or ""),
                    str(getattr(camera, "camera_ip", "") or ""),
                ) if part
            ).lower()
            item.setHidden(bool(needle) and needle not in haystack)

    def _on_camera_checkbox_toggled(self, camera_id: int, checked: bool) -> None:
        if self._camera_item_guard:
            return

        if checked and camera_id not in self.selected_camera_ids:
            if len(self.selected_camera_ids) >= 4:
                checkbox = self.camera_checkboxes.get(camera_id)
                if checkbox is not None:
                    self._camera_item_guard = True
                    try:
                        with QSignalBlocker(checkbox):
                            checkbox.setChecked(False)
                    finally:
                        self._camera_item_guard = False
                self._toast_warn("Playback", "Maximum 4 cameras can be selected.")
                return
            self.selected_camera_ids.append(camera_id)
        elif not checked and camera_id in self.selected_camera_ids:
            self.selected_camera_ids.remove(camera_id)

        self._sync_camera_selection_ui()
        self._request_available_days()
        if self.selected_date:
            self._request_available_ranges(seek_time=self.current_time)
        elif not self.selected_camera_ids:
            self._clear_playback_state("Select cameras to load playback.")

    def _sync_camera_selection_ui(self) -> None:
        self.selection_label.setText(f"Selected: {len(self.selected_camera_ids)} / 4")
        self._rebuild_players_grid(self.selected_camera_ids)

    def _on_month_changed(self, value: QDate) -> None:
        normalized = QDate(value.year(), value.month(), 1)
        if value != normalized:
            with QSignalBlocker(self.month_edit):
                self.month_edit.setDate(normalized)
        self._request_available_days()

    def _request_available_days(self) -> None:
        month_text = self.month_edit.date().toString("yyyy-MM")
        if not self.selected_camera_ids:
            self.available_days = []
            self.selected_date = ""
            with QSignalBlocker(self.days_list):
                self.days_list.clear()
            return

        self._day_request_token += 1
        token = self._day_request_token
        selected_ids = list(self.selected_camera_ids)

        def job() -> object:
            service = PlaybackService()
            combined: set[str] = set()
            by_camera: dict[int, list[str]] = {}
            for camera_id in selected_ids:
                days = service.available_days(camera_id, month_text)
                by_camera[int(camera_id)] = days
                combined.update(days)
            return {
                "token": token,
                "month": month_text,
                "selected_ids": selected_ids,
                "days": sorted(combined, reverse=True),
                "by_camera": by_camera,
            }

        task = _Task(job)
        task.signals.result.connect(self._on_days_loaded)
        task.signals.error.connect(lambda text, t=token: self._on_days_error(t, text))
        self.thread_pool.start(task)

    def _on_days_loaded(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        token = int(data.get("token") or 0)
        if token != self._day_request_token:
            return

        month_text = str(data.get("month") or "")
        if month_text != self.month_edit.date().toString("yyyy-MM"):
            return

        selected_ids = list(data.get("selected_ids") or [])
        if selected_ids != self.selected_camera_ids:
            return

        days = [str(item) for item in (data.get("days") or [])]
        self.available_days = days
        self._populate_days_list(days)

        if days:
            self.days_status_label.setText(f"{len(days)} recorded day(s) found for {month_text}.")
        else:
            self.days_status_label.setText("No recorded days found for this month.")
            if self.selected_date.startswith(month_text):
                self.selected_date = ""
                self._clear_playback_state("No recordings in the selected month.")

    def _on_days_error(self, token: int, text: str) -> None:
        if token != self._day_request_token:
            return
        self.available_days = []
        self.days_list.clear()
        self.days_status_label.setText("Unable to load available days.")
        self._toast_error("Playback", text or "Failed to load available days.")

    def _populate_days_list(self, days: List[str]) -> None:
        if self.selected_date and self.selected_date not in days:
            self.selected_date = ""

        with QSignalBlocker(self.days_list):
            self.days_list.clear()
            current_item_to_select: Optional[QListWidgetItem] = None
            for day in days:
                item = QListWidgetItem(_format_day_label(day))
                item.setData(Qt.ItemDataRole.UserRole, day)
                self.days_list.addItem(item)
                if day == self.selected_date:
                    current_item_to_select = item

            if current_item_to_select is not None:
                self.days_list.setCurrentItem(current_item_to_select)
            elif days and not self.selected_date:
                self.days_list.setCurrentRow(0)

        if not self.selected_date and self.days_list.currentItem() is not None:
            selected = self.days_list.currentItem().data(Qt.ItemDataRole.UserRole)
            self.selected_date = str(selected or "")
            self._request_available_ranges()

    def _on_day_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        del previous
        if current is None:
            return
        day_text = str(current.data(Qt.ItemDataRole.UserRole) or "")
        if not day_text or day_text == self.selected_date:
            return
        self.selected_date = day_text
        self._request_available_ranges()

    def _request_available_ranges(self, seek_time: Optional[int] = None) -> None:
        if not self.selected_camera_ids or not self.selected_date:
            self._clear_playback_state("Select cameras and a recorded day.")
            return

        self._range_request_token += 1
        token = self._range_request_token
        selected_ids = list(self.selected_camera_ids)
        date_text = self.selected_date
        self.date_chip.setText(date_text)

        def job() -> object:
            service = PlaybackService()
            by_camera: dict[int, list[tuple[int, int]]] = {}
            for camera_id in selected_ids:
                by_camera[int(camera_id)] = service.available_range(camera_id, date_text)
            return {
                "token": token,
                "selected_ids": selected_ids,
                "date": date_text,
                "seek_time": seek_time,
                "segments_by_camera": by_camera,
            }

        task = _Task(job)
        task.signals.result.connect(self._on_ranges_loaded)
        task.signals.error.connect(lambda text, t=token: self._on_ranges_error(t, text))
        self.thread_pool.start(task)

    def _on_ranges_loaded(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        token = int(data.get("token") or 0)
        if token != self._range_request_token:
            return

        selected_ids = list(data.get("selected_ids") or [])
        date_text = str(data.get("date") or "")
        if selected_ids != self.selected_camera_ids or date_text != self.selected_date:
            return

        raw_segments = data.get("segments_by_camera") or {}
        self.segments_by_camera = {
            int(camera_id): [
                (int(item[0]), int(item[1]))
                for item in segments
                if isinstance(item, (list, tuple)) and len(item) >= 2
            ]
            for camera_id, segments in raw_segments.items()
        }

        merged_segments = _flatten_segments(self.segments_by_camera)
        if not merged_segments:
            self._set_page_status("No recorded ranges found for the selected day.")
            self.segment_summary.setText("No ranges available.")
            self.timeline.set_data(self.selected_camera_ids, self._camera_name_map(), self.segments_by_camera)
            self._load_streams(None)
            return

        requested_seek = data.get("seek_time")
        if requested_seek is None:
            target_time = self._pick_default_time()
        else:
            target_time = max(0, min(86399, int(requested_seek)))

        self.current_time = target_time
        self.stream_seek_offset = target_time
        self.timeline.set_data(self.selected_camera_ids, self._camera_name_map(), self.segments_by_camera)
        self._set_window_mode(self.window_key, center_time=target_time, update_button=False)
        self._sync_time_widgets()
        self._sync_summary()
        self._load_streams(target_time)

    def _on_ranges_error(self, token: int, text: str) -> None:
        if token != self._range_request_token:
            return
        self._set_page_status("Unable to load recorded ranges.")
        self._toast_error("Playback", text or "Failed to load available ranges.")

    def _pick_default_time(self) -> int:
        merged = _flatten_segments(self.segments_by_camera)
        if not merged:
            return 0
        if any(_segment_contains(segments, self.current_time) for segments in self.segments_by_camera.values()):
            return self.current_time
        return merged[0][0]

    def _resolved_seek_time(self, seek_time: Optional[int]) -> Optional[int]:
        if seek_time is None:
            return None
        target = max(0, min(86399, int(seek_time)))
        if any(_segment_contains(segments, target) for segments in self.segments_by_camera.values()):
            return target
        next_range = _next_segment(self.segments_by_camera, target)
        if next_range is not None:
            return _segment_seek_target(next_range[0], next_range[1])
        return target

    def _advance_to_next_segment(self, after_time: int) -> bool:
        next_range = _next_segment(self.segments_by_camera, max(0, min(86399, int(after_time))))
        if next_range is None:
            return False
        target_time = _segment_seek_target(next_range[0], next_range[1])
        self.current_time = target_time
        self.stream_seek_offset = target_time
        if self.window_key != "24h":
            self._set_window_mode(self.window_key, center_time=target_time, update_button=False)
        else:
            self._sync_time_widgets()
        self._load_streams(target_time)
        return True

    def _load_streams(self, seek_time: Optional[int]) -> None:
        resolved_seek_time = self._resolved_seek_time(seek_time)
        if resolved_seek_time is not None and resolved_seek_time != seek_time:
            self.current_time = resolved_seek_time
            self.stream_seek_offset = resolved_seek_time
            if self.window_key != "24h":
                self._set_window_mode(self.window_key, center_time=resolved_seek_time, update_button=False)
            else:
                self._sync_time_widgets()

        self._last_polled_time = None
        self._stalled_poll_count = 0
        loaded_any = False
        active_ids = list(self.selected_camera_ids[:4])
        self._rebuild_players_grid(active_ids)

        for index, player in enumerate(self.players):
            if index >= len(active_ids):
                player.hide()
                player.clear("Select cameras to view playback.")
                continue

            camera_id = active_ids[index]
            camera = self.cameras_by_id.get(camera_id)
            title = camera.name if camera else f"Camera {camera_id}"
            segments = self.segments_by_camera.get(camera_id, [])
            player.show()

            if resolved_seek_time is None or not segments:
                player.clear("No recorded video for this camera on the selected day.")
                continue

            if not _segment_contains(segments, resolved_seek_time):
                player.clear("No record at the selected time.")
                continue

            url = self.playback_service.build_playlist_url(camera_id, self.selected_date, resolved_seek_time)
            player.load_url(url, title)
            player.set_speed(self.playback_speed)
            loaded_any = True
            
        self._update_play_pause_button(not loaded_any)
        if loaded_any:
            self.player_poll_timer.start()
        else:
            self.player_poll_timer.stop()

    def _toggle_playback(self) -> None:
        active_players = [player for player in self.players if player.isVisible()]
        if not active_players:
            self._toast_warn("Playback", "Select cameras and a recorded day first.")
            return

        pause_state = None
        for player in active_players:
            pause_state = player.is_paused()
            if pause_state is not None:
                break

        if pause_state is None:
            if self.selected_date and self.selected_camera_ids:
                self._load_streams(self.current_time)
            return

        next_paused = not pause_state
        for player in active_players:
            player.set_paused(next_paused)
        self._update_play_pause_button(next_paused)

    def _reload_current_range(self) -> None:
        if not self.selected_camera_ids:
            self._toast_warn("Playback", "Select at least one camera.")
            return
        if not self.selected_date:
            self._toast_warn("Playback", "Select a recorded day.")
            return
        self._request_available_ranges(seek_time=self.current_time)

    def _on_range_mode_changed(self, value: object) -> None:
        mode = str(value or "24h")
        self._set_window_mode(mode)

    def _on_speed_changed(self, value: object) -> None:
        try:
            next_speed = float(value or 1.0)
        except (TypeError, ValueError):
            next_speed = 1.0
        self.playback_speed = max(1.0, min(8.0, next_speed))
        for player in self.players:
            player.set_speed(self.playback_speed)

    def _seek_to_time(self, value: int) -> None:
        self.current_time = max(0, min(86399, int(value or 0)))
        self.stream_seek_offset = self.current_time
        self._sync_time_widgets()
        self._load_streams(self.current_time)

    def _sync_from_players(self) -> None:
        visible_players = [player for player in self.players if player.isVisible()]
        if not visible_players:
            self.player_poll_timer.stop()
            return

        master: Optional[MpvPlaybackSurface] = None
        master_time_pos: Optional[float] = None
        paused_state: Optional[bool] = None

        for player in visible_players:
            if paused_state is None:
                paused_state = player.is_paused()
            time_pos = player.time_pos()
            if time_pos is None:
                continue
            if player.eof_reached() is True:
                continue
            master = player
            master_time_pos = time_pos
            break

        if master is None:
            if self._advance_to_next_segment(self.current_time + 1):
                return
            self.player_poll_timer.stop()
            self._update_play_pause_button(True)
            return

        time_pos = master_time_pos
        if time_pos is not None:
            self.current_time = max(0, min(86399, int(self.stream_seek_offset + round(time_pos))))
            self._sync_time_widgets()
            if self.window_key != "24h":
                self._set_window_mode(self.window_key, center_time=self.current_time, update_button=False)
            if not any(_segment_contains(segments, self.current_time) for segments in self.segments_by_camera.values()):
                if self._advance_to_next_segment(self.current_time + 1):
                    return

        paused = paused_state if paused_state is not None else master.is_paused()
        if paused is False and time_pos is not None:
            if self._last_polled_time == self.current_time:
                self._stalled_poll_count += 1
            else:
                self._last_polled_time = self.current_time
                self._stalled_poll_count = 0
            active_end = _active_segment_end(self.segments_by_camera, self.current_time)
            if (
                active_end is not None
                and (active_end - self.current_time) <= 1
                and self._stalled_poll_count >= 2
                and self._advance_to_next_segment(active_end)
            ):
                return
        else:
            self._last_polled_time = self.current_time if time_pos is not None else None
            self._stalled_poll_count = 0
        if paused is not None:
            self._update_play_pause_button(paused)

    def _set_window_mode(self, key: str, center_time: Optional[int] = None, update_button: bool = True) -> None:
        mode = key if key in RANGE_PRESETS else "24h"
        self.window_key = mode
        span = RANGE_PRESETS[mode]
        if mode == "24h":
            self.visible_start = 0
            self.visible_end = 86400
        else:
            center = max(0, min(86399, int(center_time if center_time is not None else self.current_time)))
            half = span // 2
            left = center - half
            right = center + half
            if left < 0:
                right = min(86400, right - left)
                left = 0
            if right > 86400:
                left = max(0, left - (right - 86400))
                right = 86400
            self.visible_start = left
            self.visible_end = max(left + 1, right)

        if update_button and hasattr(self, "range_select"):
            self.range_select.set_value(mode)

        self._sync_window_widgets()

    def _sync_window_widgets(self) -> None:
        self.timeline.set_window(self.visible_start, self.visible_end)
        if self.current_time < self.visible_start:
            self.current_time = self.visible_start
        if self.current_time > self.visible_end:
            self.current_time = self.visible_end
        self.window_label.setText(
            f"Window: {_seconds_to_hms(self.visible_start)} - {_seconds_to_hms(max(self.visible_start, self.visible_end - 1))}"
        )
        self._sync_time_widgets()

    def _sync_time_widgets(self) -> None:
        self.current_time = max(0, min(86399, int(self.current_time or 0)))
        self.current_time_label.setText(_seconds_to_hms(self.current_time))
        self.timeline.set_current_time(self.current_time)

    def _sync_summary(self) -> None:
        merged = _flatten_segments(self.segments_by_camera)
        range_count = len(merged)
        self.segment_summary.setText(
            f"{len(self.selected_camera_ids)} camera(s)  •  {range_count} recorded range(s)  •  {self.selected_date or 'No date'}"
        )

    def _set_page_status(self, text: str) -> None:
        del text

    def _camera_name_map(self) -> Dict[int, str]:
        return {
            int(camera_id): (
                self.cameras_by_id.get(int(camera_id)).name
                if self.cameras_by_id.get(int(camera_id)) is not None
                else f"Camera {camera_id}"
            )
            for camera_id in self.selected_camera_ids
        }

    def _clear_playback_state(self, message: str) -> None:
        self.segments_by_camera = {}
        self.segment_summary.setText("No ranges loaded.")
        self._set_page_status(message)
        self.date_chip.setText("No day selected")
        self.timeline.set_data(self.selected_camera_ids, self._camera_name_map(), self.segments_by_camera)
        self.player_poll_timer.stop()
        for player in self.players:
            player.clear(message)

    def _rebuild_players_grid(self, active_camera_ids: List[int]) -> None:
        while self.players_grid.count():
            item = self.players_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        for row in range(2):
            self.players_grid.setRowStretch(row, 0)
        for col in range(2):
            self.players_grid.setColumnStretch(col, 0)

        count = min(4, len(active_camera_ids))
        if count <= 1:
            layout_positions = [(0, 0)]
        else:
            layout_positions = [(0, 0), (0, 1), (1, 0), (1, 1)]

        if count <= 1:
            self.players_grid.setRowStretch(0, 1)
            self.players_grid.setColumnStretch(0, 1)
        else:
            for row in range(2):
                self.players_grid.setRowStretch(row, 1)
            for col in range(2):
                self.players_grid.setColumnStretch(col, 1)

        for index, player in enumerate(self.players):
            if index < count:
                row, col = layout_positions[index]
                self.players_grid.addWidget(player, row, col)
                player.show()
            else:
                player.hide()
                player.clear("Select cameras to view playback.")

    def _rebuild_legend(self) -> None:
        return
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        p.fillPath(path, QColor(Constants.DARK_BG))   # dark bg — cards float above it
        super().paintEvent(event)

    def _update_play_pause_button(self, paused: bool) -> None:
        icon_type = (
            QStyle.StandardPixmap.SP_MediaPlay
            if paused
            else QStyle.StandardPixmap.SP_MediaPause
        )
        tooltip = "Play" if paused else "Pause"
        self.play_pause_btn.setIcon(self.style().standardIcon(icon_type))
        self.play_pause_btn.setIconSize(QSize(18, 18))
        self.play_pause_btn.setToolTip(tooltip)

    def _on_player_error(self, text: str) -> None:
        self._toast_error("Playback", text)

    def _toast_error(self, summary: str, detail: str = "", life: int = 4200) -> None:
        self.toast.error(summary, detail, life)

    def _toast_warn(self, summary: str, detail: str = "", life: int = 3600) -> None:
        self.toast.warn(summary, detail, life)
