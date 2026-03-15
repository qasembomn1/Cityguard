from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models.auth import ActivationInfo
from app.models.client import Client
from app.services.auth.auth_service import AuthService
from app.services.home.devices.client_service import ClientService
from app.store.auth import AuthStore
from app.store.home.devices.client_store import ClientStore
from app.ui.toast import PrimeToastHost
from app.views.home.devices.clients import ClientUsageWs
from app.widgets.svg_widget import SvgWidget


_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


def _normalize_ip(value: str) -> str:
    text = (value or "").strip().lower()
    if text.count(":") == 1 and "." in text:
        text = text.split(":", 1)[0]
    return text


def _parse_datetime_text(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    for candidate in (normalized, normalized.replace("T", " ")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _format_expire_text(value: str) -> str:
    parsed = _parse_datetime_text(value)
    if parsed is None:
        return value or "Unset"
    return parsed.strftime("%d %b %Y, %I:%M %p")


def _split_host_port(base_url: str) -> tuple[str, str]:
    text = str(base_url or "").strip()
    if not text:
        return "Unset", "Unset"
    parsed = urlparse(text if "://" in text else f"http://{text}")
    host = (parsed.hostname or parsed.path or "").strip() or "Unset"
    port = parsed.port
    if port is None:
        if parsed.scheme == "https":
            port = 443
        elif parsed.scheme == "http":
            port = 80
    return host, str(port) if port else "Unset"


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            _clear_layout(child_layout)


def _svg_orb(object_name: str, box_size: int, icon_size: int, svg_name: str) -> QWidget:
    orb = QFrame()
    orb.setObjectName(object_name)
    orb.setFixedSize(box_size, box_size)

    layout = QVBoxLayout(orb)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    svg_path = _icon_path(svg_name)
    if os.path.exists(svg_path):
        icon_widget = SvgWidget(svg_path, orb)
        icon_widget.setFixedSize(icon_size, icon_size)
        icon_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(icon_widget, 0, Qt.AlignmentFlag.AlignCenter)
    else:
        fallback = QLabel("A")
        fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(fallback, 0, Qt.AlignmentFlag.AlignCenter)

    return orb


class ActivationCard(QFrame):
    activate_requested = Signal(str)
    copy_requested = Signal(str)

    def __init__(
        self,
        title: str,
        badge_text: str,
        device_id: str,
        details: list[tuple[str, str]],
        online: bool,
        activated: bool,
        target_key: str,
        action_text: str,
        busy: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.busy = busy
        self.setObjectName("activationCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(226)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        root.addLayout(header)

        orb = _svg_orb("activationIconOrb", 48, 22, "activation.svg")
        header.addWidget(orb, 0, Qt.AlignmentFlag.AlignTop)

        meta = QVBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(2)
        header.addLayout(meta, 1)

        name = QLabel(title or "Unnamed")
        name.setObjectName("activationCardTitle")
        meta.addWidget(name)

        id_row = QHBoxLayout()
        id_row.setContentsMargins(0, 0, 0, 0)
        id_row.setSpacing(6)
        meta.addLayout(id_row)

        device_label = QLabel(f"Device ID: {device_id}")
        device_label.setObjectName("activationCardMeta")
        id_row.addWidget(device_label, 1)

        if device_id and device_id != "Unset":
            copy_btn = QToolButton()
            copy_btn.setObjectName("activationCopyBtn")
            copy_btn.setText("Copy")
            copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            copy_btn.clicked.connect(lambda: self.copy_requested.emit(device_id))
            id_row.addWidget(copy_btn)

        badge = QLabel(badge_text.upper())
        badge.setObjectName("activationCardBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        for label_text, value_text in details:
            line = QLabel(f"{label_text}: {value_text}")
            line.setObjectName("activationCardMeta")
            meta.addWidget(line)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(8)
        root.addLayout(status_row)

        if not online:
            status_text = "Offline"
            status_color = "#64748b"
        elif activated:
            status_text = "Activated"
            status_color = "#4ade80"
        else:
            status_text = "Inactive"
            status_color = "#f87171"

        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background:{status_color}; border-radius:5px;")
        status_row.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)

        status = QLabel(status_text)
        status.setObjectName("activationStatusText")
        status.setStyleSheet(f"color:{status_color};")
        status_row.addWidget(status, 0, Qt.AlignmentFlag.AlignVCenter)
        status_row.addStretch(1)

        action_btn = QPushButton()
        action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if not online and target_key != "server":
            action_btn.setObjectName("activationOfflineBtn")
            action_btn.setText("Offline")
            action_btn.setEnabled(False)
        else:
            action_btn.setObjectName("activationPrimaryBtn")
            if busy:
                action_btn.setText("Uploading...")
                action_btn.setEnabled(False)
            else:
                action_btn.setText(action_text)
                action_btn.clicked.connect(lambda: self.activate_requested.emit(target_key))
        root.addWidget(action_btn)


class ActivationPage(QWidget):
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
        self._busy_target: Optional[str] = None
        self._ws_connected = False

        self.auth_store.changed.connect(self._on_auth_changed)
        self.auth_store.error.connect(self._show_error)
        self.auth_store.success.connect(self._show_info)
        self.client_store.changed.connect(self._on_clients_changed)
        self.client_store.error.connect(self._show_error)

        self._build_ui()
        self.toast = PrimeToastHost(self)
        self._apply_style()

        self.auth_store.load()
        self.client_store.load()

        self._ws_client = ClientUsageWs(self)
        self._ws_client.connectionChanged.connect(self._on_ws_connection)
        self._ws_client.usageUpdate.connect(self._on_usage_update)
        self._ws_client.connect_socket()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(0)

        self.main_panel = QFrame()
        self.main_panel.setObjectName("activationMainPanel")
        main_layout = QVBoxLayout(self.main_panel)
        main_layout.setContentsMargins(28, 24, 28, 24)
        main_layout.setSpacing(18)
        root.addWidget(self.main_panel)

        title_wrap = QWidget()
        title_layout = QVBoxLayout(title_wrap)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(10)
        title_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        main_layout.addWidget(title_wrap, 0, Qt.AlignmentFlag.AlignHCenter)

        icon_orb = _svg_orb("activationCenterOrb", 88, 38, "activation.svg")
        title_layout.addWidget(icon_orb, 0, Qt.AlignmentFlag.AlignHCenter)

        title = QLabel("Activation Management")
        title.setObjectName("activationPageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(title)

        subtitle = QLabel(
            "Upload activation keys for the server and connected clients from one page."
        )
        subtitle.setObjectName("activationPageSubtitle")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(subtitle)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 10, 0, 0)
        actions.setSpacing(10)
        actions.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title_layout.addLayout(actions)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("activationGhostBtn")
        self.refresh_btn.clicked.connect(self._reload_all)
        actions.addWidget(self.refresh_btn)

        self.ws_status = QLabel("WS Offline")
        self.ws_status.setObjectName("activationWsOffline")
        self.ws_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ws_status.setMinimumWidth(104)
        self.ws_status.setMinimumHeight(34)
        actions.addWidget(self.ws_status)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        main_layout.addWidget(self.scroll, 1)

        scroll_body = QWidget()
        scroll_layout = QVBoxLayout(scroll_body)
        scroll_layout.setContentsMargins(0, 8, 0, 0)
        scroll_layout.setSpacing(0)

        self.cards_host = QWidget()
        self.cards_host.setMaximumWidth(1360)
        self.cards_layout = QGridLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setHorizontalSpacing(14)
        self.cards_layout.setVerticalSpacing(14)
        scroll_layout.addWidget(
            self.cards_host,
            0,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
        )
        scroll_layout.addStretch(1)
        self.scroll.setWidget(scroll_body)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                color: #f5f7fb;
            }
            QFrame#activationMainPanel {
                background: #171b22;
                border: 1px solid #2b3240;
                border-radius: 22px;
            }
            QFrame#activationCenterOrb, QFrame#activationIconOrb {
                background: rgba(255, 255, 255, 0.96);
                border-radius: 24px;
                color: #0f1726;
            }
            QFrame#activationCenterOrb {
                border-radius: 44px;
            }
            QLabel#activationPageTitle {
                color: #f8fbff;
                font-size: 22px;
                font-weight: 900;
            }
            QLabel#activationPageSubtitle {
                color: #aab4c2;
                font-size: 13px;
                max-width: 520px;
            }
            QPushButton#activationGhostBtn {
                background: #252a34;
                border: 1px solid #3b4352;
                border-radius: 12px;
                color: #f2f6ff;
                font-weight: 700;
                padding: 10px 18px;
            }
            QPushButton#activationGhostBtn:hover {
                background: #2d3644;
            }
            QLabel#activationWsOnline, QLabel#activationWsOffline {
                border-radius: 12px;
                font-size: 12px;
                font-weight: 800;
                padding: 0 12px;
            }
            QLabel#activationWsOnline {
                background: rgba(74, 222, 128, 0.14);
                border: 1px solid rgba(74, 222, 128, 0.24);
                color: #86efac;
            }
            QLabel#activationWsOffline {
                background: rgba(148, 163, 184, 0.16);
                border: 1px solid rgba(148, 163, 184, 0.28);
                color: #cbd5e1;
            }
            QFrame#activationCard {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #2a2d31,
                    stop: 0.55 #1d2025,
                    stop: 1 #050608
                );
                border: 1px solid #2e3746;
                border-radius: 24px;
            }
            QFrame#activationCard:hover {
                border-color: #4b78f2;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #303745,
                    stop: 0.55 #232834,
                    stop: 1 #090b10
                );
            }
            QLabel#activationCardTitle {
                color: #f8fbff;
                font-size: 18px;
                font-weight: 900;
            }
            QLabel#activationCardMeta {
                color: #9aa6b7;
                font-size: 12px;
            }
            QLabel#activationStatusText {
                font-size: 13px;
                font-weight: 800;
            }
            QLabel#activationCardBadge {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 11px;
                color: #e2e8f0;
                font-size: 10px;
                font-weight: 800;
                min-width: 58px;
                min-height: 22px;
                padding: 0 8px;
            }
            QToolButton#activationCopyBtn {
                background: #27303d;
                border: 1px solid #3d4756;
                border-radius: 7px;
                color: #e2e8f0;
                min-width: 46px;
                max-width: 46px;
                min-height: 24px;
                max-height: 24px;
                font-size: 11px;
                font-weight: 700;
            }
            QToolButton#activationCopyBtn:hover {
                background: #334052;
            }
            QPushButton#activationPrimaryBtn, QPushButton#activationOfflineBtn {
                min-height: 42px;
                border-radius: 18px;
                font-size: 14px;
                font-weight: 800;
            }
            QPushButton#activationPrimaryBtn {
                background: #2563eb;
                border: none;
                color: white;
            }
            QPushButton#activationPrimaryBtn:hover {
                background: #1d4ed8;
            }
            QPushButton#activationOfflineBtn {
                background: #312229;
                border: 1px solid #6f3a48;
                color: #fecaca;
            }
            QLabel#activationEmptyTitle {
                color: #f8fbff;
                font-size: 22px;
                font-weight: 900;
            }
            QLabel#activationEmptyHint {
                color: #94a3b8;
                font-size: 13px;
            }
            QScrollArea, QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 6px 0;
            }
            QScrollBar::handle:vertical {
                background: #475569;
                border-radius: 5px;
                min-height: 26px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            """
        )

    def _client_columns(self) -> int:
        width = self.cards_host.width() if self.cards_host is not None else self.width()
        if width >= 1180:
            return 3
        if width >= 760:
            return 2
        return 1

    def _update_cards_host_width(self) -> None:
        if self.scroll is None:
            return
        available = max(320, self.scroll.viewport().width() - 6)
        self.cards_host.setFixedWidth(min(1360, available))

    def _card_width(self, columns: int) -> int:
        spacing = max(0, self.cards_layout.horizontalSpacing())
        total_spacing = spacing * max(0, columns - 1)
        available = max(280, self.cards_host.width() - total_spacing)
        return max(280, available // max(1, columns))

    def _sorted_clients(self) -> list[Client]:
        def sort_key(item: Client) -> tuple[float, str]:
            expires = _parse_datetime_text(item.expire_date)
            timestamp = expires.timestamp() if expires is not None else 0.0
            return (timestamp, (item.name or "").lower())

        return sorted(self.client_store.clients, key=sort_key, reverse=True)

    def _server_card_config(self) -> dict[str, Any]:
        info = self.auth_store.server_activation_info or ActivationInfo()
        base_url = getattr(self.auth_store.service.api, "base_url", "")
        host, port = _split_host_port(base_url)
        return {
            "title": "Cityguard Server",
            "badge_text": "Server",
            "device_id": info.device_id or "Unset",
            "details": [
                ("Server IP", host),
                ("Port", port),
                ("Camera Limit", str(info.camera_limit) if int(info.camera_limit or -1) >= 0 else "Unset"),
                ("Expires At", _format_expire_text(info.expire_date)),
            ],
            "online": self.auth_store.server_activation_info is not None,
            "activated": bool(info.activated),
            "target_key": "server",
            "action_text": "Update Activation" if info.activated else "Activate Server",
            "busy": self._busy_target == "server",
        }

    def _client_card_config(self, client: Client) -> dict[str, Any]:
        return {
            "title": client.name or "Unnamed Client",
            "badge_text": "Client",
            "device_id": client.device_id or "Unset",
            "details": [
                ("Server IP", client.server_address or "Unset"),
                ("Client IP", client.ip or "Unset"),
                ("Port", str(int(client.port or 0)) if int(client.port or 0) > 0 else "Unset"),
                ("Camera Limit", str(client.camera_limit) if int(client.camera_limit or -1) >= 0 else "Unset"),
                ("Expires At", _format_expire_text(client.expire_date)),
            ],
            "online": bool(client.online),
            "activated": bool(client.activated),
            "target_key": f"client:{client.id}",
            "action_text": "Update Activation" if client.activated else "Activate",
            "busy": self._busy_target == f"client:{client.id}",
        }

    def _merge_activation(self, client: Client, info: Optional[ActivationInfo]) -> None:
        if info is None:
            client.device_id = ""
            client.server_address = ""
            client.camera_limit = -1
            client.expire_date = ""
            client.activated = False
            return
        client.device_id = info.device_id
        client.server_address = info.server_address
        client.camera_limit = info.camera_limit
        client.expire_date = info.expire_date
        client.activated = info.activated

    def _apply_cached_activation(self) -> None:
        cache = self.auth_store.client_activation_info
        for client in self.client_store.clients:
            self._merge_activation(client, cache.get(int(client.id)))

    def _reload_all(self) -> None:
        self.auth_store.load()
        self.client_store.load()

    def _load_client_activation_info(self) -> None:
        if not self.client_store.clients:
            self.refresh()
            return
        self.auth_store.load_client_activation_infos(self.client_store.clients)
        self._apply_cached_activation()
        self.refresh()

    def _on_auth_changed(self) -> None:
        self._apply_cached_activation()
        self.refresh()

    def _on_clients_changed(self) -> None:
        self._apply_cached_activation()
        if not self.client_store.clients:
            self.refresh()
            return
        self._load_client_activation_info()

    def _on_ws_connection(self, connected: bool) -> None:
        self._ws_connected = connected
        self.ws_status.setText("WS Online" if connected else "WS Offline")
        self.ws_status.setObjectName("activationWsOnline" if connected else "activationWsOffline")
        self.ws_status.style().unpolish(self.ws_status)
        self.ws_status.style().polish(self.ws_status)

    def _on_usage_update(self, update: dict) -> None:
        client_id = int(update.get("id") or 0)
        target_ip = _normalize_ip(str(update.get("ip") or ""))
        target_port = int(update.get("port") or 0)
        online_value = update.get("online")
        if online_value is None:
            return

        matched = False
        for client in self.client_store.clients:
            same_id = client_id > 0 and int(client.id) == client_id
            same_ip = bool(target_ip) and _normalize_ip(client.ip) == target_ip
            same_port = not target_port or int(client.port or 0) == target_port
            if same_id or (same_ip and same_port):
                client.online = bool(online_value)
                matched = True
        if matched:
            self.refresh()

    def _copy_device_id(self, device_id: str) -> None:
        text = str(device_id or "").strip()
        if not text:
            self._toast_warn("Missing", "Device ID is missing.")
            return
        QApplication.clipboard().setText(text)
        self._toast_success("Copied", "Device ID copied to clipboard.")

    def _activate_server(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Server Activation Key",
            "",
            "Activation Key (*.dat);;All Files (*)",
        )
        if not path:
            return

        self._busy_target = "server"
        self.refresh()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.auth_store.activate_server(path)
        finally:
            QApplication.restoreOverrideCursor()
            self._busy_target = None
            self.refresh()

    def _activate_client(self, client_id: int) -> None:
        client = next((item for item in self.client_store.clients if int(item.id) == int(client_id)), None)
        if client is None:
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Activation Key",
            "",
            "Activation Key (*.dat);;All Files (*)",
        )
        if not path:
            return

        self._busy_target = f"client:{client.id}"
        self.refresh()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            info = self.auth_store.activate_client(client, path)
            self._merge_activation(client, info)
        finally:
            QApplication.restoreOverrideCursor()
            self._busy_target = None
            self.refresh()

    def _handle_activation_request(self, target_key: str) -> None:
        if target_key == "server":
            self._activate_server()
            return
        if target_key.startswith("client:"):
            try:
                self._activate_client(int(target_key.split(":", 1)[1]))
            except ValueError:
                return

    def refresh(self) -> None:
        self._apply_cached_activation()
        self._update_cards_host_width()
        clients = self._sorted_clients()
        _clear_layout(self.cards_layout)
        columns = self._client_columns()
        card_width = self._card_width(columns)
        cards = [self._server_card_config()]
        cards.extend(self._client_card_config(client) for client in clients)

        for index, card_config in enumerate(cards):
            card = ActivationCard(parent=self.cards_host, **card_config)
            card.setFixedWidth(card_width)
            card.activate_requested.connect(self._handle_activation_request)
            card.copy_requested.connect(self._copy_device_id)
            row = index // columns
            col = index % columns
            self.cards_layout.addWidget(
                card,
                row,
                col,
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
            )

        for col in range(columns):
            self.cards_layout.setColumnStretch(col, 1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.refresh()

    def closeEvent(self, event) -> None:
        try:
            self._ws_client.close()
        except Exception:
            pass
        super().closeEvent(event)

    def _toast_warn(self, summary: str, detail: str = "", life: int = 3600) -> None:
        if hasattr(self, "toast"):
            self.toast.warn(summary, detail, life)

    def _toast_error(self, summary: str, detail: str = "", life: int = 4200) -> None:
        if hasattr(self, "toast"):
            self.toast.error(summary, detail, life)

    def _toast_success(self, summary: str, detail: str = "", life: int = 3200) -> None:
        if hasattr(self, "toast"):
            self.toast.success(summary, detail, life)

    def _show_info(self, text: str) -> None:
        self._toast_success("Success", text)

    def _show_error(self, text: str) -> None:
        self._toast_error("Error", text)


class MainWindow(QMainWindow):
    navigate = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Activation Management")
        self.resize(1440, 900)
        page = ActivationPage()
        page.navigate.connect(self.navigate.emit)
        self.setCentralWidget(page)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
