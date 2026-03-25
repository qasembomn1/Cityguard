from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass, field
from math import isqrt
from typing import TYPE_CHECKING, Dict, List, Optional

from PySide6.QtCore import QEvent, QMimeData, QObject, QPoint, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtGui import QAction, QColor, QDrag, QIcon, QPainter, QPainterPath, QPen, QPixmap, QRegion
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QScrollArea,
    QStackedWidget,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from app.models.department import DepartmentResponse
from app.models.screen import ScreenResponse
from app.models.lpr.region import plate_region
from app.services.home.stream.screen_service import ScreenService
from app.store.home.stream.screen_store import ScreenStore
from app.ui.select import PrimeSelect
from app.ui.toast import PrimeToastHost
from app.utils.env import resolve_http_base_url
from app.views.home.stream.screens import ScreensManagerDialog as StreamScreensManagerDialog
try:
    from PySide6.QtWebSockets import QWebSocket
except Exception:  # pragma: no cover - optional at runtime
    QWebSocket = None

if TYPE_CHECKING:
    from app.views.home.devices.cameras import Camera as DevicesCamera
    from app.views.home.devices.cameras import Client as DevicesClient
    from app.views.home.devices.cameras import ClientStore as DevicesClientStore
    from app.views.home.devices.cameras import DepartmentStore as DevicesDepartmentStore


# ============================================================
# Models
# ============================================================

@dataclass
class SavedScreenConfig:
    id: int
    screen_type: int
    is_main: bool = False
    cameras: List[Dict[str, int]] = field(default_factory=list)


# ============================================================
# API + RTSP
# ============================================================

MPV_EMBED_PANSCAN = 1.0
MAIN_SCREEN_OPTION = "__main_screen__"

MPV_ARGS = [
    "--idle=yes",
    "--keep-open=yes",
    "--no-osc",
    "--profile=low-latency",
    "--untimed",
    "--audio=no",
    "--demuxer-lavf-analyzeduration=0",
    "--demuxer-lavf-probesize=32",
    "--demuxer-lavf-buffersize=4096",
    "--demuxer-lavf-o=rtsp_transport=tcp,fflags=nobuffer,flags=low_delay",
    "--no-cache",
    "--input-default-bindings=no",
    "--input-vo-keyboard=no",
    "--keepaspect=yes",
    "--video-unscaled=no",
    "--aspect=16:9"
]
_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _safe_delete_later(widget: Optional[QObject]) -> None:
    if widget is None:
        return
    try:
        widget.deleteLater()
    except RuntimeError:
        pass


def _allow_horizontal_shrink(widget: QWidget) -> None:
    widget.setMinimumWidth(0)
    size_policy = widget.sizePolicy()
    size_policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
    widget.setSizePolicy(size_policy)


def _apply_sidebar_icon(label: QLabel, icon_name: str, size: int, fallback: str = "") -> None:
    label.setAlignment(Qt.AlignCenter)
    icon_file = _icon_path(icon_name)
    if os.path.isfile(icon_file):
        label.setPixmap(QIcon(icon_file).pixmap(QSize(size, size)))
        label.setText("")
        return
    label.setPixmap(QPixmap())
    label.setText(fallback)


class RoundedClipFrame(QFrame):
    def __init__(self, radius: int = 18, parent=None):
        super().__init__(parent)
        self._radius = radius

    def resizeEvent(self, event):
        if self.width() > 0 and self.height() > 0:
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), self._radius, self._radius)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        super().resizeEvent(event)


def _grid_size_value(value: object, default: int = 2) -> int:
    if isinstance(value, str):
        import re

        matches = re.findall(r"\d+", value)
        if len(matches) >= 2 and matches[0] == matches[1]:
            value = matches[0]
        elif len(matches) == 1:
            value = matches[0]
    try:
        size = int(value)
    except (TypeError, ValueError):
        return default
    if 2 <= size <= 8:
        return size
    if size > 8:
        root = isqrt(size)
        if root * root == size and 2 <= root <= 8:
            return root
    if size <= 0:
        return default
    return default


def _compose_rtsp_url(ip: str, username: str, password: str, port: int, path: str = "") -> str:
    host = (ip or "").strip()
    if not host:
        return ""
    

    if username and password:
        return f"rtsp://{username}:{password}@{host}:{port}{path}"
    else:
        return f"rtsp://{host}:{port}{path}1"


    


def _camera_ip(camera: object) -> str:
    return str(getattr(camera, "camera_ip", "") or getattr(camera, "ip", "") or "").strip()


def _camera_rtsp_urls(camera: object) -> tuple[str, str, str]:
    ip = _camera_ip(camera)
    username = str(getattr(camera, "camera_username", "") or "").strip()
    password = str(getattr(camera, "camera_password", "") or "")
    port = _as_int(getattr(camera, "camera_port", None), 554)
    camera_type = getattr(camera, "camera_type", None)
    if not isinstance(camera_type, dict):
        camera_type = {}

    main_path = str(camera_type.get("main_url"))
    sub_path = str(camera_type.get("sub_url"))

    rtsp_main = _compose_rtsp_url(ip=ip, username=username, password=password, port=port, path=main_path)
    rtsp_sub = _compose_rtsp_url(ip=ip, username=username, password=password, port=port, path=sub_path)
    return rtsp_sub, rtsp_main


def _base_http_url() -> str:
    return resolve_http_base_url()


def _monitor_ws_url() -> str:
    raw = os.getenv("MONITOR_WS_URL", "").strip()
    if raw:
        return raw
    parsed = urllib.parse.urlparse(_base_http_url())
    host = parsed.netloc or parsed.path
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{host}/api/v1/monitor/ws"


def _result_image_url(camera_or_id, filename: Optional[str] = None) -> str:
    if isinstance(camera_or_id, dict):
        camera_id = _as_int(camera_or_id.get("cam_id") or camera_or_id.get("camera_id"), 0)
        filename = str(camera_or_id.get("filename") or camera_or_id.get("file") or filename or "").strip()
        ip = str(camera_or_id.get("ip") or "").strip()
        port = _as_int(camera_or_id.get("port"), 0)
        clean_name = os.path.basename(filename)
        if not clean_name or camera_id <= 0 or not ip or port <= 0:
            return ""
        return f"http://{ip}:{port}/image/{camera_id}/crop_{urllib.parse.quote(clean_name)}"
    else:
        camera_id = _as_int(camera_or_id, 0)
        filename = str(filename or "").strip()

    clean_name = os.path.basename(filename)
    if not clean_name or camera_id <= 0:
        return ""
    return f"{_base_http_url()}/image/{camera_id}/crop_{urllib.parse.quote(clean_name)}"


def _record_filename(record: dict) -> str:
    return os.path.basename(str(record.get("filename") or record.get("file") or "").strip())


def _result_full_image_url(record: dict) -> str:
    camera_id = _as_int(record.get("cam_id") or record.get("camera_id"), 0)
    filename = _record_filename(record)
    if not filename or camera_id <= 0:
        return ""

    explicit = str(
        record.get("image")
        or record.get("image_url")
        or record.get("face")
        or record.get("frame_url")
        or record.get("url")
        or ""
    ).strip()
    if explicit.startswith(("http://", "https://", "data:image/")):
        return explicit
    if explicit.startswith("/"):
        return f"{_base_http_url()}{explicit}"

    ip = str(record.get("ip") or "").strip()
    port = _as_int(record.get("port"), 0)
    encoded = urllib.parse.quote(filename)
    if ip and port > 0:
        return f"http://{ip}:{port}/image/{camera_id}/{encoded}"
    return f"{_base_http_url()}/image/{camera_id}/{encoded}"


def _result_crop_image_url(record: dict, process_type: str) -> str:
    explicit = str(
        record.get("crop_face")
        or record.get("cropped_face")
        or record.get("crop_image")
        or ""
    ).strip()
    if explicit.startswith(("http://", "https://", "data:image/")):
        return explicit
    if explicit.startswith("/"):
        return f"{_base_http_url()}{explicit}"

    filename = _record_filename(record)
    camera_id = _as_int(record.get("cam_id") or record.get("camera_id"), 0)
    if not filename or camera_id <= 0:
        return _result_full_image_url(record)

    ip = str(record.get("ip") or "").strip()
    port = _as_int(record.get("port"), 0)
    encoded_name = urllib.parse.quote(filename)
    record_type = str(record.get("type") or "").strip().lower()
    is_face_crop_name = process_type == "face" and (record_type == "face_result" or filename.startswith("face_"))
    crop_name = encoded_name if is_face_crop_name or filename.startswith("crop_") else urllib.parse.quote(f"crop_{filename}")

    if ip and port > 0:
        return f"http://{ip}:{port}/image/{camera_id}/{crop_name}"
    return f"{_base_http_url()}/image/{camera_id}/{crop_name}"


def _record_created_text(record: dict) -> str:
    return str(
        record.get("created")
        or record.get("created_at")
        or record.get("timestamp")
        or record.get("datetime")
        or record.get("date")
        or "-"
    ).strip() or "-"


def _display_value(value: object) -> str:
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(parts) if parts else "-"
    if isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=True)
        return text if text else "-"
    text = str(value or "").strip()
    return text or "-"


def _record_confidence_value(record: dict) -> Optional[float]:
    for key in ("confidence", "score", "conf"):
        raw = record.get(key)
        if raw in (None, ""):
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def _confidence_percent(raw_value: object) -> int:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return 0
    if 0.0 <= value <= 1.0:
        value *= 100.0
    return max(0, min(100, int(round(value))))


def _confidence_text(record: dict) -> str:
    confidence = _record_confidence_value(record)
    if confidence is None:
        return "-"
    return f"{_confidence_percent(confidence)}%"


def _resolved_lpr_region(record: dict) -> str:
    return plate_region(record.get("region"), record.get("plate_no"))


class MonitorWsClient(QObject):
    lprResult = Signal(int, dict)
    faceResult = Signal(int, dict)
    statusUpdate = Signal(dict)
    connectionChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._url = _monitor_ws_url()
        self._ws = QWebSocket() if QWebSocket is not None else None
        self._reconnect = QTimer(self)
        self._reconnect.setSingleShot(True)
        self._reconnect.setInterval(3000)
        self._reconnect.timeout.connect(self.connect_socket)

        if self._ws is not None:
            self._ws.connected.connect(self._on_connected)
            self._ws.textMessageReceived.connect(self._on_message)
            self._ws.disconnected.connect(self._on_disconnected)

    def connect_socket(self) -> None:
        if self._ws is None:
            return
        self._ws.open(QUrl(self._url))

    def close(self) -> None:
        self._reconnect.stop()
        if self._ws is not None:
            self._ws.close()

    def _on_connected(self) -> None:
        self.connectionChanged.emit(True)

    def _on_disconnected(self) -> None:
        self.connectionChanged.emit(False)
        if not self._reconnect.isActive():
            self._reconnect.start()

    def _on_message(self, raw: str) -> None:
        try:
            message = json.loads(raw)
        except Exception:
            return
        msg_type = str(message.get("type") or "")
        payload = message.get("payload")
        if msg_type == "status_update" and isinstance(payload, dict):
            self.statusUpdate.emit(payload)
            return
        if msg_type == "result":
            item = payload[0] if isinstance(payload, list) and payload else payload
            if isinstance(item, dict):
                cam_id = _as_int(item.get("cam_id"), 0)
                if cam_id:
                    self.lprResult.emit(cam_id, item)
            return
        if msg_type == "face_result":
            items = payload if isinstance(payload, list) else [payload]
            for item in items:
                if not isinstance(item, dict):
                    continue
                cam_id = _as_int(item.get("cam_id"), 0)
                if cam_id:
                    self.faceResult.emit(cam_id, item)


class ResultCard(QFrame):
    opened = Signal(dict)

    def __init__(
        self,
        process_type: str,
        record: dict,
        camera_id: int,
        image_url: str,
        net: QNetworkAccessManager,
        parent=None,
    ):
        super().__init__(parent)
        self.record = record
        self.process_type = process_type
        self._net = net
        self._reply = None
        self._image_url = image_url
        self.setObjectName("resultCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMaximumHeight(100)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click to view record details")
        self.setStyleSheet(
            """
            QFrame#resultCard {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(24, 30, 39, 0.98),
                    stop:1 rgba(16, 22, 30, 0.98));
                border: 1px solid rgba(72, 85, 102, 0.88);
                border-top: 1px solid rgba(203, 213, 225, 0.12);
                border-radius: 14px;
            }
            QFrame#resultCard:hover {
                border: 1px solid rgba(96, 165, 250, 0.94);
                border-top: 1px solid rgba(191, 219, 254, 0.18);
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(29, 38, 51, 0.99),
                    stop:1 rgba(18, 26, 37, 0.99));
            }
            QLabel#cardTitle {
                color: #f8fafc;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#cardSubtle {
                color: #9ca3af;
                font-size: 11px;
            }
            QLabel#cardChip {
                background: rgba(37, 99, 235, 0.18);
                color: #bfdbfe;
                border: 1px solid rgba(96, 165, 250, 0.34);
                border-radius: 7px;
                padding: 2px 7px;
                font-size: 10px;
                font-weight: 600;
            }
            """
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(10)

        self.thumb = QLabel()
        self.thumb.setFixedSize(136, 88)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setScaledContents(True)
        self.thumb.setStyleSheet("background:#0b0f13;border:1px solid #2d3440;border-radius:8px;color:#6b7280;")
        self.thumb.setText("Loading...")
        root.addWidget(self.thumb)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(4)
        root.addLayout(body, 1)

        created = str(record.get("created") or record.get("timestamp") or "-")
        if process_type == "face":
            gender = str(record.get("gender") or "-")
            age = str(record.get("age") or "-")
            title = f"{gender} | Age {age}"
            chip_val = str(record.get("cam_id") or camera_id)
            meta = f"Camera #{chip_val}"
        else:
            title = str(record.get("plate_no") or "Unknown Plate")
            chip_val = _confidence_text(record)
            if chip_val == "-":
                chip_val = "LPR"
            color = str(record.get("color") or "-")
            region = _resolved_lpr_region(record)
            meta = f"{region} | {color}"

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("cardTitle")
        top.addWidget(title_lbl, 1)
        chip = QLabel(chip_val)
        chip.setObjectName("cardChip")
        top.addWidget(chip, 0, Qt.AlignRight)
        body.addLayout(top)

        meta_lbl = QLabel(meta)
        meta_lbl.setObjectName("cardSubtle")
        body.addWidget(meta_lbl)

        created_lbl = QLabel(created)
        created_lbl.setObjectName("cardSubtle")
        body.addWidget(created_lbl)
        body.addStretch()

        self._load_image()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.opened.emit(dict(self.record))
            event.accept()
            return
        super().mousePressEvent(event)

    def _load_image(self) -> None:
        if not self._image_url:
            self.thumb.setText("No Image")
            return
        req = QNetworkRequest(QUrl(self._image_url))
        self._reply = self._net.get(req)
        self._reply.finished.connect(self._on_image_done)

    def _on_image_done(self) -> None:
        reply = self._reply
        self._reply = None
        if reply is None:
            return
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.thumb.setText("Image Error")
                return
            payload = bytes(reply.readAll())
            pix = QPixmap()
            if not pix.loadFromData(payload):
                self.thumb.setText("No Image")
                return
            scaled = pix.scaled(self.thumb.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            self.thumb.setPixmap(scaled)
            self.thumb.setText("")
        finally:
            reply.deleteLater()


class RecordImageLabel(QLabel):
    def __init__(self, net: QNetworkAccessManager, fallback_text: str = "No Image", parent=None):
        super().__init__(parent)
        self._net = net
        self._reply = None
        self._original = QPixmap()
        self._image_url = ""
        self._fallback_text = fallback_text
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(False)
        self.setText(fallback_text)

    def set_image_url(self, url: str) -> None:
        self._abort_reply()
        self._original = QPixmap()
        self._image_url = str(url or "").strip()
        if not self._image_url:
            self.setPixmap(QPixmap())
            self.setText(self._fallback_text)
            return
        self.setPixmap(QPixmap())
        self.setText("Loading...")
        if self.isVisible():
            self._start_request()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._reply is None and self._original.isNull() and self._image_url:
            self._start_request()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_scaled()

    def _start_request(self) -> None:
        if not self._image_url:
            return
        self._reply = self._net.get(QNetworkRequest(QUrl(self._image_url)))
        self._reply.finished.connect(self._on_done)

    def _abort_reply(self) -> None:
        if self._reply is None:
            return
        try:
            self._reply.abort()
        except Exception:
            pass
        self._reply.deleteLater()
        self._reply = None

    def _on_done(self) -> None:
        reply = self._reply
        self._reply = None
        if reply is None:
            return
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.setText(self._fallback_text)
                return
            pix = QPixmap()
            if not pix.loadFromData(bytes(reply.readAll())):
                self.setText(self._fallback_text)
                return
            self._original = pix
            self._apply_scaled()
        finally:
            reply.deleteLater()

    def _apply_scaled(self) -> None:
        if self._original.isNull():
            return
        size = self.size()
        if size.width() <= 1 or size.height() <= 1:
            return
        scaled = self._original.scaled(
            size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.setPixmap(scaled)
        self.setText("")


class RecordDetailsDialog(QDialog):
    def __init__(
        self,
        process_type: str,
        record: dict,
        camera_name: str,
        net: QNetworkAccessManager,
        parent=None,
    ):
        super().__init__(parent)
        self._process_type = str(process_type or "lpr").strip().lower()
        self._record = dict(record or {})
        self._camera_name = camera_name or f"Camera #{_as_int(self._record.get('cam_id'), 0)}"

        self.setWindowTitle("Detection Details")
        self.resize(1080, 760)
        self.setMinimumSize(920, 680)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        root.addLayout(grid, 1)

        full_card = self._image_card(
            "Full Camera Frame",
            net,
            _result_full_image_url(self._record) or _result_crop_image_url(self._record, self._process_type),
            "No Frame",
            minimum_height=360,
        )
        grid.addWidget(full_card, 0, 0, 2, 2)

        crop_title = "Face Crop" if self._process_type == "face" else "Plate Crop"
        crop_card = self._image_card(
            crop_title,
            net,
            _result_crop_image_url(self._record, self._process_type),
            "No Crop",
            minimum_height=240,
        )
        grid.addWidget(crop_card, 0, 2, 1, 1)

        highlight_card = QFrame()
        highlight_card.setObjectName("detailHighlightCard")
        highlight_layout = QVBoxLayout(highlight_card)
        highlight_layout.setContentsMargins(18, 18, 18, 18)
        highlight_layout.setSpacing(8)

        if self._process_type == "face":
            hero_label = "Gender"
            hero_value = _display_value(self._record.get("gender"))
        else:
            hero_label = "Plate Number"
            hero_value = _display_value(self._record.get("plate_no"))

        hero_title = QLabel(hero_label)
        hero_title.setObjectName("detailMuted")
        hero_text = QLabel(hero_value)
        hero_text.setObjectName("detailPlateNumber")
        hero_text.setWordWrap(True)
        highlight_layout.addWidget(hero_title)
        highlight_layout.addWidget(hero_text)
        highlight_layout.addStretch(1)
        grid.addWidget(highlight_card, 1, 2, 1, 1)

        info_card = QFrame()
        info_card.setObjectName("detailInfoCard")
        info_layout = QGridLayout(info_card)
        info_layout.setContentsMargins(18, 18, 18, 18)
        info_layout.setHorizontalSpacing(14)
        info_layout.setVerticalSpacing(14)
        root.addWidget(info_card)

        info_items = self._info_items()
        for index, (label_text, value_text) in enumerate(info_items):
            card = QFrame()
            card.setObjectName("detailMetricCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)
            label = QLabel(label_text)
            label.setObjectName("detailMuted")
            card_layout.addWidget(label)
            card_layout.addWidget(self._metric_value_widget(label_text, value_text))
            info_layout.addWidget(card, index // 4, index % 4)
        root.addWidget(info_card)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("detailGhostButton")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn, 0)
        root.addLayout(footer)

        self.setStyleSheet(
            """
            QDialog {
                background: #171b22;
                color: #f8fafc;
            }
            QFrame#detailImageCard, QFrame#detailHighlightCard, QFrame#detailInfoCard {
                background: #1f242d;
                border: 1px solid #2f3642;
                border-radius: 16px;
            }
            QFrame#detailMetricCard {
                background: #141922;
                border: 1px solid #2a3140;
                border-radius: 12px;
            }
            QLabel#detailCardTitle {
                background: transparent;
                border: none;
                color: #f8fafc;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#detailMuted {
                background: transparent;
                border: none;
                color: #94a3b8;
                font-size: 12px;
            }
            QLabel#detailPlateNumber {
                background: transparent;
                border: none;
                color: #34d399;
                font-size: 28px;
                font-weight: 800;
                letter-spacing: 1px;
            }
            QLabel#detailMetricValue {
                background: transparent;
                border: none;
                color: #f8fafc;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#detailProgressValue {
                background: transparent;
                border: none;
                color: #f8fafc;
                font-size: 13px;
                font-weight: 800;
            }
            QProgressBar#detailConfidenceBar {
                background: #0f1722;
                border: 1px solid #2a3140;
                border-radius: 6px;
                min-height: 10px;
                max-height: 10px;
                text-align: center;
            }
            QProgressBar#detailConfidenceBar::chunk {
                background: #2563eb;
                border-radius: 5px;
            }
            QPushButton#detailGhostButton {
                background: #27303d;
                border: 1px solid #3a4555;
                border-radius: 12px;
                color: #e2e8f0;
                font-size: 13px;
                font-weight: 600;
                min-height: 42px;
                padding: 0 18px;
            }
            QPushButton#detailGhostButton:hover {
                background: #313b4a;
            }
            """
        )

    def _image_card(
        self,
        title: str,
        net: QNetworkAccessManager,
        image_url: str,
        fallback_text: str,
        minimum_height: int,
    ) -> QWidget:
        frame = QFrame()
        frame.setObjectName("detailImageCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        title_label = QLabel(title)
        title_label.setObjectName("detailCardTitle")
        layout.addWidget(title_label)

        image = RecordImageLabel(net, fallback_text)
        image.setMinimumHeight(minimum_height)
        image.setStyleSheet("background:#090d12;border:1px solid #1f2937;border-radius:14px;color:#64748b;")
        image.set_image_url(image_url)
        layout.addWidget(image, 1)
        return frame

    def _metric_value_widget(self, label_text: str, value_text: str) -> QWidget:
        if self._process_type == "lpr" and label_text == "Confidence":
            value = _confidence_percent(_record_confidence_value(self._record))

            wrapper = QWidget()
            layout = QVBoxLayout(wrapper)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)

            percent = QLabel(f"{value}%")
            percent.setObjectName("detailProgressValue")
            layout.addWidget(percent)

            bar = QProgressBar()
            bar.setObjectName("detailConfidenceBar")
            bar.setRange(0, 100)
            bar.setValue(value)
            bar.setTextVisible(False)
            layout.addWidget(bar)
            return wrapper

        value = QLabel(value_text)
        value.setObjectName("detailMetricValue")
        value.setWordWrap(True)
        return value

    def _info_items(self) -> List[tuple[str, str]]:
        common = [
            ("Camera", _display_value(self._camera_name)),
            ("Camera ID", _display_value(self._record.get("cam_id") or self._record.get("camera_id"))),
            ("Detected At", _record_created_text(self._record)),
        ]
        if self._process_type == "face":
            return common + [
                ("Gender", _display_value(self._record.get("gender"))),
                ("Age", _display_value(self._record.get("age"))),
                ("Top Color", _display_value(self._record.get("top_color") or self._record.get("face_color"))),
                ("Bottom Color", _display_value(self._record.get("bottom_color") or self._record.get("hair_color"))),
            ]

        confidence_text = _confidence_text(self._record)
        return common + [
            ("Plate Number", _display_value(self._record.get("plate_no"))),
            ("Region", _resolved_lpr_region(self._record)),
            ("Color", _display_value(self._record.get("color"))),
            ("Confidence", confidence_text),
        ]



class ModernButton(QPushButton):
    def __init__(self, text: str = "", icon=None, parent=None):
        super().__init__(text, parent)
        if icon is not None:
            self.setIcon(icon)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(36)

    def set_icon_only(self, icon: QIcon, tooltip: str, button_size: int = 38, icon_size: int = 18) -> None:
        self.setObjectName("streamIconButton")
        self.setText("")
        self.setToolTip(tooltip)
        self.setIcon(icon)
        self.setIconSize(QSize(icon_size, icon_size))
        self.setFixedSize(button_size, button_size)


class CameraQueuePanel(QFrame):
    closed = Signal()

    def __init__(
        self,
        lpr_result_queues: Dict[int, List[dict]],
        face_result_queues: Dict[int, List[dict]],
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("cameraQueuePanel")
        self.setMinimumWidth(0)
        self._camera = None
        self._camera_id = 0
        self._process_type = "lpr"
        self._lpr_result_queues = lpr_result_queues
        self._face_result_queues = face_result_queues
        self._net = QNetworkAccessManager(self)
        self._queue_signature: tuple[int, str] = (-1, "")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)
        self.panel_title = QLabel("Results Queue")
        self.panel_title.setObjectName("queuePanelTitle")
        header_row.addWidget(self.panel_title)
        header_row.addStretch()
        self.queue_count = QLabel("0")
        self.queue_count.setObjectName("queueCountBadge")
        header_row.addWidget(self.queue_count)
        self.btn_close = QToolButton()
        self.btn_close.setObjectName("queuePanelClose")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.setToolTip("Hide queue")
        self.btn_close.setAutoRaise(True)
        close_icon_file = _icon_path("close.svg")
        if os.path.isfile(close_icon_file):
            self.btn_close.setIcon(QIcon(close_icon_file))
            self.btn_close.setIconSize(QSize(14, 14))
            self.btn_close.setText("")
        else:
            self.btn_close.setText("X")
        self.btn_close.clicked.connect(self.closed.emit)
        header_row.addWidget(self.btn_close)
        root.addLayout(header_row)

        self.camera_title = QLabel("No camera selected")
        self.camera_title.setObjectName("queuePanelCamera")
        self.camera_title.setWordWrap(True)
        _allow_horizontal_shrink(self.camera_title)
        root.addWidget(self.camera_title)

        self.camera_meta = QLabel("Use the queue button on a stream to open its detections queue.")
        self.camera_meta.setObjectName("queuePanelMeta")
        self.camera_meta.setWordWrap(True)
        _allow_horizontal_shrink(self.camera_meta)
        root.addWidget(self.camera_meta)

        self.queue_scroll = QScrollArea()
        self.queue_scroll.setWidgetResizable(True)
        self.queue_scroll.setFrameShape(QFrame.NoFrame)
        self.queue_scroll.setStyleSheet("background:transparent;border:none;")
        self.queue_content = QWidget()
        self.queue_layout = QVBoxLayout(self.queue_content)
        self.queue_layout.setContentsMargins(0, 0, 0, 0)
        self.queue_layout.setSpacing(8)
        self.queue_layout.setAlignment(Qt.AlignTop)
        self.queue_scroll.setWidget(self.queue_content)
        root.addWidget(self.queue_scroll, 1)

        self._queue_timer = QTimer(self)
        self._queue_timer.setInterval(400)
        self._queue_timer.timeout.connect(self._refresh_queue)
        self._queue_timer.start()
        self.set_camera(None)

    def set_camera(self, camera: Optional["DevicesCamera"]) -> None:
        next_camera_id = _as_int(getattr(camera, "id", 0), 0) if camera is not None else 0
        next_process_type = str(getattr(camera, "process_type", "") or "lpr").lower() if camera is not None else "lpr"
        camera_changed = self._camera_id != next_camera_id or self._process_type != next_process_type
        self._camera = camera
        self._camera_id = next_camera_id
        self._process_type = next_process_type
        if camera is None:
            self._queue_signature = (-1, "")
            self.panel_title.setText("Results Queue")
            self.camera_title.setText("No camera selected")
            self.camera_meta.setText("Use the queue button on a stream to open its detections queue.")
            self.queue_count.setText("0")
            self._render_queue([])
            return

        queue_type = "LPR Queue" if self._process_type == "lpr" else "Face Queue"
        self.panel_title.setText(queue_type)
        self.camera_title.setText(str(getattr(camera, "name", "Unknown Camera") or "Unknown Camera"))
        self.camera_meta.setText(
            f"{_camera_ip(camera)} | "
            f"FPS {_as_int(getattr(camera, 'streaming_fps', 0))}/{_as_int(getattr(camera, 'processing_fps', 0))}"
        )
        if camera_changed:
            self._queue_signature = (-1, "")
        self._refresh_queue()

    def _queue_records(self) -> List[dict]:
        if self._camera_id <= 0:
            return []
        if self._process_type == "face":
            return list(self._face_result_queues.get(self._camera_id, []))
        return list(self._lpr_result_queues.get(self._camera_id, []))

    def _render_queue(self, records: List[dict]) -> None:
        while self.queue_layout.count():
            item = self.queue_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not records:
            empty = QLabel("No detections yet.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                "background:#161b22;border:1px solid #252c35;border-radius:10px;"
                "color:#9ca3af;padding:18px;font-size:12px;"
            )
            self.queue_layout.addWidget(empty)
            self.queue_layout.addStretch()
            return

        for rcd in reversed(records[-120:]):
            filename = str(rcd.get("filename") or rcd.get("file") or "")
            image_url = _result_image_url(rcd, filename)
            card = ResultCard(
                process_type=self._process_type,
                record=rcd,
                camera_id=self._camera_id,
                image_url=image_url,
                net=self._net,
            )
            card.opened.connect(self._open_record_dialog)
            self.queue_layout.addWidget(card)
        self.queue_layout.addStretch()

    def _refresh_queue(self) -> None:
        records = self._queue_records()
        self.queue_count.setText(str(len(records)))
        last_key = ""
        if records:
            item = records[-1]
            last_key = (
                str(item.get("created") or "")
                + "|"
                + str(item.get("filename") or item.get("file") or "")
            )
        signature = (len(records), last_key)
        if signature == self._queue_signature:
            return
        self._queue_signature = signature
        self._render_queue(records)

    def closeEvent(self, event):
        self._queue_timer.stop()
        super().closeEvent(event)

    def _open_record_dialog(self, record: dict) -> None:
        if not isinstance(record, dict):
            return
        camera_name = self.camera_title.text().strip() or f"Camera #{self._camera_id}"
        dialog = RecordDetailsDialog(
            process_type=self._process_type,
            record=record,
            camera_name=camera_name,
            net=self._net,
            parent=self,
        )
        dialog.exec()


class ScreensManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Camera Screens")
        self.resize(900, 600)
        layout = QVBoxLayout(self)
        label = QLabel("This is a placeholder for the screen management window.")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)


class AccordionHeader(QFrame):
    clicked = Signal()

    def __init__(
        self,
        title: str,
        subtitle: str,
        count_text: str,
        state_text: str,
        state_tone: str,
        icon_name: str = "client.svg",
        eyebrow_text: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("cameraSectionHeader")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        icon_card = QFrame(self)
        icon_card.setObjectName("accordionIconCard")
        icon_card.setFixedSize(44, 44)
        icon_layout = QVBoxLayout(icon_card)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setSpacing(0)
        self.icon_label = QLabel(icon_card)
        self.icon_label.setObjectName("accordionIcon")
        _apply_sidebar_icon(self.icon_label, icon_name, 18, fallback="CL")
        icon_layout.addWidget(self.icon_label, 1, Qt.AlignCenter)
        layout.addWidget(icon_card, 0, Qt.AlignTop)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(3)

        self.eyebrow_label = QLabel(eyebrow_text)
        self.eyebrow_label.setObjectName("cameraSectionEyebrow")
        self.eyebrow_label.setVisible(bool(eyebrow_text))
        _allow_horizontal_shrink(self.eyebrow_label)
        text_col.addWidget(self.eyebrow_label)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("cameraSectionTitle")
        self.title_label.setVisible(bool(title))
        _allow_horizontal_shrink(self.title_label)
        text_col.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("cameraSectionMeta")
        self.subtitle_label.setWordWrap(True)
        _allow_horizontal_shrink(self.subtitle_label)
        self.subtitle_label.setVisible(bool(subtitle))
        text_col.addWidget(self.subtitle_label)
        layout.addLayout(text_col, 1)

        right_col = QHBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(6)

        self.count_badge = QLabel(count_text)
        self.count_badge.setObjectName("cameraCountBadge")
        self.count_badge.setVisible(bool(count_text))
        right_col.addWidget(self.count_badge, 0, Qt.AlignVCenter)

        self.state_badge = QLabel(state_text)
        self.state_badge.setObjectName("sectionStateBadge")
        self.state_badge.setProperty("tone", state_tone)
        self.state_badge.setVisible(bool(state_text))
        right_col.addWidget(self.state_badge, 0, Qt.AlignVCenter)

        self.chevron = QLabel("▾")
        self.chevron.setObjectName("accordionChevron")
        self.chevron.setVisible(True)
        right_col.addWidget(self.chevron, 0, Qt.AlignVCenter)
        layout.addLayout(right_col)

        for widget in (
            self.icon_label,
            self.eyebrow_label,
            self.title_label,
            self.subtitle_label,
            self.count_badge,
            self.state_badge,
            self.chevron,
        ):
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_expanded(self, expanded: bool) -> None:
        self.chevron.setText("▾" if expanded else "▸")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class CameraAccordionRow(QFrame):
    activated = Signal(int)

    def __init__(self, camera: "DevicesCamera", parent=None):
        super().__init__(parent)
        self.camera = camera
        self.camera_id = _as_int(getattr(camera, "id", 0), 0)
        self._drag_start_pos: Optional[QPoint] = None
        self._camera_name = str(getattr(camera, "name", "Unknown Camera") or "Unknown Camera")
        self._camera_ip = _camera_ip(camera)
        self.setObjectName("cameraAccordionRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setProperty("online", bool(getattr(camera, "online", False)))
        self.setCursor(Qt.OpenHandCursor)

        root = QHBoxLayout(self)
        root.setContentsMargins(9, 7, 9, 7)
        root.setSpacing(8)

        icon_card = QFrame(self)
        icon_card.setObjectName("cameraRowIconCard")
        icon_card.setFixedSize(40, 40)
        icon_layout = QVBoxLayout(icon_card)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setSpacing(0)

        self.icon_label = QLabel(icon_card)
        self.icon_label.setObjectName("cameraRowIcon")
        _apply_sidebar_icon(self.icon_label, "camera.svg", 20, fallback="CAM")
        icon_layout.addWidget(self.icon_label, 1, Qt.AlignCenter)
        root.addWidget(icon_card, 0, Qt.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)

        self.title_label = QLabel(self._camera_name)
        self.title_label.setObjectName("cameraRowTitle")
        self.title_label.setMinimumWidth(0)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text_col.addWidget(self.title_label)

        self.meta_label = QLabel(self._camera_ip or "No camera IP")
        self.meta_label.setObjectName("cameraRowMeta")
        self.meta_label.setToolTip(self.meta_label.text())
        self.meta_label.setMinimumWidth(0)
        self.meta_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text_col.addWidget(self.meta_label)

        root.addLayout(text_col, 1)

        streaming = _as_int(getattr(camera, "streaming_fps", 0), 0)
        processing = _as_int(getattr(camera, "processing_fps", 0), 0)
        self.fps_card = QFrame(self)
        self.fps_card.setObjectName("cameraRowFpsCard")
        fps_layout = QVBoxLayout(self.fps_card)
        fps_layout.setContentsMargins(8, 5, 8, 5)
        fps_layout.setSpacing(0)
        self.fps_badge = QLabel(f"{streaming}/{processing} FPS")
        self.fps_badge.setObjectName("cameraRowFpsText")
        fps_layout.addWidget(self.fps_badge, 0, Qt.AlignCenter)
        root.addWidget(self.fps_card, 0, Qt.AlignVCenter)

        self.setToolTip(self._build_hover_tooltip())

        for widget in (
            icon_card,
            self.icon_label,
            self.title_label,
            self.meta_label,
            self.fps_card,
            self.fps_badge,
        ):
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def _build_hover_tooltip(self) -> str:
        details = [self._camera_name]
        if self.camera_id > 0:
            details.append(f"Camera ID: #{self.camera_id}")
        details.append(f"IP: {self._camera_ip or 'No camera IP'}")
        return "\n".join(details)

    def _start_drag(self) -> None:
        if self.camera_id <= 0:
            return
        mime = QMimeData()
        mime.setText(str(self.camera_id))

        drag = QDrag(self)
        drag.setMimeData(mime)
        pix = QPixmap(220, 42)
        pix.fill(QColor("#1d4ed8"))
        painter = QPainter(pix)
        painter.setPen(Qt.white)
        painter.drawText(pix.rect().adjusted(10, 0, -10, 0), Qt.AlignVCenter | Qt.AlignLeft, self._camera_name)
        painter.end()
        drag.setPixmap(pix)
        drag.exec(Qt.CopyAction)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            event.buttons() & Qt.LeftButton
            and self._drag_start_pos is not None
            and (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self._start_drag()
            self._drag_start_pos = None
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)

        background = QColor("#171b20") if self.underMouse() else QColor("#121518")
        border = QColor("#58616c") if self.underMouse() else QColor("#434b55")

        painter.fillPath(path, background)
        painter.setPen(QPen(border, 2))
        painter.drawPath(path)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self.camera_id > 0:
            self.activated.emit(self.camera_id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class CameraAccordionSection(QFrame):
    toggled = Signal(bool)

    def __init__(
        self,
        key: str,
        title: str,
        subtitle: str,
        count_text: str,
        state_text: str,
        state_tone: str,
        icon_name: str = "client.svg",
        eyebrow_text: str = "",
        expanded: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.key = key
        self.setObjectName("cameraSection")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.header = AccordionHeader(
            title=title,
            subtitle=subtitle,
            count_text=count_text,
            state_text=state_text,
            state_tone=state_tone,
            icon_name=icon_name,
            eyebrow_text=eyebrow_text,
            parent=self,
        )
        root.addWidget(self.header)
        self.header.clicked.connect(self.toggle)

        self.body = QFrame()
        self.body.setObjectName("cameraSectionBody")
        self.body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(10, 0, 10, 10)
        self.body_layout.setSpacing(8)
        root.addWidget(self.body)
        self._expanded = bool(expanded)
        self.body.setVisible(self._expanded)
        self.header.set_expanded(self._expanded)

    def add_camera_row(self, row: CameraAccordionRow) -> None:
        self.body_layout.addWidget(row)

    def set_expanded(self, expanded: bool, emit_signal: bool = False) -> None:
        self._expanded = bool(expanded)
        self.body.setVisible(self._expanded)
        self.header.set_expanded(self._expanded)
        if emit_signal:
            self.toggled.emit(self._expanded)

    def toggle(self) -> None:
        self.set_expanded(not self._expanded, emit_signal=True)


class DragCameraTree(QScrollArea):
    cameraActivated = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded_sections: Dict[str, bool] = {}
        self.setObjectName("cameraAccordion")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet("background: transparent; border: none;")
        self.content = QWidget()
        self.content.setObjectName("cameraAccordionContent")
        self.content.setMinimumWidth(0)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)
        self.content_layout.setAlignment(Qt.AlignTop)
        self.setWidget(self.content)

    def clear(self) -> None:
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _remember_section_state(self, key: str, expanded: bool) -> None:
        if key:
            self._expanded_sections[key] = bool(expanded)

    def set_sections(self, sections: List[dict], empty_message: str = "No cameras found") -> None:
        self.clear()
        if not sections:
            empty = QFrame()
            empty.setObjectName("cameraAccordionEmpty")
            layout = QVBoxLayout(empty)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(6)
            title = QLabel("No cameras found")
            title.setObjectName("cameraEmptyTitle")
            title.setAlignment(Qt.AlignCenter)
            layout.addWidget(title)
            if empty_message:
                detail = QLabel(empty_message)
                detail.setObjectName("cameraEmptyMeta")
                detail.setWordWrap(True)
                detail.setAlignment(Qt.AlignCenter)
                layout.addWidget(detail)
            self.content_layout.addWidget(empty)
            self.content_layout.addStretch()
            return

        for section_data in sections:
            key = str(section_data.get("key") or "")
            expanded = bool(section_data.get("expanded", False))
            if not bool(section_data.get("force_expanded")) and key in self._expanded_sections:
                expanded = self._expanded_sections[key]
            section = CameraAccordionSection(
                key=key,
                title=str(section_data.get("title") or ""),
                subtitle=str(section_data.get("subtitle") or ""),
                count_text=str(section_data.get("count_text") or ""),
                state_text=str(section_data.get("state_text") or ""),
                state_tone=str(section_data.get("state_tone") or "neutral"),
                icon_name=str(section_data.get("icon_name") or "client.svg"),
                eyebrow_text=str(section_data.get("eyebrow_text") or ""),
                expanded=expanded,
            )
            section.toggled.connect(lambda is_expanded, section_key=key: self._remember_section_state(section_key, is_expanded))

            for camera in section_data.get("cameras", []):
                row = CameraAccordionRow(camera)
                row.activated.connect(self.cameraActivated.emit)
                section.add_camera_row(row)

            self.content_layout.addWidget(section)

        self.content_layout.addStretch()


class GridCell(QFrame):
    removeRequested = Signal(int)
    detailsRequested = Signal(int)
    doorRequested = Signal(int)
    focusRequested = Signal(int)
    dropCamera = Signal(int, int)
    swapRequested = Signal(int, int)
    loginRequested = Signal()

    def __init__(self, index: int, login_on_right_click: bool = False, parent=None):
        super().__init__(parent)
        self.index = index
        self._login_on_right_click = bool(login_on_right_click)
        self.camera: Optional["DevicesCamera"] = None
        self._drag_start_pos: Optional[QPoint] = None
        self._syncing_overlay_geometry = False
        self._mpv_proc: Optional[subprocess.Popen] = None
        self._mpv_url: str = ""
        self._mpv_ipc: str = ""
        self._tv_mode = False
        self._use_main_stream = False
        self._hovered = False
        self._overlay_owner = None
        self.interaction_overlay = None
        self.top_controls = None
        self.bottom_info = None
        self.btn_focus = None
        self.btn_details = None
        self.btn_remove = None
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(33)
        self._hover_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._hover_timer.timeout.connect(self._sync_hover_state)
        self._stream_restart_timer = QTimer(self)
        self._stream_restart_timer.setSingleShot(True)
        self._stream_restart_timer.timeout.connect(self._start_stream)
        self._fit_retry_timer = QTimer(self)
        self._fit_retry_timer.setSingleShot(True)
        self._fit_retry_timer.timeout.connect(self._fit_stream)
        self._fit_retry_attempts = 0
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setObjectName("gridCell")
        self.setProperty("empty", True)
        self.setMinimumSize(180, 120)
        self.setFrameShape(QFrame.StyledPanel)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(0, 0, 0, 0)
        self.root.setSpacing(0)

        self.video_label = QLabel("No Video")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setObjectName("videoPlaceholder")
        self.video_label.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.video_label.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.video_label.setMouseTracking(True)
        self.root.addWidget(self.video_label, 1)

        self.placeholder_overlay = QWidget(self.video_label)
        self.placeholder_overlay.setObjectName("videoTilePlaceholder")
        self.placeholder_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.placeholder_layout = QVBoxLayout(self.placeholder_overlay)
        self.placeholder_layout.setContentsMargins(16, 16, 16, 16)
        self.placeholder_layout.setSpacing(8)
        self.placeholder_layout.setAlignment(Qt.AlignCenter)

        self.placeholder_icon = QLabel()
        self.placeholder_icon.setObjectName("videoTilePlaceholderIcon")
        self.placeholder_icon.setAlignment(Qt.AlignCenter)
        self.placeholder_layout.addWidget(self.placeholder_icon, 0, Qt.AlignCenter)

        self.placeholder_title = QLabel("No Camera")
        self.placeholder_title.setObjectName("videoTilePlaceholderTitle")
        self.placeholder_title.setAlignment(Qt.AlignCenter)
        self.placeholder_layout.addWidget(self.placeholder_title, 0, Qt.AlignCenter)

        self.placeholder_detail = QLabel("")
        self.placeholder_detail.setObjectName("videoTilePlaceholderDetail")
        self.placeholder_detail.setAlignment(Qt.AlignCenter)
        self.placeholder_detail.setWordWrap(True)
        self.placeholder_layout.addWidget(self.placeholder_detail, 0, Qt.AlignCenter)

        self.interaction_overlay = QFrame(None)
        self.interaction_overlay.setObjectName("streamInteractionOverlay")
        self.interaction_overlay.setWindowFlags(self._overlay_window_flags())
        self.interaction_overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.interaction_overlay.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.interaction_overlay.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.interaction_overlay.setAcceptDrops(True)
        self.interaction_overlay.setAutoFillBackground(False)
        self.interaction_overlay.setMouseTracking(True)
        self.interaction_overlay.setStyleSheet("background-color: rgba(0, 0, 0, 0); border: none;")
        self.destroyed.connect(lambda *_args, overlay=self.interaction_overlay: _safe_delete_later(overlay))
        self.overlay_layout = QVBoxLayout(self.interaction_overlay)
        self.overlay_layout.setContentsMargins(8, 8, 8, 8)
        self.overlay_layout.setSpacing(0)

        # Overlay controls pinned top-right above stream.
        self.top_controls = QWidget(self.interaction_overlay)
        self.top_controls.setObjectName("streamTopOverlay")
        self.top_controls.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.top_controls.setAutoFillBackground(False)
        self.top_controls.setMouseTracking(True)
        self.top_controls.setStyleSheet("background-color: rgba(0, 0, 0, 0); border: none;")
        self.top_controls_layout = QHBoxLayout(self.top_controls)
        self.top_controls_layout.setContentsMargins(0, 0, 0, 0)
        self.top_controls_layout.setSpacing(6)
        self.overlay_layout.addWidget(self.top_controls, 0, Qt.AlignTop | Qt.AlignRight)

        self.btn_focus = QToolButton()
        self.btn_focus.setToolTip("Maximize / Restore")
        self.btn_focus.clicked.connect(lambda: self.focusRequested.emit(self.index))
        self._setup_overlay_btn(self.btn_focus, "Maximize / Restore", "live_view.svg", "M")

        self.btn_details = QToolButton()
        self.btn_details.clicked.connect(lambda: self.detailsRequested.emit(self.index))
        self._setup_overlay_btn(self.btn_details, "Show Results Queue", "view.svg", "V")

        self.btn_remove = QToolButton()
        self.btn_remove.clicked.connect(lambda: self.removeRequested.emit(self.index))
        self._setup_overlay_btn(self.btn_remove, "Close Stream", "close.svg", "X")

        for btn in (self.btn_focus, self.btn_details, self.btn_remove):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setAutoRaise(True)
            btn.setMouseTracking(True)
            self.top_controls_layout.addWidget(btn)

        self.overlay_layout.addStretch(1)

        self.camera_name_label = QLabel("")
        self.camera_name_label.setObjectName("streamCameraName")
        self.camera_name_label.setMinimumWidth(0)
        self.camera_name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.camera_ip_label = QLabel("")
        self.camera_ip_label.setObjectName("streamCameraIp")
        self.camera_ip_label.setMinimumWidth(0)
        self.camera_ip_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.fps_label = QLabel("FPS 0 / 0")
        self.fps_label.setObjectName("fpsBadge")
        self.face_label = QLabel("")
        self.face_label.setObjectName("faceBadge")
        self._streaming_fps = 0
        self._processing_fps = 0
        self._face_badge_text = ""

        self.bottom_info = QWidget(self.interaction_overlay)
        self.bottom_info.setObjectName("streamBottomOverlay")
        self.bottom_info.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.bottom_info.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.bottom_info.setAutoFillBackground(False)
        self.bottom_info.setStyleSheet("background-color: rgba(0, 0, 0, 0); border: none;")
        self.bottom_info_layout = QHBoxLayout(self.bottom_info)
        self.bottom_info_layout.setContentsMargins(12, 0, 12, 12)
        self.bottom_info_layout.setSpacing(6)

        self.bottom_meta = QWidget(self.bottom_info)
        self.bottom_meta.setObjectName("streamBottomMeta")
        self.bottom_meta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.bottom_meta_layout = QVBoxLayout(self.bottom_meta)
        self.bottom_meta_layout.setContentsMargins(0, 0, 0, 0)
        self.bottom_meta_layout.setSpacing(1)
        self.bottom_meta_layout.addWidget(self.camera_name_label, 0, Qt.AlignLeft)
        self.bottom_meta_layout.addWidget(self.camera_ip_label, 0, Qt.AlignLeft)

        self.bottom_info_layout.addWidget(self.bottom_meta, 1, Qt.AlignLeft | Qt.AlignBottom)
        self.bottom_info_layout.addStretch()
        self.bottom_info_layout.addWidget(self.fps_label, 0, Qt.AlignRight | Qt.AlignBottom)
        self.bottom_info_layout.addWidget(self.face_label, 0, Qt.AlignRight | Qt.AlignBottom)
        self.overlay_layout.addWidget(self.bottom_info, 0)

        for widget in (
            self.video_label,
            self.interaction_overlay,
            self.top_controls,
            self.bottom_info,
            self.btn_focus,
            self.btn_details,
            self.btn_remove,
        ):
            widget.installEventFilter(self)

        self._sync_overlay_geometry()
        self.interaction_overlay.raise_()
        self.refresh()

    def _update_bottom_badges(self) -> None:
        tile_width = max(self.width(), self.video_label.width())
        compact = tile_width <= 240
        self.fps_label.setProperty("compact", compact)
        self.face_label.setProperty("compact", compact)
        self.camera_name_label.setProperty("compact", compact)
        self.camera_ip_label.setProperty("compact", compact)
        self.bottom_info_layout.setContentsMargins(14 if compact else 12, 0, 14 if compact else 12, 14 if compact else 12)
        self.bottom_info_layout.setSpacing(4 if compact else 6)
        fps_prefix = "FPS " if not compact else ""
        self.fps_label.setText(f"{fps_prefix}{self._streaming_fps}/{self._processing_fps}")
        self.face_label.setText(self._face_badge_text)
        self.camera_name_label.setText(self._camera_display_name())
        self.camera_ip_label.setText(self._camera_display_ip())
        self.bottom_meta.setVisible(bool(self.camera))
        for widget in (self.camera_name_label, self.camera_ip_label, self.fps_label, self.face_label):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _handle_startup_login_request(self, event) -> bool:
        if not self._login_on_right_click:
            return False
        button = getattr(event, "button", lambda: None)()
        if button != Qt.MouseButton.RightButton:
            return False
        self.loginRequested.emit()
        event.accept()
        return True

    def _sync_placeholder_geometry(self) -> None:
        if self.placeholder_overlay is None or self.video_label is None:
            return
        self.placeholder_overlay.setGeometry(0, 0, self.video_label.width(), self.video_label.height())

    def _camera_display_name(self, camera: Optional["DevicesCamera"] = None) -> str:
        current_camera = camera or self.camera
        if current_camera is None:
            return ""
        return str(getattr(current_camera, "name", "Unknown Camera") or "Unknown Camera")

    def _camera_display_ip(self, camera: Optional["DevicesCamera"] = None) -> str:
        current_camera = camera or self.camera
        if current_camera is None:
            return ""
        return _camera_ip(current_camera) or "No camera IP"

    def _camera_placeholder_detail(self, camera: Optional["DevicesCamera"] = None) -> str:
        current_camera = camera or self.camera
        if current_camera is None:
            return ""
        return f"{self._camera_display_name(current_camera)}\n{self._camera_display_ip(current_camera)}"

    def _set_placeholder_state(self, title: str, icon_name: str = "camera.svg", detail: str = "") -> None:
        icon_file = _icon_path(icon_name)
        if os.path.isfile(icon_file):
            self.placeholder_icon.setPixmap(QIcon(icon_file).pixmap(QSize(40, 40)))
            self.placeholder_icon.setText("")
        else:
            self.placeholder_icon.setPixmap(QPixmap())
            self.placeholder_icon.setText("[]")
        self.placeholder_title.setText(title)
        self.placeholder_detail.setText(detail)
        self.placeholder_detail.setVisible(bool(detail))
        self.video_label.setText("")
        self._sync_placeholder_geometry()
        self.placeholder_overlay.show()
        self.placeholder_overlay.raise_()

    def _clear_placeholder_state(self) -> None:
        self.video_label.setText("")
        self.placeholder_overlay.hide()

    def _overlay_window_flags(self) -> Qt.WindowFlags:
        return (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )

    def _ensure_overlay_owner(self) -> None:
        if self.interaction_overlay is None:
            return
        owner = self.window()
        if owner is None or owner is self.interaction_overlay:
            return
        if owner is self and self.parentWidget() is None and not self.isVisible():
            return
        current_flags = self.interaction_overlay.windowFlags()
        if (
            self._overlay_owner is owner
            and self.interaction_overlay.parentWidget() is owner
            and not bool(current_flags & Qt.WindowType.WindowStaysOnTopHint)
        ):
            return
        was_visible = self.interaction_overlay.isVisible()
        self.interaction_overlay.hide()
        self.interaction_overlay.setParent(owner, self._overlay_window_flags())
        self._overlay_owner = owner
        if was_visible:
            self.interaction_overlay.show()

    def set_tv_mode(self, enabled: bool) -> None:
        self._tv_mode = enabled
        self.refresh()

    def _setup_overlay_btn(self, btn: QToolButton, tooltip: str, svg_name: str, fallback_text: str) -> None:
        btn.setToolTip(tooltip)
        btn.setFixedSize(36, 36)
        btn.setStyleSheet(
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
        icon_file = _icon_path(svg_name)
        if os.path.isfile(icon_file):
            btn.setIcon(QIcon(icon_file))
            btn.setIconSize(QSize(18, 18))
            btn.setText("")
        else:
            btn.setText(fallback_text)

    def set_camera(self, camera: Optional["DevicesCamera"]) -> None:
        previous_id = self.camera.id if self.camera else None
        next_id = camera.id if camera else None
        if previous_id != next_id:
            self._stop_stream()
            self._use_main_stream = False
        self.camera = camera
        self.refresh()
        if previous_id != next_id and camera is not None:
            self.replay_stream()

    def set_main_stream(self, enabled: bool) -> None:
        next_value = bool(enabled)
        if self._use_main_stream == next_value:
            return
        self._use_main_stream = next_value
        if self.camera is None:
            return
        self.replay_stream()

    def _effective_rtsp_url(self) -> str:
        if self.camera is None:
            return ""
        rtsp_sub, rtsp_main = _camera_rtsp_urls(self.camera)
        if self._use_main_stream:
            return (rtsp_main or rtsp_sub).strip()
        return (rtsp_sub or rtsp_main).strip()

    def refresh(self):
        has_camera = self.camera is not None
        self.setProperty("empty", not has_camera)
        self.style().unpolish(self)
        self.style().polish(self)
        self._update_hover_tracking(has_camera)
        self._update_overlay_visibility(has_camera)

        if not has_camera:
            self._stop_stream()
            self.video_label.setProperty("active", False)
            self._set_placeholder_state("No Camera", "camera.svg", detail=f"Slot {self.index + 1} is empty")
            self._sync_camera_runtime_badges()
            self.setToolTip(f"Empty slot {self.index + 1}")
        else:
            cam = self.camera
            self.video_label.setProperty("active", False)
            self._sync_camera_runtime_badges()
            self.setToolTip(self._camera_placeholder_detail(cam))
            if not self._effective_rtsp_url():
                self._set_placeholder_state("No Video", "live_view.svg", detail=self._camera_placeholder_detail(cam))
            elif self._mpv_proc is None or self._mpv_proc.poll() is not None:
                self._set_placeholder_state("Loading Video", "live_view.svg", detail=self._camera_placeholder_detail(cam))
                if not self._stream_restart_timer.isActive():
                    self._schedule_stream_restart(80)
            else:
                self.video_label.setProperty("active", True)
                self._clear_placeholder_state()

        self._update_bottom_badges()
        self.style().unpolish(self.video_label)
        self.style().polish(self.video_label)
        if (
            self.isVisible()
            and self.interaction_overlay is not None
            and self.interaction_overlay.isVisible()
        ):
            self._sync_overlay_geometry()
            self.interaction_overlay.raise_()

    def _sync_camera_runtime_badges(self) -> None:
        if self.camera is None:
            self._streaming_fps = 0
            self._processing_fps = 0
            self._face_badge_text = ""
            return
        cam = self.camera
        self._streaming_fps = _as_int(getattr(cam, "streaming_fps", 0))
        self._processing_fps = _as_int(getattr(cam, "processing_fps", 0))
        if str(getattr(cam, "process_type", "") or "") == "face" and bool(getattr(cam, "face_show_rect", False)):
            self._face_badge_text = (
                f"In {_as_int(getattr(cam, 'total_in', 0))}   Out {_as_int(getattr(cam, 'total_out', 0))}"
            )
        else:
            self._face_badge_text = ""

    def sync_runtime_status(self) -> None:
        self._sync_camera_runtime_badges()
        self._update_bottom_badges()

    def _update_overlay_visibility(self, has_camera: Optional[bool] = None) -> None:
        if has_camera is None:
            has_camera = self.camera is not None
        controls = (
            self.interaction_overlay,
            self.top_controls,
            self.bottom_info,
            self.btn_focus,
            self.btn_details,
            self.btn_remove,
        )
        if any(widget is None for widget in controls):
            return
        host_visible = bool(self.isVisible() and self.video_label.isVisible())
        show_top_controls = bool(has_camera and not self._tv_mode and host_visible and self._hovered)
        self.btn_focus.setVisible(show_top_controls)
        self.btn_details.setVisible(show_top_controls)
        self.btn_remove.setVisible(show_top_controls)
        show_overlay_layer = bool(has_camera and not self._tv_mode and host_visible)
        if show_overlay_layer:
            self._sync_overlay_geometry()
            if not self.interaction_overlay.isVisible():
                self.interaction_overlay.show()
            self.interaction_overlay.raise_()
        else:
            if self.interaction_overlay.isVisible():
                self.interaction_overlay.hide()
        self.top_controls.setVisible(show_top_controls)
        self.bottom_info.setVisible(bool(has_camera and not self._tv_mode and host_visible))

    def _update_hover_tracking(self, has_camera: Optional[bool] = None) -> None:
        if has_camera is None:
            has_camera = self.camera is not None
        should_track = bool(has_camera and not self._tv_mode and self.isVisible())
        if should_track:
            if not self._hover_timer.isActive():
                self._hover_timer.start()
            self._sync_hover_state()
            return
        if self._hover_timer.isActive():
            self._hover_timer.stop()
        if self._hovered:
            self._hovered = False
            self._update_overlay_visibility(has_camera)

    def deactivate_overlay(self) -> None:
        self._update_hover_tracking(False)
        self._hovered = False
        self._set_drop_target(False)
        if self.interaction_overlay is not None:
            self.interaction_overlay.hide()

    def _cursor_over_widget(self, widget: Optional[QWidget]) -> bool:
        if widget is None or not widget.isVisible():
            return False
        try:
            return bool(widget.underMouse())
        except RuntimeError:
            return False

    def _cursor_over_interaction_area(self) -> bool:
        return any(
            self._cursor_over_widget(widget)
            for widget in (
                self,
                getattr(self, "video_label", None),
                getattr(self, "interaction_overlay", None),
                getattr(self, "top_controls", None),
                getattr(self, "bottom_info", None),
                getattr(self, "btn_focus", None),
                getattr(self, "btn_details", None),
                getattr(self, "btn_remove", None),
            )
        )

    def _sync_hover_state(self) -> None:
        if not self.isVisible():
            hovered = False
        else:
            hovered = self._cursor_over_interaction_area()
        if self._hovered == hovered:
            return
        self._hovered = hovered
        self._update_overlay_visibility()

    def _start_stream(self) -> None:
        if not self.isVisible() or self.camera is None:
            return
        url = self._effective_rtsp_url()
        if not url:
            return
        if self._mpv_proc and self._mpv_proc.poll() is None and self._mpv_url == url:
            return

        self._stop_stream()
        self._mpv_url = url
        wid = int(self.video_label.winId())
        if wid <= 0:
            self._schedule_stream_restart(80)
            return

        ipc = os.path.join(tempfile.gettempdir(), f"mpv-live-{wid}.sock")
        self._mpv_ipc = ipc
        try:
            if os.path.exists(ipc):
                os.unlink(ipc)
        except OSError:
            pass
        try:
            self._mpv_proc = subprocess.Popen(
                [
                    "mpv",
                    *MPV_ARGS,
                    f"--wid={wid}",
                    f"--input-ipc-server={ipc}",
                    url,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.video_label.setText("")
            self.video_label.setProperty("active", True)
            self._clear_placeholder_state()
            self._schedule_stream_fit()
        except FileNotFoundError:
            self._mpv_proc = None
            self.video_label.setProperty("active", False)
            self._set_placeholder_state("No Video", "live_view.svg", detail=self._camera_placeholder_detail())
        except Exception:
            self._mpv_proc = None
            self.video_label.setProperty("active", False)
            self._set_placeholder_state("No Video", "live_view.svg", detail=self._camera_placeholder_detail())
        self.style().unpolish(self.video_label)
        self.style().polish(self.video_label)

    def _stop_stream(self) -> None:
        self._stream_restart_timer.stop()
        self._fit_retry_timer.stop()
        self._fit_retry_attempts = 0
        if self._mpv_proc:
            try:
                self._mpv_proc.terminate()
            except Exception:
                pass
            try:
                self._mpv_proc.wait(timeout=0.35)
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
        self._mpv_url = ""

    def _fit_stream(self) -> None:
        if self._mpv_proc is None or self._mpv_proc.poll() is not None:
            self._fit_retry_attempts = 0
            return
        applied = False
        for command in (
            ["set_property", "keepaspect", True],
            ["set_property", "video-unscaled", False],
            ["set_property", "video-zoom", 0.0],
            ["set_property", "video-pan-x", 0.0],
            ["set_property", "video-pan-y", 0.0],
            ["set_property", "panscan", MPV_EMBED_PANSCAN],
        ):
            applied = self._send_mpv_command(command) or applied
        if applied:
            self._fit_retry_attempts = 0
            return
        if self._fit_retry_attempts <= 0:
            return
        self._fit_retry_attempts -= 1
        self._fit_retry_timer.start(120)

    def _schedule_stream_fit(self, delay_ms: int = 120, attempts: int = 5) -> None:
        if self._mpv_proc is None or self._mpv_proc.poll() is not None:
            return
        self._fit_retry_attempts = max(self._fit_retry_attempts, attempts)
        self._fit_retry_timer.start(max(0, delay_ms))

    def _schedule_stream_restart(self, delay_ms: int = 80) -> None:
        if self.camera is None or not self._effective_rtsp_url():
            self._stream_restart_timer.stop()
            return
        self._stream_restart_timer.start(max(0, delay_ms))

    def replay_stream(self, delay_ms: int = 80) -> None:
        if self.camera is None:
            self._stop_stream()
            return
        self.video_label.setProperty("active", False)
        self._set_placeholder_state("Loading Video", "live_view.svg", detail=self._camera_placeholder_detail())
        self._stop_stream()
        self._schedule_stream_restart(delay_ms)

    def _send_mpv_command(self, command: List[object]) -> bool:
        if not self._mpv_ipc:
            return False
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(0.3)
            sock.connect(self._mpv_ipc)
            payload = json.dumps({"command": command}).encode("utf-8") + b"\n"
            sock.sendall(payload)
            sock.close()
            return True
        except Exception:
            return False

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_placeholder_geometry()
        self._update_hover_tracking()
        self._sync_overlay_geometry()
        self._update_overlay_visibility()
        self._schedule_stream_restart(0)

    def hideEvent(self, event):
        self._update_hover_tracking(False)
        self.interaction_overlay.hide()
        self._stop_stream()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._update_hover_tracking(False)
        self.interaction_overlay.close()
        self._stop_stream()
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_placeholder_geometry()
        self._sync_overlay_geometry()
        self._update_bottom_badges()
        if self.isVisible() and self._mpv_proc and self._mpv_proc.poll() is None:
            self._schedule_stream_fit(60, attempts=1)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._sync_overlay_geometry()

    def _sync_overlay_geometry(self) -> None:
        if self._syncing_overlay_geometry:
            return
        if self.interaction_overlay is None or not hasattr(self, "video_label"):
            return
        self._ensure_overlay_owner()
        self._syncing_overlay_geometry = True
        try:
            host = self.video_label
            if not host.isVisible():
                return
            if host.width() <= 0 or host.height() <= 0:
                return
            host_top_left = host.mapToGlobal(QPoint(0, 0))
            self.interaction_overlay.setGeometry(
                host_top_left.x(),
                host_top_left.y(),
                host.width(),
                host.height(),
            )
        finally:
            self._syncing_overlay_geometry = False

    def _start_grid_drag(self) -> None:
        mime = QMimeData()
        mime.setData("application/x-grid-index", str(self.index).encode())
        drag = QDrag(self)
        drag.setMimeData(mime)

        # Do not grab native mpv surface; render a lightweight drag preview.
        preview = QPixmap(220, 140)
        preview.fill(QColor("#0b1220"))
        painter = QPainter(preview)
        painter.setPen(QColor("#3b82f6"))
        painter.drawRect(preview.rect().adjusted(0, 0, -1, -1))
        painter.setPen(QColor("#e5e7eb"))
        label = self.camera.name if self.camera else f"Slot {self.index + 1}"
        painter.drawText(preview.rect(), Qt.AlignCenter, label)
        painter.end()
        drag.setPixmap(preview)
        self._drag_start_pos = None
        drag.exec(Qt.MoveAction)

    def mouseDoubleClickEvent(self, event):
        if self.camera:
            self.focusRequested.emit(self.index)
        super().mouseDoubleClickEvent(event)

    def enterEvent(self, event):
        self._sync_hover_state()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._sync_hover_state()
        super().leaveEvent(event)

    def eventFilter(self, obj, event):
        watched_objects = tuple(
            candidate
            for candidate in (
                getattr(self, "video_label", None),
                getattr(self, "interaction_overlay", None),
                getattr(self, "top_controls", None),
                getattr(self, "bottom_info", None),
                getattr(self, "btn_focus", None),
                getattr(self, "btn_details", None),
                getattr(self, "btn_remove", None),
            )
            if candidate is not None
        )
        if obj in watched_objects:
            if event.type() in (QEvent.Type.Enter, QEvent.Type.Leave, QEvent.Type.MouseMove):
                self._sync_hover_state()
            elif event.type() == QEvent.Type.MouseButtonPress and self._handle_startup_login_request(event):
                return True
        if obj is self.video_label and event.type() == QEvent.Type.MouseButtonDblClick:
            if self.camera and event.button() == Qt.MouseButton.LeftButton:
                self.focusRequested.emit(self.index)
                return True
        if obj is self.interaction_overlay and event.type() == QEvent.Type.MouseButtonDblClick:
            if self.camera and event.button() == Qt.MouseButton.LeftButton:
                self.focusRequested.emit(self.index)
                return True
        if obj is self.interaction_overlay and event.type() == QEvent.Type.MouseButtonPress:
            if self.camera and event.button() == Qt.MouseButton.LeftButton:
                self._drag_start_pos = event.position().toPoint()
                return False
        if obj is self.interaction_overlay and event.type() == QEvent.Type.MouseMove:
            if not self.camera or not (event.buttons() & Qt.MouseButton.LeftButton):
                return False
            if self._drag_start_pos is None:
                return False
            if (event.position().toPoint() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
                return False
            self._start_grid_drag()
            return True
        if obj is self.interaction_overlay and event.type() == QEvent.Type.DragEnter:
            self._handle_drag_enter(event)
            return True
        if obj is self.interaction_overlay and event.type() == QEvent.Type.DragLeave:
            self._handle_drag_leave()
            return True
        if obj is self.interaction_overlay and event.type() == QEvent.Type.Drop:
            self._handle_drop(event)
            return True
        if obj is self.video_label and event.type() == QEvent.Type.MouseButtonPress:
            if self.camera and event.button() == Qt.MouseButton.LeftButton:
                self._drag_start_pos = event.position().toPoint()
                return False
        if obj is self.video_label and event.type() == QEvent.Type.MouseMove:
            if not self.camera or not (event.buttons() & Qt.LeftButton):
                return False
            if self._drag_start_pos is None:
                return False
            if (event.position().toPoint() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
                return False
            self._start_grid_drag()
            return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if self._handle_startup_login_request(event):
            return
        if event.button() == Qt.LeftButton and self.camera:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self.camera or not (event.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(event)
        if self._drag_start_pos is None:
            return super().mouseMoveEvent(event)
        current_pos = event.position().toPoint()
        if (current_pos - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return super().mouseMoveEvent(event)
        self._start_grid_drag()
        super().mouseMoveEvent(event)

    def _set_drop_target(self, active: bool) -> None:
        self.setProperty("dropTarget", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def _handle_drag_enter(self, event) -> None:
        if event.mimeData().hasText() or event.mimeData().hasFormat("application/x-grid-index"):
            event.acceptProposedAction()
            self._set_drop_target(True)
            return
        event.ignore()

    def _handle_drag_leave(self) -> None:
        self._set_drop_target(False)

    def _handle_drop(self, event) -> None:
        self._set_drop_target(False)

        if event.mimeData().hasFormat("application/x-grid-index"):
            source_index = int(bytes(event.mimeData().data("application/x-grid-index")).decode())
            if source_index != self.index:
                self.swapRequested.emit(source_index, self.index)
            event.acceptProposedAction()
            return

        if event.mimeData().hasText():
            try:
                cam_id = int(event.mimeData().text())
                self.dropCamera.emit(self.index, cam_id)
                event.acceptProposedAction()
                return
            except ValueError:
                pass
        event.ignore()

    def dragEnterEvent(self, event):
        self._handle_drag_enter(event)

    def dragLeaveEvent(self, event):
        self._handle_drag_leave()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._handle_drop(event)


# ============================================================
# Main window
# ============================================================

class CameraDashboard(QMainWindow):
    tvModeChanged = Signal(bool)
    loginRequested = Signal()

    def __init__(self, startup_mode: bool = False):
        super().__init__()
        self.startup_mode = bool(startup_mode)
        self.setWindowTitle("PySide6 Camera Monitor")
        self.resize(1520, 900)

        from app.services.home.devices.camera_service import (
            CameraService as DevicesCameraService,
        )
        from app.services.home.devices.client_service import (
            ClientService as DevicesClientService,
        )
        from app.services.home.user.department_service import DepartmentService
        from app.store.home.devices.client_store import (
            ClientStore as DevicesClientStore,
        )
        from app.store.home.user.department_store import (
            DepartmentCrudStore as DevicesDepartmentCrudStore,
            DepartmentStore as DevicesDepartmentStore,
        )

        self.client_store: "DevicesClientStore" = DevicesClientStore(DevicesClientService())
        self.department_store: "DevicesDepartmentStore" = DevicesDepartmentStore(DevicesCameraService())
        self.department_crud_store: "DevicesDepartmentCrudStore" = DevicesDepartmentCrudStore(DepartmentService())
        self.screen_store = ScreenStore(ScreenService())
        self.clients: List["DevicesClient"] = []
        self.cameras: List["DevicesCamera"] = []
        self.departments: List["DepartmentResponse"] = []
        self.lpr_result_queues: Dict[int, List[dict]] = {}
        self.face_result_queues: Dict[int, List[dict]] = {}
        self.saved_configs: List[SavedScreenConfig] = []
        self.client_map = {c.id: c for c in self.clients}
        self.camera_map = {c.id: c for c in self.cameras}
        self.screen_cells: List[GridCell] = []
        self.selected_grid_size = 2
        self.selected_config: Optional[SavedScreenConfig] = None
        self.is_tv_mode = False
        self.focused_camera_id: Optional[int] = None
        self.queue_camera_id: Optional[int] = None
        self._sidebar_ratio = 0.20
        self._sidebar_min_width = 260
        self._sidebar_max_width = 560
        self._content_min_width = 240
        self._camera_sidebar_width = 460
        self._queue_sidebar_width = 460
        self.ws_client = MonitorWsClient(self)
        self.ws_client.lprResult.connect(self._on_lpr_result)
        self.ws_client.faceResult.connect(self._on_face_result)
        self.ws_client.statusUpdate.connect(self._on_status_update)
        self.ws_client.connect_socket()

        self._build_ui()
        self.toast = PrimeToastHost(self)
        self._apply_theme()
        self._load_api_data()
        self.populate_camera_tree()
        self.populate_config_combo()
        self.rebuild_grid()
        self._apply_default_screen_selection()
        self._apply_startup_layout()

    # ------------------------------ UI ------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.main_splitter = QSplitter(Qt.Horizontal)
        root.addWidget(self.main_splitter)

        self.sidebar = self._build_sidebar()
        self.content = self._build_content()

        self.main_splitter.addWidget(self.sidebar)
        self.main_splitter.addWidget(self.content)
        self.main_splitter.setHandleWidth(0)
        self.main_splitter.setChildrenCollapsible(False)
        handle = self.main_splitter.handle(1)
        if handle is not None:
            handle.setEnabled(False)
            handle.hide()
        self._apply_fixed_sidebar_split()
        QTimer.singleShot(0, self._apply_fixed_sidebar_split)

        self._create_actions()

    def _toast_info(self, summary: str, detail: str = "", life: int = 3200) -> None:
        if hasattr(self, "toast"):
            self.toast.info(summary, detail, life)

    def _toast_warn(self, summary: str, detail: str = "", life: int = 3600) -> None:
        if hasattr(self, "toast"):
            self.toast.warn(summary, detail, life)

    def _toast_error(self, summary: str, detail: str = "", life: int = 4200) -> None:
        if hasattr(self, "toast"):
            self.toast.error(summary, detail, life)

    def _toast_success(self, summary: str, detail: str = "", life: int = 3200) -> None:
        if hasattr(self, "toast"):
            self.toast.success(summary, detail, life)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(self._sidebar_min_width)
        sidebar.setMaximumWidth(self._sidebar_max_width)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        self.sidebar_title = QLabel("Cameras")
        self.sidebar_title.setObjectName("sidebarTitle")
        header.addWidget(self.sidebar_title)
        header.addStretch()
        video_icon = QLabel()
        video_icon.setObjectName("headerIcon")
        cam_icon_file = _icon_path("devices.svg")
        if os.path.isfile(cam_icon_file):
            video_icon.setPixmap(QIcon(cam_icon_file).pixmap(QSize(18, 18)))
        else:
            video_icon.setText("📹")
        video_icon.setAlignment(Qt.AlignCenter)
        header.addWidget(video_icon)
        layout.addLayout(header)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search departments or cameras...")
        self.search.textChanged.connect(self.populate_camera_tree)
        layout.addWidget(self.search)

        self.sidebar_stack = QStackedWidget()
        self.sidebar_stack.setObjectName("sidebarStack")

        self.sidebar_camera_page = QWidget()
        self.sidebar_camera_page_layout = QVBoxLayout(self.sidebar_camera_page)
        self.sidebar_camera_page_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_camera_page_layout.setSpacing(0)
        self.camera_render_panel = RoundedClipFrame(18)
        self.camera_render_panel.setObjectName("cameraRenderPanel")
        self.camera_render_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        render_layout = QVBoxLayout(self.camera_render_panel)
        render_layout.setContentsMargins(0, 0, 0, 0)
        render_layout.setSpacing(0)
        self.camera_tree = DragCameraTree()
        self.camera_tree.cameraActivated.connect(self.add_camera_to_last_stream)
        render_layout.addWidget(self.camera_tree, 1)
        self.sidebar_camera_page_layout.addWidget(self.camera_render_panel, 1)
        self.sidebar_stack.addWidget(self.sidebar_camera_page)

        self.sidebar_queue_page = QWidget()
        self.sidebar_queue_page_layout = QVBoxLayout(self.sidebar_queue_page)
        self.sidebar_queue_page_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_queue_page_layout.setSpacing(0)
        self.camera_queue_panel = CameraQueuePanel(
            lpr_result_queues=self.lpr_result_queues,
            face_result_queues=self.face_result_queues,
            parent=self.sidebar_queue_page,
        )
        self.camera_queue_panel.closed.connect(self.close_camera_queue_panel)
        self.sidebar_queue_page_layout.addWidget(self.camera_queue_panel, 1)
        self.sidebar_stack.addWidget(self.sidebar_queue_page)
        self.sidebar_stack.setCurrentWidget(self.sidebar_camera_page)
        layout.addWidget(self.sidebar_stack, 1)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        self.config_combo = PrimeSelect(placeholder="Main Screen")
        self.config_combo.value_changed.connect(self.load_configuration_by_id)
        layout.addWidget(self.config_combo)

        controls = QHBoxLayout()
        self.btn_tv = ModernButton("TV Mode")
        tv_icon_file = _icon_path("tv-mode.svg")
        if os.path.isfile(tv_icon_file):
            self.btn_tv.set_icon_only(QIcon(tv_icon_file), "Enter TV mode")
        self.btn_tv.clicked.connect(self.toggle_tv_mode)
        controls.addWidget(self.btn_tv)

        self.btn_save = ModernButton("Save")
        self.btn_save.clicked.connect(self.save_current_screen)
        controls.addWidget(self.btn_save)

        self.btn_screens = ModernButton("Screens")
        screens_icon_file = _icon_path("list_management.svg")
        if os.path.isfile(screens_icon_file):
            self.btn_screens.set_icon_only(QIcon(screens_icon_file), "Manage screens")
        self.btn_screens.clicked.connect(self.open_screens_manager)
        controls.addWidget(self.btn_screens)
        layout.addLayout(controls)

        if self.startup_mode:
            self.btn_save.hide()
            self.btn_screens.hide()

        return sidebar

    def _build_content(self) -> QWidget:
        wrapper = QFrame()
        wrapper.setObjectName("contentArea")
        self.content_wrapper = wrapper
        self.content_layout = QVBoxLayout(wrapper)
        self.content_layout.setContentsMargins(12, 12, 12, 12)
        self.content_layout.setSpacing(12)
        self._normal_content_margins = (12, 12, 12, 12)
        self._normal_content_spacing = 12
        self._normal_grid_spacing = 1

        self.topbar_widget = QWidget(wrapper)
        self.topbar = QHBoxLayout(self.topbar_widget)
        self.topbar.setContentsMargins(0, 0, 0, 0)
        self.topbar.setSpacing(8)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("subtleLabel")
        self.topbar.addWidget(self.status_label)
        self.topbar.addStretch()
        self.grid_size_combo = QComboBox()
        self.grid_size_combo.addItems([f"{size}x{size}" for size in range(2, 9)])
        self.grid_size_combo.setCurrentText("2x2")
        self.grid_size_combo.currentTextChanged.connect(self.on_grid_size_changed)
        self.topbar.addWidget(QLabel("Grid"))
        self.topbar.addWidget(self.grid_size_combo)
        self.topbar_widget.hide()

        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setFrameShape(QFrame.NoFrame)
        self.grid_scroll.setStyleSheet("background: transparent; border: none;")

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(self._normal_grid_spacing)
        self.grid_scroll.setWidget(self.grid_container)
        self.content_layout.addWidget(self.grid_scroll, 1)

        self.tv_exit_overlay = QFrame(None)
        self.tv_exit_overlay.setObjectName("tvExitOverlay")
        self.tv_exit_overlay.setWindowFlags(self._tv_exit_overlay_window_flags())
        self.tv_exit_overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.tv_exit_overlay.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.tv_exit_overlay.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.tv_exit_overlay.setStyleSheet("background-color: rgba(0, 0, 0, 0); border: none;")

        self.btn_exit_tv = QToolButton(self.tv_exit_overlay)
        self.btn_exit_tv.setCursor(Qt.PointingHandCursor)
        self.btn_exit_tv.setToolTip("Exit TV mode")
        self.btn_exit_tv.setFixedSize(36, 36)
        self.btn_exit_tv.setAutoRaise(True)
        self.btn_exit_tv.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_exit_tv.move(0, 0)
        self.btn_exit_tv.clicked.connect(lambda: self.set_tv_mode(False))
        self.btn_exit_tv.setStyleSheet(
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
        icon_file = _icon_path("close.svg")
        if os.path.isfile(icon_file):
            self.btn_exit_tv.setIcon(QIcon(icon_file))
            self.btn_exit_tv.setIconSize(QSize(18, 18))
            self.btn_exit_tv.setText("")
        else:
            self.btn_exit_tv.setText("X")
        self.tv_exit_overlay.setFixedSize(self.btn_exit_tv.size())
        self.tv_exit_overlay.hide()
        return wrapper

    def _create_actions(self):
        toggle_sidebar = QAction("Toggle Sidebar", self)
        toggle_sidebar.setShortcut("Ctrl+B")
        toggle_sidebar.triggered.connect(lambda: self.sidebar.setVisible(not self.sidebar.isVisible()))
        self.addAction(toggle_sidebar)

    def _apply_theme(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #111315;
                color: #e5e7eb;
                font-family: Segoe UI, Inter, Arial;
                font-size: 13px;
            }
            QFrame#sidebar {
                background: #171a1d;
                border-right: 1px solid #262b31;
            }
            QLabel#sidebarTitle {
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#headerIcon {
                font-size: 18px;
                min-width: 28px;
                min-height: 28px;
                qproperty-alignment: AlignCenter;
                background: #1e2329;
                border-radius: 8px;
            }
            QLineEdit, QComboBox {
                background: #14181c;
                border: 1px solid #2b3138;
                border-radius: 10px;
                padding: 8px 10px;
                min-height: 20px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #3b82f6;
            }
            QPushButton {
                background: #1d4ed8;
                border: none;
                border-radius: 10px;
                padding: 8px 12px;
                font-weight: 600;
            }
            QPushButton#streamIconButton {
                min-width: 38px;
                max-width: 38px;
                min-height: 38px;
                max-height: 38px;
                padding: 0;
            }
            QPushButton:hover {
                background: #2563eb;
            }
            QPushButton:pressed {
                background: #1e40af;
            }
            QScrollArea#cameraAccordion {
                background: transparent;
                border: none;
            }
            QWidget#cameraAccordionContent {
                background: transparent;
            }
            QFrame#cameraRenderPanel {
                background: transparent;
                border-radius: 18px;
            }
            QFrame#cameraSection {
                background: #31353a;
                border: 1px solid #3d434b;
                border-radius: 18px;
            }
            QFrame#cameraSectionHeader {
                background: transparent;
                border: none;
                border-radius: 16px;
            }
            QFrame#cameraSectionHeader:hover {
                background: rgba(255, 255, 255, 0.03);
            }
            QFrame#accordionIconCard {
                background: #262b31;
                border: 1px solid #353b44;
                border-radius: 14px;
            }
            QLabel#accordionIcon {
                min-width: 22px;
                min-height: 22px;
                color: #dbeafe;
                font-size: 10px;
                font-weight: 800;
                qproperty-alignment: AlignCenter;
            }
            QLabel#cameraSectionEyebrow {
                color: #7dd3fc;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 1px;
            }
            QLabel#cameraSectionTitle {
                color: #f8fafc;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#cameraSectionMeta {
                color: #94a3b8;
                font-size: 11px;
            }
            QLabel#cameraCountBadge {
                background: #262b31;
                color: #dbeafe;
                border: 1px solid #353b44;
                border-radius: 999px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#sectionStateBadge {
                border-radius: 999px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#sectionStateBadge[tone="online"] {
                background: rgba(22, 163, 74, 0.16);
                color: #86efac;
                border: 1px solid rgba(34, 197, 94, 0.45);
            }
            QLabel#sectionStateBadge[tone="offline"] {
                background: rgba(148, 163, 184, 0.12);
                color: #cbd5e1;
                border: 1px solid #374151;
            }
            QLabel#sectionStateBadge[tone="neutral"] {
                background: rgba(59, 130, 246, 0.14);
                color: #bfdbfe;
                border: 1px solid rgba(59, 130, 246, 0.35);
            }
            QLabel#accordionChevron {
                color: #93c5fd;
                font-size: 16px;
                font-weight: 700;
                min-width: 16px;
            }
            QFrame#cameraSectionBody {
                background: transparent;
                border: none;
                border-radius: 0;
            }
            QFrame#cameraAccordionRow {
                background: #121518;
                border: 2px solid #353c45;
                border-radius: 12px;
            }
            QFrame#cameraAccordionRow[online="true"] {
                background: #121518;
                border: 2px solid #353c45;
            }
            QFrame#cameraAccordionRow:hover {
                background: #171b20;
                border: 2px solid #4a5058;
            }
            QFrame#cameraRowIconCard {
                background: #1a1f25;
                border: 1px solid #3a424c;
                border-radius: 12px;
            }
            QLabel#cameraRowIcon {
                min-width: 18px;
                min-height: 18px;
                color: #dbeafe;
                font-size: 8px;
                font-weight: 800;
                qproperty-alignment: AlignCenter;
            }
            QLabel#cameraRowEyebrow {
                color: #7dd3fc;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 1px;
            }
            QLabel#cameraRowTitle {
                color: #f8fafc;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#cameraRowMeta {
                color: #94a3b8;
                font-size: 9px;
                font-weight: 500;
            }
            QFrame#cameraRowFpsCard {
                background: rgba(15, 23, 42, 0.9);
                border: 1px solid rgba(71, 85, 105, 0.72);
                border-radius: 10px;
                min-width: 62px;
            }
            QLabel#cameraRowFpsText {
                background: transparent;
                color: #d8e1ea;
                border: none;
                font-size: 9px;
                font-weight: 800;
                qproperty-alignment: AlignCenter;
            }
            QLabel#cameraDragHint {
                color: #7a8ca3;
                font-size: 10px;
                font-weight: 600;
            }
            QFrame#cameraAccordionEmpty {
                background: #11161b;
                border: 1px dashed #2a313a;
                border-radius: 16px;
            }
            QLabel#cameraEmptyTitle {
                color: #f8fafc;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#cameraEmptyMeta {
                color: #94a3b8;
                font-size: 12px;
            }
            QFrame#contentArea {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #16191d, stop:0.5 #101214, stop:1 #16191d);
            }
            QLabel#subtleLabel {
                color: #9ca3af;
            }
            QFrame#gridCell {
                background: #000000;
                border: 1px solid #20252b;
            }
            QFrame#gridCell[empty="true"] {
                border: none;
            }
            QFrame#gridCell[dropTarget="true"] {
                border: 2px solid rgba(59, 130, 246, 0.95);
            }
            QFrame#gridCell[empty="true"][dropTarget="true"] {
                border: 2px solid rgba(59, 130, 246, 0.95);
            }
            QWidget#streamTopOverlay,
            QWidget#streamBottomOverlay {
                background-color: rgba(0, 0, 0, 0);
                border: none;
            }
            QLabel#videoPlaceholder {
                background: #000000;
                color: #8a9199;
                font-size: 15px;
            }
            QWidget#videoTilePlaceholder {
                background: transparent;
            }
            QLabel#videoTilePlaceholderIcon {
                background: transparent;
            }
            QLabel#videoTilePlaceholderTitle {
                background: transparent;
                color: #f8fafc;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#videoTilePlaceholderDetail {
                background: transparent;
                color: #94a3b8;
                font-size: 12px;
            }
            QLabel#streamCameraName {
                background: transparent;
                color: #f8fafc;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#streamCameraIp {
                background: transparent;
                color: #94a3b8;
                font-size: 11px;
            }
            QLabel#streamCameraName[compact="true"] {
                font-size: 11px;
            }
            QLabel#streamCameraIp[compact="true"] {
                font-size: 10px;
            }
            QLabel#videoPlaceholder[active="true"] {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #0b0f13, stop:1 #111827);
                color: #e5e7eb;
                font-weight: 600;
            }
            QLabel#fpsBadge, QLabel#faceBadge {
                background: rgba(0, 0, 0, 0.72);
                border: 1px solid #2c3137;
                border-radius: 10px;
                padding: 5px 9px;
                color: #d1d5db;
                font-size: 12px;
            }
            QLabel#fpsBadge[compact="true"], QLabel#faceBadge[compact="true"] {
                border-radius: 8px;
                padding: 4px 7px;
                font-size: 11px;
            }
            QLabel#faceBadge {
                color: #86efac;
            }
            QFrame#cameraQueuePanel {
                background: rgba(11, 15, 19, 0.94);
                border: 1px solid #29303a;
                border-radius: 14px;
            }
            QLabel#queuePanelTitle {
                color: #f8fafc;
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#queuePanelCamera {
                color: #f8fafc;
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#queuePanelMeta {
                color: #9ca3af;
                font-size: 12px;
            }
            QLabel#queueCountBadge {
                background: rgba(59,130,246,0.2);
                color: #93c5fd;
                border-radius: 10px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 700;
            }
            QToolButton#queuePanelClose {
                background: rgba(15, 23, 42, 0.82);
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 4px;
            }
            QToolButton#queuePanelClose:hover {
                background: #1f2937;
            }
            QToolButton {
                background: rgba(15, 23, 42, 0.82);
                color: white;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 4px;
            }
            QToolButton:hover {
                background: #1f2937;
            }
            """
        )

    # ------------------------------ data ------------------------------
    def _load_api_data(self):
        try:
            self.client_store.load()
            self.department_store.get_camera_for_user(None, silent=True)
        except Exception as exc:
            self.clients = []
            self.cameras = []
            self.departments = []
            self.client_map = {}
            self.camera_map = {}
            self.saved_configs = []
            self.status_label.setText(f"Failed to load cameras: {exc}")
            return

        self.clients = list(self.client_store.clients)
        self.cameras = list(self.department_store.cameras)
        self.departments = list(self.department_crud_store.load())
        self.client_map = {c.id: c for c in self.clients}
        self.camera_map = {c.id: c for c in self.cameras}

        try:
            self.screen_store.load()
            self.saved_configs = [self._saved_config_from_screen(item) for item in self.screen_store.screens]
            self.status_label.setText(
                f"Loaded {len(self.cameras)} camera(s) and {len(self.saved_configs)} screen layout(s)"
            )
        except Exception:
            self.saved_configs = []
            self.status_label.setText(f"Loaded {len(self.cameras)} camera(s). Screen layouts unavailable.")

    def _saved_config_from_screen(self, screen: ScreenResponse) -> SavedScreenConfig:
        cameras = [
            {"camera_id": assignment.camera_id, "index": assignment.index}
            for assignment in screen.cameras
            if assignment.camera_id > 0
        ]
        return SavedScreenConfig(screen.id, _grid_size_value(screen.screen_type), bool(screen.is_main), cameras)

    def _main_saved_config(self) -> Optional[SavedScreenConfig]:
        return next((cfg for cfg in self.saved_configs if cfg.is_main), None)

    def _default_saved_screen_id(self) -> Optional[int]:
        main_config = self._main_saved_config()
        return main_config.id if main_config is not None else None

    def _apply_default_screen_selection(self) -> None:
        if self.selected_config is not None:
            return
        default_screen_id = self._default_saved_screen_id()
        if default_screen_id is None:
            self.config_combo.blockSignals(True)
            self.config_combo.set_value(MAIN_SCREEN_OPTION)
            self.config_combo.blockSignals(False)
            return
        self.load_configuration_by_id(default_screen_id)

    def _refresh_saved_configs(
        self,
        preferred_screen_id: Optional[int] = None,
        preserve_current_selection: bool = True,
    ) -> None:
        current_id = self.selected_config.id if self.selected_config is not None else None
        self.saved_configs = [self._saved_config_from_screen(item) for item in self.screen_store.screens]
        default_id = self._default_saved_screen_id()
        target_id = (
            preferred_screen_id
            if preferred_screen_id is not None
            else current_id if current_id is not None else default_id
        )
        self.populate_config_combo()

        if not preserve_current_selection:
            self.selected_config = None
            self.config_combo.blockSignals(True)
            self.config_combo.set_value(default_id if default_id is not None else MAIN_SCREEN_OPTION)
            self.config_combo.blockSignals(False)
            self.update_save_button_state()
            return

        if target_id is None:
            self.selected_config = None
            self.config_combo.blockSignals(True)
            self.config_combo.set_value(MAIN_SCREEN_OPTION)
            self.config_combo.blockSignals(False)
            self.update_save_button_state()
            return

        self.selected_config = next((cfg for cfg in self.saved_configs if cfg.id == target_id), None)
        self.config_combo.blockSignals(True)
        self.config_combo.set_value(self.selected_config.id if self.selected_config is not None else MAIN_SCREEN_OPTION)
        self.config_combo.blockSignals(False)
        self.update_save_button_state()

    def _on_lpr_result(self, cam_id: int, record: dict) -> None:
        queue = self.lpr_result_queues.setdefault(cam_id, [])
        queue.append(record)
        if len(queue) > 1000:
            del queue[:-1000]

    def _on_face_result(self, cam_id: int, record: dict) -> None:
        queue = self.face_result_queues.setdefault(cam_id, [])
        queue.append(record)
        if len(queue) > 100:
            del queue[:-100]

    def _on_status_update(self, payload: dict) -> None:
        clients = payload.get("clients")
        cameras = payload.get("cameras")
        client_list = clients if isinstance(clients, list) else []
        camera_list = cameras if isinstance(cameras, list) else []
        if not client_list and not camera_list:
            return

        client_changed = False
        sidebar_needs_refresh = False
        for updated in client_list:
            if not isinstance(updated, dict):
                continue
            client_id = _as_int(updated.get("id"), 0)
            if not client_id:
                continue
            client = self.client_map.get(client_id)
            if client is None:
                continue

            for key in ("name", "ip", "port", "last_seen", "online"):
                if key in updated:
                    value = updated.get(key)
                    if getattr(client, key, None) != value:
                        setattr(client, key, value)
                        client_changed = True
                        if key in {"name", "ip", "port", "online"}:
                            sidebar_needs_refresh = True
            status_data = updated.get("data")
            next_monitor_data = status_data if isinstance(status_data, dict) else {}
            if getattr(client, "monitor_data", None) != next_monitor_data:
                setattr(client, "monitor_data", next_monitor_data)
                client_changed = True

        changed_ids: set[int] = set()
        full_refresh_ids: set[int] = set()
        for updated in camera_list:
            if not isinstance(updated, dict):
                continue
            cam_id = _as_int(updated.get("id"), 0)
            if not cam_id:
                continue
            cam = self.camera_map.get(cam_id)
            if cam is None:
                continue

            flattened_updates: dict[str, object] = {}
            for key, value in updated.items():
                if key == "data":
                    continue
                if hasattr(cam, key):
                    flattened_updates[key] = value

            status_data = updated.get("data")
            if isinstance(status_data, dict):
                for key, value in status_data.items():
                    if key == "id":
                        continue
                    if hasattr(cam, key):
                        flattened_updates[key] = value
            else:
                flattened_updates["streaming_fps"] = 0
                flattened_updates["processing_fps"] = 0

            camera_changed = False
            for key, value in flattened_updates.items():
                if getattr(cam, key, None) == value:
                    continue
                setattr(cam, key, value)
                camera_changed = True
                if key in {"camera_ip", "ip", "camera_port", "camera_username", "camera_password", "camera_type"}:
                    full_refresh_ids.add(cam_id)
                if key in {"name", "online", "ip", "camera_ip", "process_type", "client_id_1", "client_id_2"}:
                    sidebar_needs_refresh = True
                if key in {"process_type", "face_show_rect"}:
                    full_refresh_ids.add(cam_id)
            if camera_changed:
                changed_ids.add(cam_id)

        if not changed_ids and not client_changed:
            return
        for cell in self.screen_cells:
            if cell.camera and cell.camera.id in changed_ids:
                if cell.camera.id in full_refresh_ids:
                    cell.refresh()
                else:
                    cell.sync_runtime_status()
        self._sync_camera_queue_panel()
        if sidebar_needs_refresh:
            self.populate_camera_tree()

    def populate_camera_tree(self):
        query = self.search.text().strip().lower()
        section_camera_ids: set[int] = set()
        camera_by_id = {int(getattr(cam, "id", 0) or 0): cam for cam in self.cameras if _as_int(getattr(cam, "id", 0), 0) > 0}
        sections: List[dict] = []
        sorted_departments = sorted(
            self.departments,
            key=lambda department: str(getattr(department, "name", "") or "").lower(),
        )

        for department in sorted_departments:
            department_camera_ids = []
            seen_camera_ids: set[int] = set()
            for camera_id in getattr(department, "camera_ids", []):
                normalized_id = _as_int(camera_id, 0)
                if normalized_id <= 0 or normalized_id in seen_camera_ids:
                    continue
                seen_camera_ids.add(normalized_id)
                department_camera_ids.append(normalized_id)

            related_cameras = [
                camera_by_id[camera_id]
                for camera_id in department_camera_ids
                if camera_id in camera_by_id
            ]
            if not related_cameras:
                continue

            department_name = str(getattr(department, "name", "") or f"Department {getattr(department, 'id', 0)}").strip()
            department_match = query in department_name.lower() if query else False
            if query and not department_match:
                related_cameras = [
                    cam
                    for cam in related_cameras
                    if query in str(getattr(cam, "name", "") or "").lower()
                    or query in _camera_ip(cam).lower()
                ]
                if not related_cameras:
                    continue

            related_cameras = sorted(
                related_cameras,
                key=lambda cam: (
                    not bool(getattr(cam, "online", False)),
                    str(getattr(cam, "name", "") or "").lower(),
                ),
            )
            section_camera_ids.update(_as_int(getattr(cam, "id", 0), 0) for cam in related_cameras)
            sections.append(
                {
                    "key": f"department:{_as_int(getattr(department, 'id', 0), 0)}",
                    "title": department_name,
                    "subtitle": "",
                    "eyebrow_text": "DEPARTMENT",
                    "icon_name": "home.svg",
                    "count_text": "",
                    "state_text": "",
                    "state_tone": "neutral",
                    "expanded": bool(query) or not sections,
                    "force_expanded": bool(query),
                    "cameras": related_cameras,
                }
            )

        visible_unassigned = [
            cam
            for cam in self.cameras
            if _as_int(getattr(cam, "id", 0), 0) not in section_camera_ids
            if not query
            or query in str(getattr(cam, "name", "") or "").lower()
            or query in _camera_ip(cam).lower()
            or query in "unassigned"
        ]
        if visible_unassigned:
            visible_unassigned = sorted(
                visible_unassigned,
                key=lambda cam: (
                    not bool(getattr(cam, "online", False)),
                    str(getattr(cam, "name", "") or "").lower(),
                ),
            )
            sections.append(
                {
                    "key": "unassigned",
                    "title": "",
                    "subtitle": "",
                    "eyebrow_text": "UNASSIGNED GROUP",
                    "icon_name": "camera.svg",
                    "count_text": "",
                    "state_text": "",
                    "state_tone": "neutral",
                    "expanded": bool(query) or not sections,
                    "force_expanded": bool(query),
                    "cameras": visible_unassigned,
                }
            )

        empty_message = (
            "Try a different search term."
            if query
            else "No department cameras are available for this account yet."
        )
        self.camera_tree.set_sections(sections, empty_message=empty_message)

    def populate_config_combo(self):
        self.config_combo.blockSignals(True)
        options = [{"label": "Main Screen", "value": MAIN_SCREEN_OPTION}]
        for cfg in self.saved_configs:
            grid_size = _grid_size_value(cfg.screen_type)
            options.append(
                {
                    "label": f"{grid_size}x{grid_size} Grid ({len(cfg.cameras)} cameras){' • Main' if cfg.is_main else ''}",
                    "value": cfg.id,
                }
            )
        self.config_combo.set_options(options)
        current_value = (
            self.selected_config.id
            if self.selected_config is not None
            else self._default_saved_screen_id() or MAIN_SCREEN_OPTION
        )
        self.config_combo.set_value(current_value)
        self.config_combo.blockSignals(False)

    # ------------------------------ grid ------------------------------
    def on_grid_size_changed(self, text: str):
        self.selected_grid_size = int(text.split("x")[0])
        self.selected_config = None
        self.config_combo.blockSignals(True)
        self.config_combo.set_value(MAIN_SCREEN_OPTION)
        self.config_combo.blockSignals(False)
        self.rebuild_grid(preserve_existing=True)

    def _grid_cell_minimum_size(self) -> QSize:
        if self.selected_grid_size >= 7:
            return QSize(110, 82)
        if self.selected_grid_size >= 5:
            return QSize(135, 96)
        return QSize(180, 120)

    def rebuild_grid(self, preserve_existing: bool = False):
        existing_cameras = []
        if preserve_existing:
            existing_cameras = [cell.camera for cell in self.screen_cells]

        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                if isinstance(widget, GridCell):
                    widget.set_camera(None)
                widget.deleteLater()

        self.screen_cells.clear()
        total = self.selected_grid_size * self.selected_grid_size
        min_size = self._grid_cell_minimum_size()
        self.grid_layout.setSpacing(0 if self.selected_grid_size >= 6 else self._normal_grid_spacing)
        for idx in range(total):
            cell = GridCell(idx, login_on_right_click=self.startup_mode)
            cell.setMinimumSize(min_size)
            cell.removeRequested.connect(self.remove_stream)
            cell.detailsRequested.connect(self.open_camera_details)
            cell.doorRequested.connect(self.open_door_control)
            cell.focusRequested.connect(self.toggle_focused_camera)
            cell.dropCamera.connect(self.on_drop_camera)
            cell.swapRequested.connect(self.swap_cells)
            cell.loginRequested.connect(self.loginRequested.emit)
            self.screen_cells.append(cell)
            row = idx // self.selected_grid_size
            col = idx % self.selected_grid_size
            self.grid_layout.addWidget(cell, row, col)

        if preserve_existing:
            for idx, cam in enumerate(existing_cameras[: len(self.screen_cells)]):
                self.screen_cells[idx].set_camera(cam)
        for cell in self.screen_cells:
            cell.set_tv_mode(self.is_tv_mode)

        self.refresh_grid_visibility()
        self.update_save_button_state()
        self._position_exit_tv_button()

    def _apply_startup_layout(self) -> None:
        if not self.startup_mode or not self.screen_cells:
            return
        if any(cell.camera is not None for cell in self.screen_cells):
            return
        visible_cameras = sorted(
            self.cameras,
            key=lambda cam: (
                not bool(getattr(cam, "online", False)),
                str(getattr(cam, "name", "") or "").lower(),
            ),
        )
        if not visible_cameras:
            return
        for cell, camera in zip(self.screen_cells, visible_cameras):
            cell.set_camera(camera)
        self.focused_camera_id = None
        self.queue_camera_id = None
        self.refresh_grid_visibility()
        self.status_label.setText(f"Loaded {min(len(visible_cameras), len(self.screen_cells))} startup camera(s)")

    def refresh_grid_visibility(self):
        if self.queue_camera_id is not None and self.focused_camera_id != self.queue_camera_id and not self.is_tv_mode:
            self.queue_camera_id = None
        active = [cell for cell in self.screen_cells if cell.camera is not None]
        use_single = self.focused_camera_id is not None or len(active) == 1

        for cell in self.screen_cells:
            if not use_single:
                cell.show()
                continue
            visible = False
            if self.focused_camera_id is not None:
                visible = bool(cell.camera and cell.camera.id == self.focused_camera_id)
            else:
                visible = cell.camera is not None
            if not visible:
                cell.deactivate_overlay()
            cell.setVisible(visible)
        self._apply_stream_profiles()
        self._sync_camera_queue_panel()

    def _screen_camera_by_id(self, camera_id: Optional[int]) -> Optional["DevicesCamera"]:
        if camera_id is None:
            return None
        for cell in self.screen_cells:
            if cell.camera and cell.camera.id == camera_id:
                return cell.camera
        return None

    def _set_sidebar_width_mode(self, show_queue: bool) -> None:
        if not hasattr(self, "sidebar"):
            return
        self._apply_fixed_sidebar_split()

    def _apply_fixed_sidebar_split(self) -> None:
        if not hasattr(self, "sidebar") or not hasattr(self, "main_splitter"):
            return
        total_width = self.main_splitter.width()
        if total_width <= 0:
            sizes = self.main_splitter.sizes()
            total_width = sum(sizes) if sizes else self.width()
        total_width = max(total_width, 2)
        sidebar_width = max(1, int(total_width * self._sidebar_ratio))
        sidebar_width = max(self._sidebar_min_width, min(self._sidebar_max_width, sidebar_width))
        if total_width - sidebar_width < self._content_min_width:
            sidebar_width = max(1, total_width - self._content_min_width)
        content_width = max(1, total_width - sidebar_width)
        self._camera_sidebar_width = sidebar_width
        self._queue_sidebar_width = sidebar_width
        self.sidebar.setMinimumWidth(sidebar_width)
        self.sidebar.setMaximumWidth(sidebar_width)
        self.main_splitter.setSizes([sidebar_width, content_width])

    def _sync_camera_queue_panel(self) -> None:
        if not hasattr(self, "camera_queue_panel") or not hasattr(self, "sidebar_stack"):
            return
        camera = self._screen_camera_by_id(self.queue_camera_id)
        if camera is None:
            self.queue_camera_id = None
            self.camera_queue_panel.set_camera(None)
            self.sidebar_title.setText("Cameras")
            self.search.show()
            self.sidebar_stack.setCurrentWidget(self.sidebar_camera_page)
            self._set_sidebar_width_mode(False)
            return
        self.camera_queue_panel.set_camera(camera)
        show_queue = bool(not self.is_tv_mode and self.focused_camera_id == camera.id)
        self.sidebar_title.setText("Results")
        self.search.setVisible(not show_queue)
        self.sidebar_stack.setCurrentWidget(self.sidebar_queue_page if show_queue else self.sidebar_camera_page)
        self._set_sidebar_width_mode(show_queue)
        if not show_queue:
            self.sidebar_title.setText("Cameras")
            self.search.show()

    def _show_camera_queue(self, camera: "DevicesCamera") -> None:
        self.focused_camera_id = camera.id
        self.queue_camera_id = camera.id
        self.refresh_grid_visibility()
        self.status_label.setText(f"Showing results queue for {camera.name}")

    def close_camera_queue_panel(self) -> None:
        camera = self._screen_camera_by_id(self.queue_camera_id)
        self.queue_camera_id = None
        self.refresh_grid_visibility()
        if camera is not None:
            self.status_label.setText(f"Closed queue for {camera.name}")
        else:
            self.status_label.setText("Closed queue view")

    def _apply_stream_profiles(self):
        force_main_for_all = _env_flag("LIVE_VIEW_FORCE_MAIN_STREAM_ALL", False)
        for cell in self.screen_cells:
            if cell.camera is None:
                continue
            use_main = bool(force_main_for_all or (self.focused_camera_id is not None and cell.camera.id == self.focused_camera_id))
            cell.set_main_stream(use_main)

    def on_drop_camera(self, index: int, cam_id: int):
        camera = self.camera_map.get(cam_id)
        if not camera:
            return
        if any(cell.camera and cell.camera.id == cam_id for cell in self.screen_cells):
            self.status_label.setText("Camera already shown in grid")
            return
        self.screen_cells[index].set_camera(camera)
        self.screen_cells[index].replay_stream()
        self.status_label.setText(f"Added {camera.name} to slot {index + 1}")
        self.refresh_grid_visibility()
        self.update_save_button_state()

    def swap_cells(self, from_index: int, to_index: int):
        left = self.screen_cells[from_index].camera
        right = self.screen_cells[to_index].camera
        self.screen_cells[from_index].set_camera(right)
        self.screen_cells[to_index].set_camera(left)
        self.screen_cells[from_index].replay_stream()
        self.screen_cells[to_index].replay_stream()
        self.refresh_grid_visibility()
        self.update_save_button_state()

    def remove_stream(self, index: int):
        shifted = [self.screen_cells[i + 1].camera for i in range(index, len(self.screen_cells) - 1)]
        for i in range(index, len(self.screen_cells) - 1):
            self.screen_cells[i].set_camera(shifted[i - index])
        self.screen_cells[-1].set_camera(None)
        self.focused_camera_id = None if not any(c.camera and c.camera.id == self.focused_camera_id for c in self.screen_cells) else self.focused_camera_id
        self.refresh_grid_visibility()
        self.update_save_button_state()

    def add_camera_to_last_stream(self, cam_id: int):
        camera = self.camera_map.get(cam_id)
        if not camera:
            return
        existing = next((cell for cell in self.screen_cells if cell.camera and cell.camera.id == cam_id), None)
        if existing is not None:
            self.focused_camera_id = camera.id
            self.refresh_grid_visibility()
            self.update_save_button_state()
            self.status_label.setText(f"Focused {camera.name}")
            return
        for cell in self.screen_cells:
            if cell.camera is None:
                cell.set_camera(camera)
                self.focused_camera_id = camera.id
                self.status_label.setText(f"Loaded {camera.name}")
                self.refresh_grid_visibility()
                self.update_save_button_state()
                return
        self.status_label.setText("No empty slot available")

    # ------------------------------ actions ------------------------------
    def toggle_focused_camera(self, index: int):
        camera = self.screen_cells[index].camera
        if not camera:
            return
        if self.focused_camera_id == camera.id and self.queue_camera_id is None:
            self.focused_camera_id = None
            self.refresh_grid_visibility()
            self.status_label.setText("Restored grid view")
            return
        self.focused_camera_id = camera.id
        self.queue_camera_id = None
        self.refresh_grid_visibility()
        self.status_label.setText(f"Maximized {camera.name}")

    def open_camera_details(self, index: int):
        camera = self.screen_cells[index].camera
        if not camera:
            return
        if self.focused_camera_id == camera.id and self.queue_camera_id == camera.id:
            self.close_camera_queue_panel()
            return
        self._show_camera_queue(camera)

    def open_door_control(self, index: int):
        camera = self.screen_cells[index].camera
        if not camera:
            return
        self._toast_info("Door Control", f"Door relay triggered for {camera.name}.")

    def toggle_tv_mode(self):
        self.set_tv_mode(not self.is_tv_mode)

    def _tv_exit_overlay_window_flags(self) -> Qt.WindowFlags:
        return (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )

    def _ensure_exit_tv_overlay_owner(self) -> None:
        if not hasattr(self, "tv_exit_overlay"):
            return
        owner = self.window()
        if owner is None or owner is self.tv_exit_overlay:
            return
        current_flags = self.tv_exit_overlay.windowFlags()
        if (
            self.tv_exit_overlay.parentWidget() is owner
            and not bool(current_flags & Qt.WindowType.WindowStaysOnTopHint)
        ):
            return
        was_visible = self.tv_exit_overlay.isVisible()
        self.tv_exit_overlay.hide()
        self.tv_exit_overlay.setParent(owner, self._tv_exit_overlay_window_flags())
        self.tv_exit_overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.tv_exit_overlay.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.tv_exit_overlay.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        if was_visible:
            self.tv_exit_overlay.show()

    def set_tv_mode(self, enabled: bool):
        if self.is_tv_mode == enabled:
            return
        self.is_tv_mode = enabled
        self.sidebar.setVisible(not enabled)
        self.topbar_widget.hide()
        self.btn_tv.setToolTip("Exit TV mode" if enabled else "Enter TV mode")
        self.status_label.setText("TV mode enabled" if enabled else "TV mode disabled")
        if enabled:
            self.content_layout.setContentsMargins(0, 0, 0, 0)
            self.content_layout.setSpacing(0)
            self.grid_layout.setSpacing(0)
            self._position_exit_tv_button()
            self.tv_exit_overlay.show()
            self.tv_exit_overlay.raise_()
        else:
            self.tv_exit_overlay.hide()
            l, t, r, b = self._normal_content_margins
            self.content_layout.setContentsMargins(l, t, r, b)
            self.content_layout.setSpacing(self._normal_content_spacing)
            self.grid_layout.setSpacing(0 if self.selected_grid_size >= 6 else self._normal_grid_spacing)
        for cell in self.screen_cells:
            cell.set_tv_mode(enabled)
        self._sync_camera_queue_panel()
        self._position_exit_tv_button()
        self.tvModeChanged.emit(enabled)

    def save_current_screen(self):
        cameras = [
            {"camera_id": cell.camera.id, "index": idx}
            for idx, cell in enumerate(self.screen_cells)
            if cell.camera is not None
        ]
        if not cameras:
            self._toast_warn("Save Screen", "No cameras to save. Add at least one camera.")
            return

        payload = {
            "screen_type": _grid_size_value(self.selected_grid_size),
            "is_main": bool(self.selected_config.is_main) if self.selected_config is not None else False,
            "cameras": cameras,
        }
        try:
            if self.selected_config is None:
                saved = self.screen_store.create_screen(payload)
                self._toast_success("Save Screen", f"Screen #{saved.id} saved.")
                self.status_label.setText(f"Saved {saved.screen_type}x{saved.screen_type} layout")
            else:
                payload["screen_id"] = self.selected_config.id
                saved = self.screen_store.update_screen(payload)
                self._toast_success("Save Screen", f"Screen #{saved.id} updated.")
                self.status_label.setText(f"Updated {saved.screen_type}x{saved.screen_type} layout")
        except Exception as exc:
            self._toast_error("Save Screen", str(exc))
            return

        self._refresh_saved_configs(preferred_screen_id=saved.id)
        self.update_save_button_state()

    def open_screens_manager(self):
        dialog = StreamScreensManagerDialog(self.screen_store, self.cameras, self)
        result = dialog.exec()
        preferred_id = dialog.selected_screen_id
        self._refresh_saved_configs(preferred_screen_id=preferred_id)
        if result == QDialog.DialogCode.Accepted and preferred_id is not None:
            self.load_configuration_by_id(preferred_id)
            return
        if result == QDialog.DialogCode.Accepted:
            self._apply_default_screen_selection()

    def load_configuration_by_index(self, combo_index: int):
        screen_id = None
        if combo_index > 0 and combo_index - 1 < len(self.saved_configs):
            screen_id = self.saved_configs[combo_index - 1].id
        self.load_configuration_by_id(screen_id)

    def load_configuration_by_id(self, screen_id):
        if screen_id in {None, MAIN_SCREEN_OPTION}:
            self.selected_config = None
            self.config_combo.blockSignals(True)
            self.config_combo.set_value(MAIN_SCREEN_OPTION)
            self.config_combo.blockSignals(False)
            self.update_save_button_state()
            return

        cfg = next((item for item in self.saved_configs if item.id == screen_id), None)
        if cfg is None:
            self.selected_config = None
            self.config_combo.blockSignals(True)
            self.config_combo.set_value(MAIN_SCREEN_OPTION)
            self.config_combo.blockSignals(False)
            self.update_save_button_state()
            return

        self.selected_config = cfg
        self.selected_grid_size = _grid_size_value(cfg.screen_type)
        self.grid_size_combo.blockSignals(True)
        self.grid_size_combo.setCurrentText(f"{self.selected_grid_size}x{self.selected_grid_size}")
        self.grid_size_combo.blockSignals(False)
        self.rebuild_grid()

        for cell in self.screen_cells:
            cell.set_camera(None)

        for assignment in cfg.cameras:
            index = assignment["index"]
            camera = self.camera_map.get(assignment["camera_id"])
            if 0 <= index < len(self.screen_cells) and camera:
                self.screen_cells[index].set_camera(camera)
        self.focused_camera_id = None
        self.refresh_grid_visibility()
        self.status_label.setText(f"Loaded {self.selected_grid_size}x{self.selected_grid_size} configuration")
        self.update_save_button_state()

    def closeEvent(self, event):
        self.ws_client.close()
        self.tv_exit_overlay.close()
        for cell in self.screen_cells:
            cell.set_camera(None)
        super().closeEvent(event)

    def hideEvent(self, event):
        self.deactivate_overlays()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_fixed_sidebar_split()
        QTimer.singleShot(0, self._apply_fixed_sidebar_split)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_fixed_sidebar_split()
        self._position_exit_tv_button()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._position_exit_tv_button()

    def _position_exit_tv_button(self):
        if not hasattr(self, "tv_exit_overlay") or not hasattr(self, "content_wrapper"):
            return
        self._ensure_exit_tv_overlay_owner()
        if not self.content_wrapper.isVisible():
            return
        margin = 14
        size = self.tv_exit_overlay.size()
        top_left = self.content_wrapper.mapToGlobal(QPoint(0, 0))
        self.tv_exit_overlay.setGeometry(
            top_left.x() + max(margin, self.content_wrapper.width() - size.width() - margin),
            top_left.y() + margin,
            size.width(),
            size.height(),
        )
        if self.is_tv_mode:
            self.tv_exit_overlay.raise_()

    def deactivate_overlays(self) -> None:
        if hasattr(self, "tv_exit_overlay"):
            self.tv_exit_overlay.hide()
        for cell in getattr(self, "screen_cells", []):
            try:
                cell.deactivate_overlay()
            except RuntimeError:
                continue

    # ------------------------------ state ------------------------------
    def current_layout_signature(self):
        return [
            (idx, cell.camera.id if cell.camera else None)
            for idx, cell in enumerate(self.screen_cells)
        ]

    def selected_layout_signature(self):
        if self.selected_config is None:
            return []
        total = self.selected_config.screen_type * self.selected_config.screen_type
        sig = [(i, None) for i in range(total)]
        sig_map = {item[0]: item[1] for item in sig}
        for assignment in self.selected_config.cameras:
            sig_map[assignment["index"]] = assignment["camera_id"]
        return sorted(sig_map.items())

    def has_unsaved_changes(self) -> bool:
        current = self.current_layout_signature()
        if self.selected_config is None:
            return any(cam_id is not None for _, cam_id in current)
        if self.selected_config.screen_type != self.selected_grid_size:
            return True
        return current != self.selected_layout_signature()

    def update_save_button_state(self):
        if self.startup_mode:
            self.btn_save.hide()
            return
        self.btn_save.setVisible(self.has_unsaved_changes())
