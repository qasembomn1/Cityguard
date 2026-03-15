from __future__ import annotations

import os
import sys
import urllib.parse
from datetime import datetime
from typing import Dict, List, Optional

from PySide6.QtCore import QDate, QDateTime, QSize, Qt, QTime, QUrl, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models.lpr.repeated import LprRepeatedPayload, LprRepeatedResult
from app.models.lpr.search import LprSearchResult
from app.services.auth.auth_service import AuthService
from app.services.home.devices.camera_service import CameraService
from app.services.home.lpr.repeated_service import LprRepeatedService
from app.services.home.lpr.search_service import LprSearchService
from app.store.auth.auth_store import AuthStore
from app.store.home.lpr.repeated_store import LprRepeatedStore
from app.store.home.lpr.search_store import LprSearchStore
from app.store.home.user.department_store import DepartmentStore as CameraDepartmentStore
from app.ui.button import PrimeButton
from app.ui.multiselect import PrimeMultiSelect
from app.ui.table import PrimeDataTable, PrimeTableColumn
from app.ui.toast import PrimeToastHost
from app.utils.digits import normalize_ascii_digits


_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


def _base_http_url() -> str:
    raw = os.getenv("Base_URL", "http://192.168.100.120:8800").strip().rstrip("/")
    if raw.startswith(("http://", "https://")):
        return raw
    return f"http://{raw}"


def _record_image_url(record: LprSearchResult, crop: bool = False) -> str:
    camera_id = int(record.camera_id or 0)
    filename = os.path.basename(str(record.filename or "").strip())
    if camera_id <= 0 or not filename:
        return ""

    suffix = f"crop_{filename}" if crop else filename
    encoded = urllib.parse.quote(suffix)
    if record.ip and int(record.port or 0) > 0:
        return f"http://{record.ip}:{int(record.port)}/image/{camera_id}/{encoded}"
    return f"{_base_http_url()}/image/{camera_id}/{encoded}"


class RemoteImageLabel(QLabel):
    def __init__(
        self,
        net: QNetworkAccessManager,
        fallback_text: str = "No Image",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._net = net
        self._reply: Optional[QNetworkReply] = None
        self._original = QPixmap()
        self._image_url = ""
        self._fallback_text = fallback_text
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(self._fallback_text)
        self.setScaledContents(False)

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

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if self._reply is None and self._original.isNull() and self._image_url:
            self._start_request()

    def hideEvent(self, event) -> None:  # type: ignore[override]
        super().hideEvent(event)
        if self._reply is not None:
            self._abort_reply()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._apply_scaled()

    def _start_request(self) -> None:
        if not self._image_url:
            return
        request = QNetworkRequest(QUrl(self._image_url))
        request.setRawHeader(b"Accept", b"image/*")
        self._reply = self._net.get(request)
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
        self.setPixmap(
            self._original.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.setText("")


class FilterDateTimeField(QFrame):
    def __init__(self, placeholder: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("repeatedDateField")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        self.edit = QDateTimeEdit()
        self.edit.setCalendarPopup(True)
        self.edit.setDisplayFormat("yyyy-MM-dd hh:mm AP")
        self.edit.setSpecialValueText(placeholder)
        self.edit.setDateTime(QDateTime.currentDateTime())
        self.edit.setMinimumDateTime(QDateTime.fromSecsSinceEpoch(0))
        self.edit.setObjectName("repeatedDateEdit")
        self.edit.dateTimeChanged.connect(self._mark_has_value)
        layout.addWidget(self.edit, 1)

        clear_btn = QToolButton()
        clear_btn.setObjectName("repeatedDateClear")
        clear_btn.setIcon(QIcon(_icon_path("close.svg")))
        clear_btn.setIconSize(QSize(14, 14))
        clear_btn.setToolTip("Clear")
        clear_btn.clicked.connect(self.clear)
        layout.addWidget(clear_btn)

        self._has_value = False
        self.clear()

    def value(self) -> Optional[datetime]:
        if not self._has_value:
            return None
        return self.edit.dateTime().toPython()

    def set_value(self, value: Optional[datetime]) -> None:
        if value is None:
            self.clear()
            return
        self.edit.blockSignals(True)
        self._has_value = True
        self.edit.setDateTime(
            QDateTime(
                QDate(value.year, value.month, value.day),
                QTime(value.hour, value.minute, value.second),
            )
        )
        self.edit.blockSignals(False)
        self.edit.setStyleSheet("")

    def clear(self) -> None:
        self.edit.blockSignals(True)
        self._has_value = False
        self.edit.setDateTime(QDateTime.currentDateTime())
        self.edit.blockSignals(False)
        self.edit.setStyleSheet("color: #93a1b6;")

    def _mark_has_value(self) -> None:
        self._has_value = True
        self.edit.setStyleSheet("")


class RepeatedDetailDialog(QDialog):
    def __init__(self, net: QNetworkAccessManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._net = net
        self._records: List[LprSearchResult] = []
        self._index = 0
        self.setWindowTitle("Repeated Details")
        self.resize(1120, 680)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        self.summary_label = QLabel("Plate: -")
        self.summary_label.setObjectName("repeatedDetailSummary")
        root.addWidget(self.summary_label)

        body = QGridLayout()
        body.setHorizontalSpacing(16)
        body.setVerticalSpacing(16)
        body.setColumnStretch(0, 2)
        body.setColumnStretch(1, 1)
        root.addLayout(body, 1)

        frame_card = QFrame()
        frame_card.setObjectName("repeatedDetailImageCard")
        frame_layout = QVBoxLayout(frame_card)
        frame_layout.setContentsMargins(14, 14, 14, 14)
        frame_layout.setSpacing(10)
        frame_title = QLabel("Full Camera Frame")
        frame_title.setObjectName("repeatedDetailCardTitle")
        frame_layout.addWidget(frame_title)

        self.frame_image_label = RemoteImageLabel(self._net, "No Frame")
        self.frame_image_label.setMinimumSize(520, 360)
        self.frame_image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.frame_image_label.setStyleSheet(
            "background:#090d12; border:1px solid #1f2937; border-radius:14px; color:#64748b;"
        )
        frame_layout.addWidget(self.frame_image_label, 1)
        body.addWidget(frame_card, 0, 0, 2, 1)

        crop_card = QFrame()
        crop_card.setObjectName("repeatedDetailImageCard")
        crop_layout = QVBoxLayout(crop_card)
        crop_layout.setContentsMargins(14, 14, 14, 14)
        crop_layout.setSpacing(10)
        crop_title = QLabel("License Plate Crop")
        crop_title.setObjectName("repeatedDetailCardTitle")
        crop_layout.addWidget(crop_title)

        self.crop_image_label = RemoteImageLabel(self._net, "No Plate Crop")
        self.crop_image_label.setMinimumHeight(220)
        self.crop_image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.crop_image_label.setStyleSheet(
            "background:#090d12; border:1px solid #1f2937; border-radius:14px; color:#64748b;"
        )
        crop_layout.addWidget(self.crop_image_label, 1)
        body.addWidget(crop_card, 0, 1, 1, 1)

        info_card = QFrame()
        info_card.setObjectName("repeatedDetailCard")
        body.addWidget(info_card, 1, 1, 1, 1)

        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(18, 18, 18, 18)
        info_layout.setSpacing(14)

        self.plate_label = QLabel("-")
        self.plate_label.setObjectName("repeatedDetailPlate")
        info_layout.addWidget(self.plate_label)

        self.region_label = QLabel("Region: -")
        self.conf_label = QLabel("Confidence: -")
        self.camera_label = QLabel("Camera: -")
        self.note_label = QLabel("Note: -")
        self.date_label = QLabel("Date: -")
        self.empty_label = QLabel("No records found for this repeated plate.")
        self.empty_label.setObjectName("repeatedDetailEmpty")
        self.empty_label.setWordWrap(True)

        for field in (
            self.region_label,
            self.conf_label,
            self.camera_label,
            self.note_label,
            self.date_label,
        ):
            field.setObjectName("repeatedDetailField")
            field.setWordWrap(True)
            info_layout.addWidget(field)
        info_layout.addWidget(self.empty_label)

        info_layout.addStretch(1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        root.addLayout(footer)

        self.position_label = QLabel("Record 0 of 0")
        self.position_label.setObjectName("repeatedDetailMeta")
        footer.addWidget(self.position_label)

        footer.addStretch(1)

        self.prev_btn = QPushButton("Prev")
        self.prev_btn.clicked.connect(self._show_prev)
        footer.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self._show_next)
        footer.addWidget(self.next_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)

        self.setStyleSheet(
            """
            QDialog {
                background: #171b21;
                color: #eef2f8;
            }
            QLabel#repeatedDetailSummary {
                color: #f8fafc;
                font-size: 16px;
                font-weight: 700;
            }
            QFrame#repeatedDetailImageCard,
            QFrame#repeatedDetailCard {
                background: #11161d;
                border: 1px solid #293241;
                border-radius: 16px;
            }
            QLabel#repeatedDetailCardTitle {
                color: #f8fafc;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#repeatedDetailPlate {
                color: #60a5fa;
                font-size: 24px;
                font-weight: 800;
            }
            QLabel#repeatedDetailField {
                color: #dbe3ef;
                font-size: 13px;
            }
            QLabel#repeatedDetailMeta {
                color: #93a1b6;
                font-size: 12px;
            }
            QLabel#repeatedDetailEmpty {
                color: #f59e0b;
                font-size: 13px;
            }
            QPushButton {
                background: #2b3340;
                border: 1px solid #425062;
                border-radius: 8px;
                color: #f8fafc;
                padding: 7px 14px;
                font-weight: 600;
                min-height: 18px;
            }
            QPushButton:hover {
                background: #35507f;
                border-color: #4d76bb;
            }
            QPushButton:disabled {
                background: #20242b;
                color: #7f8a99;
                border-color: #313844;
            }
            """
        )

    def set_data(self, repeated: LprRepeatedResult, records: List[LprSearchResult]) -> None:
        self._records = list(records)
        self._index = 0
        self.summary_label.setText(
            f"Plate: {repeated.number or '-'} | Repeated Number: {repeated.count_text} | Total Results: {len(self._records)}"
        )
        self._render_current()

    def _show_prev(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._render_current()

    def _show_next(self) -> None:
        if self._index + 1 < len(self._records):
            self._index += 1
            self._render_current()

    def _render_current(self) -> None:
        total = len(self._records)
        has_records = total > 0
        self.prev_btn.setEnabled(has_records and self._index > 0)
        self.next_btn.setEnabled(has_records and self._index + 1 < total)
        self.position_label.setText(f"Record {self._index + 1 if has_records else 0} of {total}")
        self.empty_label.setVisible(not has_records)

        if not has_records:
            self.plate_label.setText("-")
            self.region_label.setText("Region: -")
            self.conf_label.setText("Confidence: -")
            self.camera_label.setText("Camera: -")
            self.note_label.setText("Note: -")
            self.date_label.setText("Date: -")
            self.frame_image_label.set_image_url("")
            self.crop_image_label.set_image_url("")
            return

        record = self._records[self._index]
        self.plate_label.setText(record.number or "Unknown Plate")
        self.region_label.setText(f"Region: {record.region or 'Unknown'}")
        self.conf_label.setText(f"Confidence: {record.confidence_text}")
        self.camera_label.setText(f"Camera: {record.camera_name or 'N/A'}")
        self.note_label.setText(f"Note: {record.note or 'None'}")
        self.date_label.setText(f"Date: {record.created_text}")
        self.frame_image_label.set_image_url(_record_image_url(record, crop=False))
        self.crop_image_label.set_image_url(_record_image_url(record, crop=True))


class LprRepeatedPage(QWidget):
    navigate = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.toast = PrimeToastHost(self)
        self.net = QNetworkAccessManager(self)

        self.auth_store = AuthStore(AuthService())
        self.camera_store = CameraDepartmentStore(CameraService())
        self.repeated_store = LprRepeatedStore(LprRepeatedService())
        self.search_store = LprSearchStore(LprSearchService())

        self._loaded_department_id: Optional[int] = None
        self.filters_window_visible = True
        self.has_searched = False

        self.auth_store.changed.connect(self.refresh)
        self.auth_store.error.connect(self._show_error)
        self.camera_store.changed.connect(self.refresh)
        self.camera_store.error.connect(self._show_error)
        self.repeated_store.changed.connect(self.refresh)
        self.repeated_store.error.connect(self._show_error)
        self.search_store.error.connect(self._show_error)

        self._build_ui()
        self._apply_style()

        self.auth_store.load()
        self.camera_store.get_camera_for_user(None, silent=True)
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.content_panel = QFrame()
        self.content_panel.setObjectName("repeatedContentPanel")
        root.addWidget(self.content_panel, 1)

        content = QVBoxLayout(self.content_panel)
        content.setContentsMargins(18, 18, 18, 18)
        content.setSpacing(12)

        self.hero_scroll = QScrollArea()
        self.hero_scroll.setObjectName("repeatedFiltersScroll")
        self.hero_scroll.setWidgetResizable(True)
        self.hero_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.hero_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.hero_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.hero_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.hero_scroll.setMinimumHeight(0)
        content.addWidget(self.hero_scroll)

        hero_frame = QFrame()
        hero_frame.setObjectName("repeatedHero")
        self.hero_frame = hero_frame
        hero = QVBoxLayout(hero_frame)
        hero.setContentsMargins(18, 18, 18, 18)
        hero.setSpacing(14)
        self.hero_scroll.setWidget(hero_frame)

        hero_head = QHBoxLayout()
        hero_head.setContentsMargins(0, 0, 0, 0)
        hero_head.setSpacing(8)
        hero.addLayout(hero_head)

        hero_text = QVBoxLayout()
        hero_text.setContentsMargins(0, 0, 0, 0)
        hero_text.setSpacing(4)
        hero_head.addLayout(hero_text, 1)

        hero_title = QLabel("LPR Repeated Window")
        hero_title.setObjectName("heroTitle")
        hero_text.addWidget(hero_title)

        hero_hint = QLabel("Search repeated license plates by time range, threshold, and selected cameras. Use the filter panel only when you need it.")
        hero_hint.setObjectName("heroHint")
        hero_hint.setWordWrap(True)
        hero_text.addWidget(hero_hint)

        self.filter_state_chip = QLabel("Filters visible")
        self.filter_state_chip.setObjectName("heroChip")
        hero_head.addWidget(self.filter_state_chip, 0, Qt.AlignmentFlag.AlignTop)

        fields_grid = QGridLayout()
        fields_grid.setContentsMargins(0, 0, 0, 0)
        fields_grid.setHorizontalSpacing(12)
        fields_grid.setVerticalSpacing(12)
        fields_grid.setColumnStretch(0, 1)
        fields_grid.setColumnStretch(1, 1)
        hero.addLayout(fields_grid)

        self.date_from_field = FilterDateTimeField("Start Time")
        fields_grid.addWidget(
            self._hero_field_block(
                "Start Date & Time",
                self.date_from_field,
                "Search from this timestamp.",
            ),
            0,
            0,
        )

        self.date_to_field = FilterDateTimeField("End Time")
        fields_grid.addWidget(
            self._hero_field_block(
                "End Date & Time",
                self.date_to_field,
                "Search until this timestamp.",
            ),
            0,
            1,
        )

        self.repeated_spin = QSpinBox()
        self.repeated_spin.setRange(1, 9999)
        self.repeated_spin.setValue(2)
        fields_grid.addWidget(
            self._hero_field_block(
                "Repeated Number",
                self.repeated_spin,
                "Minimum repeated hits required for a plate.",
            ),
            1,
            0,
        )

        self.camera_select = PrimeMultiSelect(options=[], placeholder="Select Camera")
        self.camera_select.setMinimumWidth(0)
        self.camera_select.setMaximumWidth(16777215)
        self.camera_select.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        fields_grid.addWidget(
            self._hero_field_block(
                "Camera",
                self.camera_select,
                "Limit repeated search to selected cameras.",
            ),
            1,
            1,
        )

        hero_actions = QHBoxLayout()
        hero_actions.setContentsMargins(0, 0, 0, 0)
        hero_actions.setSpacing(10)
        hero.addLayout(hero_actions)

        self.filter_toggle_btn = QPushButton("Hide Filters")
        self.filter_toggle_btn.setObjectName("filterToggleButton")
        self.filter_toggle_btn.clicked.connect(self.toggle_filters_window)
        hero_actions.addWidget(self.filter_toggle_btn)

        self.reset_btn = QPushButton("Reset Filters")
        self.reset_btn.setObjectName("secondarySidebarButton")
        self.reset_btn.clicked.connect(self.reset_filters)
        hero_actions.addWidget(self.reset_btn)

        self.search_btn = QPushButton("Search Records")
        self.search_btn.setObjectName("primarySidebarButton")
        self.search_btn.clicked.connect(self.perform_search)
        hero_actions.addWidget(self.search_btn)

        hero_actions.addStretch(1)

        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("repeatedToolbar")
        toolbar = QHBoxLayout(toolbar_frame)
        toolbar.setContentsMargins(14, 14, 14, 14)
        toolbar.setSpacing(10)
        content.addWidget(toolbar_frame)

        left_cluster = QVBoxLayout()
        left_cluster.setContentsMargins(0, 0, 0, 0)
        left_cluster.setSpacing(3)
        self.page_title = QLabel("LPR Repeated Results")
        self.page_title.setObjectName("pageTitle")
        self.status_label = QLabel("Adjust filters and run a repeated search.")
        self.status_label.setObjectName("pageSummary")
        left_cluster.addWidget(self.page_title)
        left_cluster.addWidget(self.status_label)
        toolbar.addLayout(left_cluster, 1)

        self.results_filter_btn = QPushButton("Hide Filters")
        self.results_filter_btn.setObjectName("filterToggleButton")
        self.results_filter_btn.clicked.connect(self.toggle_filters_window)
        toolbar.addWidget(self.results_filter_btn)

        self.goto_page_edit = QLineEdit()
        self.goto_page_edit.setPlaceholderText("Goto Page...")
        self.goto_page_edit.setFixedWidth(120)
        self.goto_page_edit.textEdited.connect(self._normalize_page_digits)
        toolbar.addWidget(self.goto_page_edit)

        self.goto_btn = PrimeButton("Goto", variant="primary", size="sm")
        self.goto_btn.clicked.connect(self.goto_page)
        toolbar.addWidget(self.goto_btn)

        self.prev_btn = PrimeButton("Prev", variant="secondary", size="sm")
        self.prev_btn.clicked.connect(self.goto_prev_page)
        toolbar.addWidget(self.prev_btn)

        self.next_btn = PrimeButton("Next", variant="secondary", size="sm")
        self.next_btn.clicked.connect(self.goto_next_page)
        toolbar.addWidget(self.next_btn)

        self.page_meta = QLabel("0-0 of 0")
        self.page_meta.setObjectName("repeatedMeta")
        toolbar.addWidget(self.page_meta)

        toolbar.addStretch(1)

        self.rows_combo = QComboBox()
        for size in (10, 20, 50, 100, 200):
            self.rows_combo.addItem(f"{size} Rows", size)
        self.rows_combo.setCurrentIndex(2)
        self.rows_combo.currentIndexChanged.connect(self._on_rows_changed)
        toolbar.addWidget(self.rows_combo)

        self.table = PrimeDataTable(page_size=50, page_size_options=[10, 20, 50, 100, 200], row_height=48, show_footer=False)
        self.table.set_columns(
            [
                PrimeTableColumn("number", "Plate Number", stretch=True),
                PrimeTableColumn("color", "Plate Color", stretch=True),
                PrimeTableColumn("plate_type", "Plate Type", stretch=True),
                PrimeTableColumn("region", "Region", stretch=True),
                PrimeTableColumn("count", "Repeated Number", stretch=True),
            ]
        )
        self.table.row_clicked.connect(self.open_repeated_details)
        self.table.page_changed.connect(self._sync_page_state)
        content.addWidget(self.table, 1)

        self._sync_filters_window_ui()
        self._update_filters_scroll_height()

    def _time_range_widget(self) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.date_from_field = FilterDateTimeField("Start Time")
        layout.addWidget(self.date_from_field, 1)

        self.date_to_field = FilterDateTimeField("End Time")
        layout.addWidget(self.date_to_field, 1)
        return wrapper

    def _field_block(self, label_text: str, field: QWidget) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label = QLabel(label_text)
        label.setObjectName("repeatedFieldLabel")
        layout.addWidget(label)
        layout.addWidget(field)
        return wrapper

    def _hero_field_block(self, label_text: str, field: QWidget, hint_text: str) -> QWidget:
        wrapper = QWidget()
        wrapper.setObjectName("heroFieldBlock")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label = QLabel(label_text)
        label.setObjectName("heroFieldLabel")
        layout.addWidget(label)
        layout.addWidget(field)

        hint = QLabel(hint_text)
        hint.setObjectName("heroFieldHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return wrapper

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                color: #eef2f8;
            }
            QFrame#repeatedContentPanel {
                background: #171b21;
                border: 1px solid #2b3340;
                border-radius: 16px;
            }
            QFrame#repeatedHero {
                background: #151920;
                border: 1px solid #2a3140;
                border-radius: 16px;
            }
            QFrame#repeatedToolbar {
                background: #151920;
                border: 1px solid #2a3140;
                border-radius: 14px;
            }
            QLabel#heroTitle {
                color: #f8fafc;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#heroHint {
                color: #93a1b6;
                font-size: 13px;
            }
            QLabel#heroChip {
                padding: 6px 12px;
                border-radius: 999px;
                background: rgba(59, 130, 246, 0.18);
                border: 1px solid rgba(96, 165, 250, 0.35);
                color: #dbeafe;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#pageTitle {
                color: #f8fafc;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#pageSummary,
            QLabel#repeatedFieldLabel {
                color: #93a1b6;
                font-size: 13px;
            }
            QLabel#heroFieldLabel {
                color: #dbe3ef;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#heroFieldHint {
                color: #93a1b6;
                font-size: 11px;
            }
            QLabel#repeatedMeta {
                color: #93a1b6;
                font-size: 12px;
            }
            QFrame#repeatedDateField {
                background: #242a33;
                border: 1px solid #364150;
                border-radius: 10px;
            }
            QDateTimeEdit#repeatedDateEdit,
            QSpinBox,
            QLineEdit,
            QComboBox {
                background: #242a33;
                border: 1px solid #364150;
                border-radius: 10px;
                color: #eef2f8;
                padding: 8px 10px;
                min-height: 24px;
            }
            QToolButton#repeatedDateClear {
                background: transparent;
                border: none;
                padding: 0 8px;
            }
            QWidget#heroFieldBlock {
                background: #11161d;
                border: 1px solid #293241;
                border-radius: 14px;
                padding: 2px;
            }
            QPushButton#primarySidebarButton {
                background: #2563eb;
                color: #ffffff;
                border: 1px solid #2563eb;
                border-radius: 10px;
                padding: 8px 14px;
                font-weight: 700;
                min-height: 18px;
            }
            QPushButton#primarySidebarButton:hover {
                background: #1d4ed8;
                border-color: #1d4ed8;
            }
            QPushButton#secondarySidebarButton,
            QPushButton#filterToggleButton {
                background: #2b3340;
                color: #eef2f8;
                border: 1px solid #425062;
                border-radius: 10px;
                padding: 8px 14px;
                font-weight: 600;
                min-height: 18px;
            }
            QPushButton#secondarySidebarButton:hover,
            QPushButton#filterToggleButton:hover {
                background: #35507f;
                border-color: #4d76bb;
            }
            """
        )

    def _camera_options(self) -> List[dict]:
        options: List[dict] = []
        for camera in self.camera_store.cameras:
            label = camera.name or f"Camera #{camera.id}"
            options.append({"label": label, "value": camera.id})
        return options

    def _rows(self) -> List[Dict[str, object]]:
        rows: List[Dict[str, object]] = []
        for item in self.repeated_store.results:
            rows.append(
                {
                    "number": item.number or "Unset",
                    "color": item.color or "Unset",
                    "plate_type": item.plate_type or "Unset",
                    "region": item.region or "Unset",
                    "count": item.count_text,
                    "_entry": item,
                }
            )
        return rows

    def refresh(self) -> None:
        current_user = self.auth_store.current_user
        department_id = current_user.department_id if current_user is not None else None
        if department_id != self._loaded_department_id:
            self._loaded_department_id = department_id
            self.camera_store.get_camera_for_user(department_id, silent=True)

        self.camera_select.set_options(self._camera_options())
        self.table.set_rows(self._rows())
        self.search_btn.setEnabled(not self.repeated_store.loading)
        self.reset_btn.setEnabled(not self.repeated_store.loading)
        self.filter_toggle_btn.setEnabled(not self.repeated_store.loading)
        self.results_filter_btn.setEnabled(not self.repeated_store.loading)
        if self.repeated_store.loading:
            self.status_label.setText("Loading repeated results...")
        elif self.repeated_store.results:
            self.status_label.setText(f"Loaded {len(self.repeated_store.results)} repeated plates.")
        elif self.has_searched:
            self.status_label.setText("No repeated plates found for the current filters.")
        else:
            self.status_label.setText("Adjust filters and run a repeated search.")

    def _normalize_page_digits(self, text: str) -> None:
        normalized = normalize_ascii_digits(text)
        if normalized == text:
            return
        cursor = self.goto_page_edit.cursorPosition()
        self.goto_page_edit.blockSignals(True)
        self.goto_page_edit.setText(normalized)
        self.goto_page_edit.blockSignals(False)
        self.goto_page_edit.setCursorPosition(min(cursor, len(normalized)))

    def _on_rows_changed(self, _index: int) -> None:
        size = self.rows_combo.currentData()
        if isinstance(size, int):
            self.table.set_page_size(size)

    def _sync_page_state(self, current_page: int, total_pages: int, total_rows: int) -> None:
        if self.goto_page_edit.text().strip() != str(current_page if total_pages else ""):
            self.goto_page_edit.setText(str(current_page) if total_pages else "")
        if total_rows <= 0:
            self.page_meta.setText("0-0 of 0")
        else:
            page_size = self.table.page_size()
            start = (current_page - 1) * page_size + 1
            end = min(total_rows, start + page_size - 1)
            self.page_meta.setText(f"{start}-{end} of {total_rows}")
        self.prev_btn.setEnabled(current_page > 1)
        self.next_btn.setEnabled(total_pages > 0 and current_page < total_pages)

    def _sync_filters_window_ui(self) -> None:
        self.hero_scroll.setVisible(self.filters_window_visible)
        self._update_filters_scroll_height()
        button_text = "Hide Filters" if self.filters_window_visible else "Show Filters"
        self.results_filter_btn.setText(button_text)
        self.filter_toggle_btn.setText(button_text)
        self.filter_state_chip.setText("Filters visible" if self.filters_window_visible else "Filters hidden")

    def _update_filters_scroll_height(self) -> None:
        max_height = max(220, min(430, int(self.height() * 0.42)))
        self.hero_scroll.setMaximumHeight(max_height)

    def _set_filters_window_visible(self, visible: bool) -> None:
        self.filters_window_visible = visible
        self._sync_filters_window_ui()

    def toggle_filters_window(self) -> None:
        self._set_filters_window_visible(not self.filters_window_visible)

    def goto_page(self) -> None:
        page_text = normalize_ascii_digits(self.goto_page_edit.text()).strip()
        if not page_text.isdigit():
            return
        self.table.set_page_number(int(page_text))

    def goto_prev_page(self) -> None:
        self.table.set_page_number(self.table.current_page() - 1)

    def goto_next_page(self) -> None:
        self.table.set_page_number(self.table.current_page() + 1)

    def reset_filters(self) -> None:
        self.has_searched = False
        self.date_from_field.clear()
        self.date_to_field.clear()
        self.camera_select.set_value([])
        self.repeated_spin.setValue(2)
        self.repeated_store.clear()
        self._set_filters_window_visible(True)

    def perform_search(self) -> None:
        date_from = self.date_from_field.value()
        date_to = self.date_to_field.value()
        if date_from is None or date_to is None:
            self._show_error("Please select both start and end dates.")
            return
        if date_from > date_to:
            self._show_error("Start date must be before end date.")
            return

        payload = LprRepeatedPayload(
            date_from=date_from,
            date_to=date_to,
            camera_ids=self.camera_select.value(),
            repeated_number=self.repeated_spin.value(),
        )
        self.has_searched = True
        self._set_filters_window_visible(False)
        results = self.repeated_store.search(payload)
        if results:
            self.toast.success("Repeated Search", f"Loaded {len(results)} repeated plates.")

    def open_repeated_details(self, row: Dict[str, object]) -> None:
        entry = row.get("_entry")
        if not isinstance(entry, LprRepeatedResult):
            return

        payload = {
            "plate_no": entry.number,
            "compare": "equal",
            "date_from": self.date_from_field.value(),
            "date_to": self.date_to_field.value(),
            "camera_ids": self.camera_select.value(),
            "start": 0,
            "length": 300,
            "order_col": 0,
            "order": "asc",
        }
        records = self.search_store.search(payload)
        dialog = RepeatedDetailDialog(self.net, self)
        dialog.set_data(entry, records)
        dialog.exec()

    def _show_error(self, text: str) -> None:
        self.toast.error("Repeated Search", text)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._update_filters_scroll_height()


class MainWindow(QMainWindow):
    navigate = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LPR Repeated Search")
        self.resize(1500, 900)
        page = LprRepeatedPage()
        page.navigate.connect(self.navigate.emit)
        self.setCentralWidget(page)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
