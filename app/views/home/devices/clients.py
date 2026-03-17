from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, QSize, Qt, QTimer, QUrl, Signal,QRectF
from PySide6.QtGui import QIcon,QPainter,QPainterPath,QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from app.constants._init_ import Constants
try:
    from PySide6.QtWebSockets import QWebSocket
except Exception:  # pragma: no cover - optional runtime dependency
    QWebSocket = None

from app.models.client import Client
from app.services.auth.auth_service import AuthService
from app.services.home.devices.client_service import ClientService
from app.store.auth import AuthStore
from app.store.home.devices.client_store import ClientStore
from app.ui.table import PrimeDataTable, PrimeTableColumn
from app.utils.env import resolve_http_base_url


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


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
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


def _normalize_ip(value: str) -> str:
    text = (value or "").strip().lower()
    if text.count(":") == 1 and "." in text:
        text = text.split(":", 1)[0]
    return text


def _format_percent(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return f"{int(round(value))} %"
    return f"{value:.1f} %"


@dataclass
class ClientUsageSnapshot:
    cpu: float = 0.0
    memory: float = 0.0
    gpu: float = 0.0
    disk: float = 0.0
    online: Optional[bool] = None


class ClientUsageWs(QObject):
    usageUpdate = Signal(dict)
    connectionChanged = Signal(bool)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._url = _monitor_ws_url()
        self._ws = QWebSocket() if QWebSocket is not None else None
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

        msg_type = str(message.get("type") or "").strip().lower()
        if msg_type != "status_update":
            return

        payload = message.get("payload")
        updates = self._extract_usage_updates(payload)
        for update in updates:
            self.usageUpdate.emit(update)

    @classmethod
    def _extract_usage_updates(cls, payload: Any) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []

        def has_identifier(node: Dict[str, Any]) -> bool:
            lowered = {str(k).strip().lower() for k in node.keys()}
            return bool(
                lowered
                & {
                    "id",
                    "client_id",
                    "ip",
                    "ip_port",
                    "client_ip",
                    "server_ip",
                    "name",
                    "client_name",
                    "host_name",
                }
            )

        def walk(node: Any) -> None:
            if isinstance(node, list):
                for item in node:
                    walk(item)
                return

            if not isinstance(node, dict):
                return

            if cls._looks_like_client_usage(node):
                candidates.append(node)

            for key, value in node.items():
                lowered = str(key).strip().lower()
                if isinstance(value, dict):
                    promoted = dict(value)
                    if not has_identifier(promoted):
                        raw_name = str(key).strip()
                        if raw_name and lowered not in {
                            "clients",
                            "client",
                            "servers",
                            "hosts",
                            "nodes",
                            "machines",
                            "devices",
                            "status",
                            "stats",
                            "usage",
                            "payload",
                            "data",
                            "result",
                            "results",
                            "metrics",
                            "resources",
                            "system",
                        }:
                            promoted["name"] = raw_name
                    walk(promoted)
                    continue
                if isinstance(value, list):
                    walk(value)

        walk(payload)

        normalized: List[Dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for item in candidates:
            update = cls._normalize_update(item)
            key = (
                update.get("id", 0),
                update.get("ip", ""),
                update.get("port", 0),
                update.get("name", ""),
                update.get("cpu"),
                update.get("memory"),
                update.get("gpu"),
                update.get("disk"),
                update.get("online"),
            )
            if key in seen:
                continue
            seen.add(key)
            normalized.append(update)
        return normalized

    @classmethod
    def _looks_like_client_usage(cls, node: Dict[str, Any]) -> bool:
        keys = {str(k).strip().lower() for k in node.keys()}
        identifier_keys = {
            "id",
            "client_id",
            "ip",
            "ip_port",
            "client_ip",
            "server_ip",
            "name",
            "client_name",
            "host_name",
        }
        usage_keys = {
            "cpu_usage",
            "cpu",
            "cpu_percent",
            "memory_usage",
            "memory",
            "memory_percent",
            "mem",
            "ram",
            "memory_info",
            "gpu_usage",
            "gpu",
            "gpu_load",
            "disk_usage",
            "disk",
            "storage",
            "filesystem",
            "fs",
            "data",
            "used_percent",
            "usage",
            "stats",
            "metrics",
            "resources",
            "system",
            "online",
            "status",
            "connected",
            "is_online",
        }
        has_usage_container = any(
            isinstance(node.get(k), (dict, list))
            for k in ("usage", "stats", "metrics", "resources", "system")
        )
        return bool(keys & identifier_keys) and (bool(keys & usage_keys) or has_usage_container)

    @classmethod
    def _parse_number(cls, value: Any) -> Optional[float]:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            clean = value.strip().replace(",", "").replace("%", "")
            if not clean:
                return None
            try:
                return float(clean)
            except ValueError:
                match = re.search(r"-?\d+(?:\.\d+)?", clean)
                if match:
                    return float(match.group(0))
        return None

    @classmethod
    def _parse_percent(cls, value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            parsed_values: List[float] = []
            for item in value:
                parsed = cls._parse_percent(item)
                if parsed is not None:
                    parsed_values.append(parsed)
            if not parsed_values:
                return None
            return sum(parsed_values) / len(parsed_values)
        if isinstance(value, dict):
            for key in (
                "value",
                "percent",
                "percentage",
                "usage",
                "used_percent",
                "usedPercentage",
                "load",
                "ratio",
                "pct",
            ):
                if key in value:
                    parsed = cls._parse_percent(value.get(key))
                    if parsed is not None:
                        return parsed

            used = cls._parse_number(
                value.get("used")
                or value.get("use")
                or value.get("used_bytes")
                or value.get("used_memory")
                or value.get("occupied")
            )
            total = cls._parse_number(
                value.get("total")
                or value.get("capacity")
                or value.get("max")
                or value.get("all")
            )
            if used is not None and total is not None and total > 0:
                return max(0.0, min(100.0, (used / total) * 100.0))

            free = cls._parse_number(
                value.get("free")
                or value.get("available")
                or value.get("avail")
            )
            if free is not None and total is not None and total > 0:
                return max(0.0, min(100.0, ((total - free) / total) * 100.0))

            for nested_key in ("stats", "usage", "memory", "ram", "disk", "storage", "gpu", "metrics", "data"):
                nested = value.get(nested_key)
                if nested is None:
                    continue
                parsed = cls._parse_percent(nested)
                if parsed is not None:
                    return parsed
            return None

        source_had_percent = False
        if isinstance(value, str):
            source_had_percent = "%" in value
        parsed = cls._parse_number(value)
        if parsed is None:
            return None

        if not source_had_percent and 0.0 <= parsed <= 1.0:
            parsed *= 100.0
        parsed = max(0.0, min(100.0, parsed))
        return parsed

    @classmethod
    def _parse_online(cls, value: Any) -> Optional[bool]:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"online", "connected", "up", "running", "active", "alive", "true", "1", "yes"}:
                return True
            if normalized in {"offline", "disconnected", "down", "inactive", "stopped", "dead", "false", "0", "no", "error"}:
                return False
            return None
        if isinstance(value, (bool, int, float)):
            return _as_bool(value)
        return None

    @classmethod
    def _normalize_update(cls, source: Dict[str, Any]) -> Dict[str, Any]:
        usage = {}
        for key in ("data", "usage", "stats", "metrics", "resources", "system"):
            value = source.get(key)
            if isinstance(value, dict):
                usage = value
                break
        nested_client = source.get("client") if isinstance(source.get("client"), dict) else {}

        def pick_case_insensitive(container: Dict[str, Any], name: str) -> Any:
            lowered = name.lower()
            for key, value in container.items():
                if str(key).strip().lower() == lowered:
                    return value
            return None

        def pick(*names: str) -> Any:
            for name in names:
                for container in (source, usage, nested_client):
                    if name in container:
                        return container.get(name)
                    ci_value = pick_case_insensitive(container, name)
                    if ci_value is not None:
                        return ci_value
            return None

        raw_ip = str(
            pick("ip", "client_ip", "server_ip", "host", "address", "ip_port", "host_port")
            or ""
        ).strip()
        parsed_port = _as_int(pick("port", "client_port", "server_port"), 0)
        if not parsed_port and raw_ip.count(":") == 1 and "." in raw_ip:
            maybe_port = raw_ip.rsplit(":", 1)[1]
            parsed_port = _as_int(maybe_port, 0)

        cpu = cls._parse_percent(pick("cpu_usage", "cpu_percent", "cpu", "cpuUsage"))
        memory = cls._parse_percent(
            pick(
                "memory_usage",
                "memory_percent",
                "memory",
                "mem_usage",
                "mem",
                "ram_usage",
                "ram",
                "memory_info",
            )
        )
        gpu = cls._parse_percent(pick("gpu_usage", "gpu_percent", "gpu", "gpu_load", "vram_usage"))
        disk = cls._parse_percent(
            pick(
                "disk_usage",
                "disk_percent",
                "disk",
                "storage_usage",
                "storage",
                "hdd_usage",
                "filesystem",
                "fs",
                "used_percent",
            )
        )
        online = cls._parse_online(
            pick("online", "is_online", "connected", "alive", "status", "state", "is_alive")
        )

        return {
            "id": _as_int(pick("id", "client_id", "cid"), 0),
            "name": str(pick("name", "client_name", "host_name", "hostname") or "").strip(),
            "ip": _normalize_ip(raw_ip),
            "port": parsed_port,
            "cpu": cpu,
            "memory": memory,
            "gpu": gpu,
            "disk": disk,
            "online": online,
        }


class ClientFormDialog(QDialog):
    submitted = Signal(dict, bool)

    def __init__(self, client: Optional[Client] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.client = client
        self.is_edit_mode = client is not None

        self.setWindowTitle("Edit Client" if self.is_edit_mode else "Add New Client")
        self.resize(460, 360)

        root = QVBoxLayout(self)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setSpacing(10)

        self.name_edit = QLineEdit()
        self.ip_edit = QLineEdit()
        self.port_spin = QSpinBox()
        self.port_spin.setMaximum(65535)
        self.port_spin.setValue(5050)

        self.type_combo = QComboBox()
        self.type_combo.addItem("Process", "process")
        self.type_combo.addItem("Record", "record")

        self.save_path_edit = QLineEdit()
        self.local_check = QCheckBox("Local Client")
        self.local_check.setChecked(True)

        form.addRow("Name *", self.name_edit)
        form.addRow("IP *", self.ip_edit)
        form.addRow("Port", self.port_spin)
        form.addRow("Type *", self.type_combo)
        form.addRow("Save Path", self.save_path_edit)
        form.addRow("", self.local_check)
        root.addLayout(form)

        controls = QHBoxLayout()
        controls.addStretch(1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        controls.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._submit)
        controls.addWidget(save_btn)

        root.addLayout(controls)

        self._apply_style()
        if self.client is not None:
            self._fill(self.client)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #171a1f;
                color: #f1f5f9;
            }
            QLineEdit, QSpinBox, QComboBox {
                background: #232831;
                border: 1px solid #3a424f;
                border-radius: 8px;
                color: #f8fafc;
                padding: 6px 8px;
                min-height: 24px;
            }
            QCheckBox {
                color: #d7dde8;
                spacing: 8px;
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

    def _fill(self, client: Client) -> None:
        self.name_edit.setText(client.name)
        self.ip_edit.setText(client.ip)
        self.port_spin.setValue(max(0, int(client.port or 0)))
        idx = self.type_combo.findData(client.type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.save_path_edit.setText(client.save_path)
        self.local_check.setChecked(bool(client.is_local))

    def _submit(self) -> None:
        name = self.name_edit.text().strip()
        ip = self.ip_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing", "Client name is required.")
            return
        if not ip:
            QMessageBox.warning(self, "Missing", "Client IP is required.")
            return

        payload = {
            "name": name,
            "ip": ip,
            "port": int(self.port_spin.value()),
            "type": str(self.type_combo.currentData() or "process"),
            "save_path": self.save_path_edit.text().strip(),
            "is_local": bool(self.local_check.isChecked()),
        }

        if self.client is not None:
            payload["id"] = int(self.client.id)

        self.submitted.emit(payload, self.is_edit_mode)
        self.accept()


class ClientPage(QWidget):
    navigate = Signal(str)

    def __init__(
        self,
        auth_store: Optional[AuthStore] = None,
        client_store: Optional[ClientStore] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.auth_store = auth_store or AuthStore(AuthService())
        self.client_store = client_store or ClientStore(ClientService())
        self._usage_by_client_id: Dict[int, ClientUsageSnapshot] = {}
        self._ws_connected = False

        self.auth_store.changed.connect(self.refresh)
        self.auth_store.error.connect(self._show_error)
        self.client_store.changed.connect(self.refresh)
        self.client_store.error.connect(self._show_error)
        self.client_store.success.connect(self._show_info)

        self._build_ui()
        self._apply_style()

        self.auth_store.load()
        self.client_store.load()

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_clients)
        self._poll_timer.start(15000)

        self._ws_client = ClientUsageWs(self)
        self._ws_client.connectionChanged.connect(self._on_ws_connection)
        self._ws_client.usageUpdate.connect(self._on_usage_update)
        self._ws_client.connect_socket()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("clientSideNav")
        self.sidebar.setFixedWidth(96)
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(8, 12, 8, 12)
        side_layout.setSpacing(10)
        side_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        nav_items = [
            ("Clients", "user_management.svg", "/device/clients"),
            ("Cameras", "devices.svg", "/device/cameras"),
            # ("GPS", "gps.svg", "/device/gps"),
            # ("Bodycam", "bodycam.svg", "/device/body-cam"),
            ("Access", "activation.svg", "/device/access-control"),
        ]
        current_path = "/device/clients"
        for label, icon_name, path in nav_items:
            btn = QToolButton()
            btn.setText(label)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setFixedSize(72, 72)
            icon_file = _icon_path(icon_name)
            if os.path.isfile(icon_file):
                btn.setIcon(QIcon(icon_file))
                btn.setIconSize(QSize(22, 22))
            btn.setObjectName("clientSideBtnActive" if path == current_path else "clientSideBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, p=path: self.navigate.emit(p))
            side_layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
        side_layout.addStretch(1)
        root.addWidget(self.sidebar)

        main = QFrame()
        main.setObjectName("clientMainPanel")
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(18, 14, 18, 18)
        main_layout.setSpacing(14)
        root.addWidget(main, 1)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        main_layout.addLayout(toolbar)

        self.new_btn = QPushButton("+ New")
        self.new_btn.setObjectName("clientNewBtn")
        self.new_btn.clicked.connect(self.toggle_add)
        toolbar.addWidget(self.new_btn)

        toolbar.addStretch(1)

        self.ws_status = QLabel("WS Offline")
        self.ws_status.setObjectName("clientWsOffline")
        self.ws_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ws_status.setMinimumWidth(86)
        self.ws_status.setMinimumHeight(36)
        toolbar.addWidget(self.ws_status)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("clientSearchInput")
        self.search_edit.setPlaceholderText("Search...")
        self.search_edit.setMaximumWidth(300)
        self.search_edit.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_edit)

        self.table = PrimeDataTable(page_size=20, row_height=58, show_footer=False)
        self.table.set_columns(
            [
                PrimeTableColumn("name", "Name", width=190),
                PrimeTableColumn("ip", "IP", width=165),
                PrimeTableColumn("port", "Port", width=90, alignment=Qt.AlignLeft | Qt.AlignVCenter),
                PrimeTableColumn("type", "Type", width=130, alignment=Qt.AlignLeft | Qt.AlignVCenter),
                PrimeTableColumn("cpu_usage", "CPU Usage", width=120, alignment=Qt.AlignLeft | Qt.AlignVCenter),
                PrimeTableColumn("memory_usage", "Memory Usage", width=135, alignment=Qt.AlignLeft | Qt.AlignVCenter),
                PrimeTableColumn("gpu_usage", "GPU Usage", width=120, alignment=Qt.AlignLeft | Qt.AlignVCenter),
                PrimeTableColumn("disk_usage", "Disk Usage", width=120, alignment=Qt.AlignLeft | Qt.AlignVCenter),
                PrimeTableColumn("status", "Status", width=110, alignment=Qt.AlignLeft | Qt.AlignVCenter),
                PrimeTableColumn(
                    "actions",
                    "Actions",
                    sortable=False,
                    searchable=False,
                    stretch=True,
                    alignment=Qt.AlignLeft | Qt.AlignVCenter,
                ),
            ]
        )
        self.table.table.horizontalHeader().setStretchLastSection(True)
        self.table.set_cell_widget_factory("type", self._type_cell_widget)
        self.table.set_cell_widget_factory("cpu_usage", lambda row: self._usage_cell_widget(row, "cpu_usage"))
        self.table.set_cell_widget_factory("memory_usage", lambda row: self._usage_cell_widget(row, "memory_usage"))
        self.table.set_cell_widget_factory("gpu_usage", lambda row: self._usage_cell_widget(row, "gpu_usage"))
        self.table.set_cell_widget_factory("disk_usage", lambda row: self._usage_cell_widget(row, "disk_usage"))
        self.table.set_cell_widget_factory("status", self._status_cell_widget)
        self.table.set_cell_widget_factory("actions", lambda row: self._action_widget(row["_client"]))
        main_layout.addWidget(self.table, 1)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget { color: #f5f7fb; }
            QFrame#clientMainPanel {
                background: #1f2024;
                border: 1px solid #2e3138;
                border-radius: 12px;
            }
            QFrame#clientSideNav {
                background: #1b1c20;
                border: 1px solid #2e3138;
                border-radius: 12px;
            }
            QToolButton#clientSideBtn, QToolButton#clientSideBtnActive {
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
            QToolButton#clientSideBtn {
                background: #23272e;
                color: #8f98a8;
                border-color: #2f3742;
            }
            QToolButton#clientSideBtn:hover {
                background: #2b3038;
                color: #f3f6fc;
                border-color: #4b5563;
            }
            QToolButton#clientSideBtnActive {
                background: #2f6ff0;
                color: white;
                border-color: #5f92ff;
            }
            QPushButton#clientNewBtn {
                background: #3b82f6;
                border: none;
                border-radius: 10px;
                color: white;
                font-size: 14px;
                font-weight: 700;
                padding: 9px 18px;
            }
            QPushButton#clientNewBtn:hover { background: #2f6ce3; }
            QPushButton#clientNewBtn:disabled {
                background: #374151;
                color: #9ca3af;
            }
            QLineEdit#clientSearchInput {
                background: #2b2e34;
                border: 1px solid #3a3e46;
                border-radius: 10px;
                color: #f5f7fb;
                padding: 9px 12px;
                font-size: 14px;
                min-height: 24px;
            }
            QLabel#clientWsOnline, QLabel#clientWsOffline {
                border-radius: 10px;
                border: 1px solid #3a3e46;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#clientWsOnline {
                background: #133127;
                border-color: #275d49;
                color: #b8f5d8;
            }
            QLabel#clientWsOffline {
                background: #3a2222;
                border-color: #6a3a3a;
                color: #ffd5d5;
            }
            """
        )

    def has_permission(self, permission: str) -> bool:
        return self.auth_store.has_permission(permission)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._ws_client.close()
        return super().closeEvent(event)

    def _on_search_changed(self, text: str) -> None:
        self.table.set_filter_text(text)

    def _poll_clients(self) -> None:
        self.client_store.load()

    def _on_ws_connection(self, connected: bool) -> None:
        self._ws_connected = connected
        self.ws_status.setObjectName("clientWsOnline" if connected else "clientWsOffline")
        self.ws_status.setText("WS Online" if connected else "WS Offline")
        self.ws_status.style().unpolish(self.ws_status)
        self.ws_status.style().polish(self.ws_status)

    def _on_usage_update(self, update: Dict[str, Any]) -> None:
        target_ids = self._resolve_target_client_ids(update)
        if not target_ids:
            return

        changed = False
        for client_id in target_ids:
            snapshot = self._usage_by_client_id.setdefault(client_id, ClientUsageSnapshot())

            cpu = update.get("cpu")
            memory = update.get("memory")
            gpu = update.get("gpu")
            disk = update.get("disk")
            online = update.get("online")

            if cpu is not None and abs(snapshot.cpu - float(cpu)) > 0.05:
                snapshot.cpu = float(cpu)
                changed = True
            if memory is not None and abs(snapshot.memory - float(memory)) > 0.05:
                snapshot.memory = float(memory)
                changed = True
            if gpu is not None and abs(snapshot.gpu - float(gpu)) > 0.05:
                snapshot.gpu = float(gpu)
                changed = True
            if disk is not None and abs(snapshot.disk - float(disk)) > 0.05:
                snapshot.disk = float(disk)
                changed = True
            if online is not None and snapshot.online != bool(online):
                snapshot.online = bool(online)
                changed = True

        if changed:
            self._populate_table()

    def _resolve_target_client_ids(self, update: Dict[str, Any]) -> set[int]:
        ids_by_id: set[int] = set()
        ids_by_endpoint: set[int] = set()
        ids_by_name: set[int] = set()
        ids_by_ip_only: set[int] = set()

        by_id = _as_int(update.get("id"), 0)
        target_ip = _normalize_ip(str(update.get("ip") or ""))
        target_port = _as_int(update.get("port"), 0)
        target_name = str(update.get("name") or "").strip().lower()

        for item in self.client_store.clients:
            if by_id and item.id == by_id:
                ids_by_id.add(item.id)
                continue
            if (
                target_ip
                and target_port > 0
                and _normalize_ip(item.ip) == target_ip
                and _as_int(item.port, 0) == target_port
            ):
                ids_by_endpoint.add(item.id)
                continue
            if target_name and item.name.strip().lower() == target_name:
                ids_by_name.add(item.id)
                continue
            if target_ip and _normalize_ip(item.ip) == target_ip:
                ids_by_ip_only.add(item.id)

        if ids_by_id:
            return ids_by_id
        if ids_by_endpoint:
            return ids_by_endpoint
        if ids_by_name:
            return ids_by_name
        if len(ids_by_ip_only) == 1:
            return ids_by_ip_only
        return set()

    def _prune_usage_cache(self) -> None:
        known_ids = {item.id for item in self.client_store.clients}
        self._usage_by_client_id = {
            client_id: usage
            for client_id, usage in self._usage_by_client_id.items()
            if client_id in known_ids
        }

    def refresh(self) -> None:
        self.new_btn.setEnabled(self.has_permission("add_client"))
        self._prune_usage_cache()
        self._populate_table()

    def _usage_snapshot(self, client_id: int) -> ClientUsageSnapshot:
        return self._usage_by_client_id.get(client_id, ClientUsageSnapshot())

    def _populate_table(self) -> None:
        rows: List[Dict[str, Any]] = []
        for item in self.client_store.clients:
            usage = self._usage_snapshot(item.id)
            rows.append(
                {
                    "name": item.name,
                    "ip": item.ip,
                    "port": int(item.port or 0),
                    "type": item.type,
                    "cpu_usage": float(usage.cpu),
                    "memory_usage": float(usage.memory),
                    "gpu_usage": float(usage.gpu),
                    "disk_usage": float(usage.disk),
                    "status": usage.online,
                    "_client": item,
                }
            )
        self.table.set_rows(rows)

    def _chip(self, text: str, bg: str, fg: str, border: str, min_width: int = 82) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumHeight(28)
        label.setMinimumWidth(min_width)
        label.setStyleSheet(
            f"background:{bg}; color:{fg}; border:1px solid {border}; border-radius:14px;"
            "padding:2px 8px; font-size:13px; font-weight:700;"
        )
        layout.addWidget(label)
        return wrapper

    def _type_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        value = str(row.get("type") or "process").strip().lower()
        if value == "record":
            return self._chip("Record", "#d7e4ff", "#1e40af", "#9eb5ff", min_width=90)
        return self._chip("Process", "#d8f8df", "#0f6a34", "#93e1a8", min_width=90)

    def _usage_cell_widget(self, row: Dict[str, Any], key: str) -> QWidget:
        value = float(row.get(key) or 0.0)
        text = _format_percent(value)
        color = "#f8fafc" if value > 0 else "#d8dee8"

        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        label.setStyleSheet(f"color:{color}; font-size:13px; font-weight:700;")
        layout.addWidget(label)
        return wrapper

    def _status_cell_widget(self, row: Dict[str, Any]) -> QWidget:
        status = row.get("status")
        if status is True:
            return self._chip("Online", "#bde9cf", "#125730", "#90d3ad", min_width=86)
        if status is False:
            return self._chip("Offline", "#f3dbdb", "#8e1b1b", "#e6b4b4", min_width=86)
        return self._chip("Unknown", "#d8dee8", "#3f4756", "#b9c2d1", min_width=86)

    def _action_button(
        self,
        svg_icon: str,
        bg: str,
        border: str,
        tooltip: str,
        size: int = 38,
    ) -> QToolButton:
        btn = QToolButton()
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(size, size)
        btn.setToolTip(tooltip)

        icon_file = _icon_path(svg_icon)
        if os.path.isfile(icon_file):
            btn.setIcon(QIcon(icon_file))
            btn.setIconSize(QSize(18, 18))

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
                background: #2f333a;
                border-color: #414751;
            }}
            """
        )
        return btn

    def _action_widget(self, client: Client) -> QWidget:
        wrapper = QWidget()
        wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        edit_btn = self._action_button("edit.svg", "#3b82f6", "#5d9bff", "Edit Client")
        edit_btn.clicked.connect(lambda: self.handle_edit(client))
        edit_btn.setEnabled(self.has_permission("edit_client"))
        layout.addWidget(edit_btn)

        delete_btn = self._action_button("trash.svg", "#ef4444", "#ff6d6d", "Delete Client")
        delete_btn.clicked.connect(lambda: self.handle_delete(client))
        delete_btn.setEnabled(self.has_permission("delete_client"))
        layout.addWidget(delete_btn)

        return wrapper

    def toggle_add(self) -> None:
        dialog = ClientFormDialog(parent=self)
        dialog.submitted.connect(self.handle_submit_form)
        dialog.exec()

    def handle_edit(self, client: Client) -> None:
        dialog = ClientFormDialog(client=client, parent=self)
        dialog.submitted.connect(self.handle_submit_form)
        dialog.exec()

    def handle_submit_form(self, payload: Dict[str, Any], is_edit: bool) -> None:
        if is_edit:
            client_id = _as_int(payload.get("id"), 0)
            if client_id <= 0:
                self._show_error("Invalid client id for update.")
                return
            self.client_store.update_client(client_id, payload)
            return
        self.client_store.add_client(payload)

    def handle_delete(self, client: Client) -> None:
        if not self.has_permission("delete_client"):
            self._show_error("You do not have permission to delete clients.")
            return

        result = QMessageBox.question(
            self,
            "Delete Client",
            f"Are you sure you want to delete '{client.name}'?",
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self.client_store.delete_client(client.id)

    def _show_info(self, text: str) -> None:
        QMessageBox.information(self, "Info", text)

    def _show_error(self, text: str) -> None:
        QMessageBox.critical(self, "Error", text)
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        p.fillPath(path, QColor(Constants.DARK_BG))   # dark bg — cards float above it
        super().paintEvent(event)
