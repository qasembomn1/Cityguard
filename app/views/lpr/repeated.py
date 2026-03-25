from __future__ import annotations

import os
import sys
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from app.constants._init_ import Constants
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QSizePolicy,
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
from app.ui.dialog import PrimeDialog
from app.ui.input import PrimeInput
from app.ui.multiselect import PrimeMultiSelect
from app.ui.select import PrimeSelect
from app.ui.sidebar_toggle import SidebarToggleButton
from app.ui.table import PrimeDataTable, PrimeTableColumn
from app.ui.toast import PrimeToastHost
from app.utils.digits import normalize_ascii_digits
from app.utils.env import resolve_http_base_url
from app.views.lpr.search import ClearableDateTimeField, FilterAccordionSection, SEARCH_TIMEZONE
from app.views.search_shared import SEARCH_SIDEBAR_STYLES, SearchSidebar


def _base_http_url() -> str:
    return resolve_http_base_url()


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


class RepeatedDetailDialog(PrimeDialog):
    def __init__(self, net: QNetworkAccessManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            title="Repeated Details",
            parent=parent,
            width=1120,
            height=680,
            ok_text="Details",
            cancel_text="Close",
            draggable=False,
        )
        self._net = net
        self._records: List[LprSearchResult] = []
        self._index = 0

        self.ok_button.hide()
        footer = self.footer_widget.layout()

        self.position_label = QLabel("Record 0 of 0")
        self.position_label.setObjectName("repeatedDetailMeta")
        footer.insertWidget(0, self.position_label)

        self.prev_btn = PrimeButton("Prev", variant="secondary", mode="outline", size="sm", width=90)
        self.prev_btn.clicked.connect(self._show_prev)
        footer.insertWidget(1, self.prev_btn)

        self.next_btn = PrimeButton("Next", variant="secondary", mode="outline", size="sm", width=90)
        self.next_btn.clicked.connect(self._show_next)
        footer.insertWidget(2, self.next_btn)

        content = QWidget()
        root = QVBoxLayout(content)
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

        self.set_content(content, fill_height=True)
        self.setStyleSheet(
            self.styleSheet()
            + """
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
        self.set_title(f"Repeated Details ({self._index + 1 if has_records else 0} / {total})")
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
        self.filter_panel_open = False
        self.filters_window_visible = False
        self._filters_slide_animation: Optional[QPropertyAnimation] = None
        self._filter_sections: list[FilterAccordionSection] = []
        self.rows_per_page = 50
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
        self._apply_default_date_range()

        self.auth_store.load()
        self.camera_store.get_camera_for_user(None, silent=True)
        self.refresh()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)
        self._root_layout = root

        self.sidebar = SearchSidebar("/search/lpr/repeated", self)
        self.sidebar.navigate.connect(self.navigate.emit)
        root.addWidget(self.sidebar, 0)

        self.filters_panel = QFrame()
        self.filters_panel.setObjectName("filtersPanel")
        self.filters_panel.setMinimumWidth(0)
        self.filters_panel.setMaximumWidth(0 if not self.filters_window_visible else 16777215)
        self.filters_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        filters_layout = QVBoxLayout(self.filters_panel)
        filters_layout.setContentsMargins(0, 0, 0, 0)
        filters_layout.setSpacing(0)
        self.filters_panel.setVisible(self.filters_window_visible)
        root.addWidget(self.filters_panel, 0)

        self.content_panel = QFrame()
        self.content_panel.setObjectName("resultsPanel")
        self.content_panel.setMinimumWidth(0)
        self.content_panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        root.addWidget(self.content_panel, 1)
        root.setStretch(0, 0)
        root.setStretch(1, 1)
        root.setStretch(2, 4)

        content = QVBoxLayout(self.content_panel)
        content.setContentsMargins(18, 16, 18, 18)
        content.setSpacing(14)

        self.hero_scroll = QScrollArea()
        self.hero_scroll.setObjectName("filtersScroll")
        self.hero_scroll.setWidgetResizable(True)
        self.hero_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.hero_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.hero_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.hero_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.hero_scroll.viewport().setAutoFillBackground(False)
        filters_layout.addWidget(self.hero_scroll, 1)

        hero_frame = QFrame()
        hero_frame.setObjectName("searchHero")
        hero_frame.setMinimumWidth(0)
        self.hero_frame = hero_frame
        hero = QVBoxLayout(hero_frame)
        hero.setContentsMargins(18, 18, 18, 18)
        hero.setSpacing(14)
        self.hero_scroll.setWidget(hero_frame)

        hero_head = QVBoxLayout()
        hero_head.setContentsMargins(0, 0, 0, 0)
        hero_head.setSpacing(6)
        hero.addLayout(hero_head)

        hero_text = QVBoxLayout()
        hero_text.setContentsMargins(0, 0, 0, 0)
        hero_text.setSpacing(4)
        hero_head.addLayout(hero_text)

        hero_title = QLabel("Repeated Search")
        hero_title.setObjectName("heroTitle")
        hero_title.setWordWrap(True)
        hero_text.addWidget(hero_title)

        time_band = FilterAccordionSection(
            "Time Range",
            "",
            expanded=True,
            collapsible=False,
        )
        self._filter_sections.append(time_band)
        hero.addWidget(time_band)
        time_layout = QGridLayout()
        time_layout.setContentsMargins(0, 0, 0, 0)
        time_layout.setHorizontalSpacing(12)
        time_layout.setVerticalSpacing(10)
        time_layout.setColumnStretch(0, 1)
        time_layout.setRowStretch(2, 1)
        time_band.body_layout.addLayout(time_layout)
        time_band.body_layout.addStretch(1)

        self.date_from_field = ClearableDateTimeField("Start Time")
        self._allow_horizontal_shrink(self.date_from_field)
        time_layout.addWidget(
            self._hero_field_block(
                "Start Date & Time",
                self.date_from_field,
                "",
            ),
            0,
            0,
        )

        self.date_to_field = ClearableDateTimeField("End Time")
        self._allow_horizontal_shrink(self.date_to_field)
        time_layout.addWidget(
            self._hero_field_block(
                "End Date & Time",
                self.date_to_field,
                "",
            ),
            1,
            0,
        )

        repeated_band = FilterAccordionSection(
            "Repeated Filters",
            "",
            expanded=True,
            collapsible=False,
        )
        self._filter_sections.append(repeated_band)
        hero.addWidget(repeated_band)
        repeated_layout = QGridLayout()
        repeated_layout.setContentsMargins(0, 0, 0, 0)
        repeated_layout.setHorizontalSpacing(12)
        repeated_layout.setVerticalSpacing(10)
        repeated_layout.setColumnStretch(0, 1)
        repeated_layout.setRowStretch(2, 1)
        repeated_band.body_layout.addLayout(repeated_layout)
        repeated_band.body_layout.addStretch(1)

        self.repeated_input = PrimeInput(
            type="number",
            minimum=1,
            maximum=9999,
            decimals=0,
            value=2,
            placeholder_text="Repeated number",
        )
        self._allow_horizontal_shrink(self.repeated_input)
        repeated_layout.addWidget(
            self._hero_field_block(
                "Repeated Number",
                self.repeated_input,
                "",
            ),
            0,
            0,
        )

        self.camera_select = PrimeMultiSelect(options=[], placeholder="Select Camera")
        self._allow_horizontal_shrink(self.camera_select)
        repeated_layout.addWidget(
            self._hero_field_block(
                "Camera",
                self.camera_select,
                "",
            ),
            1,
            0,
        )

        for section in self._filter_sections:
            section.toggled.connect(self._sync_filter_toggle_ui)

        hero_actions = QVBoxLayout()
        hero_actions.setContentsMargins(0, 0, 0, 0)
        hero_actions.setSpacing(8)
        hero.addLayout(hero_actions)

        self.reset_btn = PrimeButton("Reset Filters", variant="secondary", mode="outline", size="sm")
        self.reset_btn.clicked.connect(self.reset_filters)
        self._allow_horizontal_shrink(self.reset_btn)
        hero_actions.addWidget(self.reset_btn)

        self.filter_toggle_btn = PrimeButton("Hide Filters", variant="secondary", mode="outline", size="sm")
        self.filter_toggle_btn.clicked.connect(self.toggle_filter_panel)
        self.filter_toggle_btn.hide()
        self._allow_horizontal_shrink(self.filter_toggle_btn)
        hero_actions.addWidget(self.filter_toggle_btn)

        self.search_btn = PrimeButton("Search Records", variant="primary", mode="filled", size="sm")
        self.search_btn.clicked.connect(self.perform_search)
        self._allow_horizontal_shrink(self.search_btn)
        hero_actions.addWidget(self.search_btn)
        self._sync_filter_toggle_ui()
        self._sync_filters_window_ui()

        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("resultsToolbar")
        toolbar_frame.setMinimumWidth(0)
        toolbar_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar = QVBoxLayout(toolbar_frame)
        toolbar.setContentsMargins(14, 14, 14, 14)
        toolbar.setSpacing(10)
        content.addWidget(toolbar_frame)

        toolbar_head = QHBoxLayout()
        toolbar_head.setContentsMargins(0, 0, 0, 0)
        toolbar_head.setSpacing(10)
        toolbar.addLayout(toolbar_head)

        self.results_filter_btn = SidebarToggleButton(self.filters_window_visible, self)
        self.results_filter_btn.clicked.connect(self.toggle_filters_window)
        toolbar_head.addWidget(self.results_filter_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        left_cluster = QVBoxLayout()
        left_cluster.setContentsMargins(0, 0, 0, 0)
        left_cluster.setSpacing(3)
        self.page_title = QLabel("LPR Repeated Results")
        self.page_title.setObjectName("pageTitle")
        self.page_title.setWordWrap(True)
        self.page_title.setMinimumWidth(0)
        self.page_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status_label = QLabel("Adjust filters and run a repeated search.")
        self.status_label.setObjectName("pageSummary")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumWidth(0)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        left_cluster.addWidget(self.page_title)
        left_cluster.addWidget(self.status_label)
        toolbar_head.addLayout(left_cluster, 1)

        self.rows_combo = PrimeSelect(
            options=[{"label": f"{size} Rows", "value": size} for size in (10, 20, 50, 100, 200)],
            placeholder="50 Rows",
        )
        self.rows_combo.set_value(self.rows_per_page)
        self.rows_combo.value_changed.connect(self._on_rows_changed)
        self._allow_horizontal_shrink(self.rows_combo)
        toolbar_head.addWidget(self.rows_combo)

        toolbar_nav = QHBoxLayout()
        toolbar_nav.setContentsMargins(0, 0, 0, 0)
        toolbar_nav.setSpacing(10)
        toolbar.addLayout(toolbar_nav)
        toolbar_nav.addStretch(1)

        self.goto_page_edit = PrimeInput(
            type="number",
            minimum=1,
            maximum=999999,
            decimals=0,
            placeholder_text="Goto Page...",
        )
        self.goto_page_edit.clear()
        self.goto_page_edit.setFixedWidth(120)
        self.goto_page_edit.textEdited.connect(self._normalize_page_digits)
        self._allow_horizontal_shrink(self.goto_page_edit)
        toolbar_nav.addWidget(self.goto_page_edit)

        self.goto_btn = PrimeButton("Goto", variant="primary", size="sm", width=72)
        self.goto_btn.clicked.connect(self.goto_page)
        self._allow_horizontal_shrink(self.goto_btn)
        toolbar_nav.addWidget(self.goto_btn)

        self.prev_btn = PrimeButton("Prev", variant="secondary", mode="outline", size="sm", width=82)
        self.prev_btn.clicked.connect(self.goto_prev_page)
        self._allow_horizontal_shrink(self.prev_btn)
        toolbar_nav.addWidget(self.prev_btn)

        self.next_btn = PrimeButton("Next", variant="secondary", mode="outline", size="sm", width=82)
        self.next_btn.clicked.connect(self.goto_next_page)
        self._allow_horizontal_shrink(self.next_btn)
        toolbar_nav.addWidget(self.next_btn)

        self.page_meta = QLabel("0-0 of 0")
        self.page_meta.setObjectName("repeatedMeta")
        toolbar_nav.addWidget(self.page_meta)

        self.table = PrimeDataTable(
            page_size=self.rows_per_page,
            page_size_options=[10, 20, 50, 100, 200],
            row_height=48,
            show_footer=False,
        )
        self.table.setMinimumWidth(0)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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

        self._update_filters_scroll_height()

    def _hero_field_block(self, label_text: str, field: QWidget, hint_text: str = "") -> QWidget:
        wrapper = QWidget()
        wrapper.setObjectName("heroFieldBlock")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label = QLabel(label_text)
        label.setObjectName("heroFieldLabel")
        layout.addWidget(label)

        if hint_text:
            hint = QLabel(hint_text)
            hint.setObjectName("heroFieldHint")
            hint.setWordWrap(True)
            layout.addWidget(hint)
        layout.addWidget(field)
        return wrapper

    def _allow_horizontal_shrink(self, widget: QWidget) -> None:
        widget.setMinimumWidth(0)
        policy = widget.sizePolicy()
        if policy.horizontalPolicy() == QSizePolicy.Policy.Fixed:
            policy.setHorizontalPolicy(QSizePolicy.Policy.Preferred)
        else:
            policy.setHorizontalPolicy(QSizePolicy.Policy.Expanding)
        widget.setSizePolicy(policy)

    def _apply_default_date_range(self) -> None:
        now = datetime.now(SEARCH_TIMEZONE).replace(second=0, microsecond=0)
        self.date_to_field.set_value(now)
        self.date_from_field.set_value(now - timedelta(hours=24))

    def _apply_style(self) -> None:
        self.setStyleSheet(
            SEARCH_SIDEBAR_STYLES
            + """
            QWidget {
                color: #e2e8f0;
                font-size: 13px;
            }
            QFrame#filtersPanel {
                background: transparent;
                border: none;
            }
            QFrame#resultsPanel {
                background: #171b22;
                border: 1px solid #2b3240;
                border-radius: 18px;
            }
            QFrame#resultsToolbar {
                background: #1f2630;
                border: 1px solid #2e3746;
                border-radius: 16px;
            }
            QFrame#searchHero {
                background: #171b22;
                border: 1px solid #2b3240;
                border-radius: 22px;
            }
            QFrame#filterAccordion {
                background: #1f2630;
                border: 1px solid #2e3746;
                border-radius: 18px;
            }
            QPushButton#filterAccordionHeader {
                background: transparent;
                border: none;
                color: #e2e8f0;
                font-size: 14px;
                font-weight: 800;
                padding: 14px 16px;
                text-align: left;
            }
            QPushButton#filterAccordionHeader:hover {
                background: rgba(148, 163, 184, 0.08);
            }
            QPushButton#filterAccordionHeader:disabled {
                color: #64748b;
            }
            QFrame#filterAccordionBody {
                background: transparent;
                border-top: 1px solid rgba(71, 85, 105, 0.55);
            }
            QLabel#filterAccordionHint {
                color: #94a3b8;
                font-size: 11px;
            }
            QLabel#heroTitle {
                color: #f8fafc;
                font-size: 28px;
                font-weight: 900;
            }
            QLabel#heroHint {
                color: #94a3b8;
                font-size: 13px;
            }
            QLabel#heroChip {
                background: rgba(148, 163, 184, 0.14);
                border: 1px solid rgba(148, 163, 184, 0.32);
                color: #e2e8f0;
                font-size: 11px;
                font-weight: 800;
                padding: 6px 10px;
            }
            QLabel#pageTitle {
                color: #f8fafc;
                font-size: 22px;
                font-weight: 800;
            }
            QLabel#pageSummary {
                color: #94a3b8;
                font-size: 12px;
            }
            QLabel#heroFieldLabel {
                color: #cbd5e1;
                font-size: 12px;
                font-weight: 800;
            }
            QLabel#heroFieldHint {
                color: #94a3b8;
                font-size: 11px;
            }
            QLabel#repeatedMeta {
                color: #94a3b8;
                font-size: 12px;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QTimeEdit {
                background: #232a34;
                border: 1px solid #364152;
                border-radius: 10px;
                color: #f8fafc;
                min-height: 38px;
                padding: 0 12px;
            }
            QWidget#heroFieldBlock {
                background: transparent;
            }
            QFrame#dateField {
                background: #232a34;
                border: 1px solid #364152;
                border-radius: 12px;
            }
            QLineEdit#datePickerDisplay {
                background: transparent;
                border: none;
                color: #f8fafc;
                min-height: 46px;
                padding: 0 12px;
                selection-background-color: #3b82f6;
            }
            QToolButton#datePickerButton, QToolButton#dateClearButton {
                background: transparent;
                border: none;
                min-width: 38px;
                max-width: 38px;
                min-height: 46px;
                max-height: 46px;
                padding: 0;
            }
            QToolButton#datePickerButton:hover, QToolButton#dateClearButton:hover {
                background: rgba(96, 165, 250, 0.14);
            }
            QFrame#searchHero QLineEdit,
            QFrame#searchHero QComboBox,
            QFrame#searchHero QSpinBox,
            QFrame#searchHero QDoubleSpinBox,
            QFrame#searchHero QDateTimeEdit,
            QFrame#searchHero QTimeEdit {
                background: #232a34;
                border: 1px solid #364152;
                border-radius: 12px;
                color: #f8fafc;
                min-height: 44px;
                padding: 0 12px;
            }
            QFrame#searchHero QLineEdit:focus,
            QFrame#searchHero QComboBox:focus,
            QFrame#searchHero QSpinBox:focus,
            QFrame#searchHero QDoubleSpinBox:focus,
            QFrame#searchHero QDateTimeEdit:focus,
            QFrame#searchHero QTimeEdit:focus {
                border: 1px solid #64748b;
            }
            QDialog#datePickerPopup {
                background: #0f1726;
                border: 1px solid #35588c;
                border-radius: 16px;
            }
            QLabel#datePopupTitle {
                color: #f8fbff;
                font-size: 14px;
                font-weight: 800;
            }
            QLabel#datePopupHint {
                color: #a9bfdc;
                font-size: 11px;
            }
            QCalendarWidget {
                background: transparent;
                color: #e5e7eb;
            }
            QCalendarWidget QWidget#qt_calendar_navigationbar {
                background: transparent;
            }
            QCalendarWidget QToolButton {
                color: #e5e7eb;
                min-width: 28px;
                min-height: 28px;
                border-radius: 8px;
            }
            QCalendarWidget QToolButton:hover {
                background: rgba(59, 130, 246, 0.15);
            }
            QCalendarWidget QMenu {
                background: #0f1726;
                color: #e5e7eb;
                border: 1px solid #35588c;
                border-radius: 8px;
            }
            QCalendarWidget QSpinBox {
                background: #111827;
                border: 1px solid #334155;
                border-radius: 8px;
                color: #f8fafc;
                min-height: 28px;
                padding: 0 8px;
            }
            QCalendarWidget QAbstractItemView:enabled {
                background: #0b1220;
                color: #e5e7eb;
                selection-background-color: #3b82f6;
                selection-color: white;
                outline: 0;
            }
            QTimeEdit#datePopupTimeEdit {
                background: #111827;
                border: 1px solid #334155;
                border-radius: 10px;
                color: #f8fafc;
                min-height: 36px;
                padding: 0 10px;
            }
            QPushButton#datePopupSecondaryButton, QPushButton#datePopupPrimaryButton {
                min-height: 34px;
                border-radius: 10px;
                padding: 0 14px;
                font-weight: 700;
            }
            QPushButton#datePopupSecondaryButton {
                background: #1f2937;
                border: 1px solid #374151;
                color: #e5e7eb;
            }
            QPushButton#datePopupSecondaryButton:hover {
                background: #273446;
            }
            QPushButton#datePopupPrimaryButton {
                background: #2563eb;
                border: none;
                color: white;
            }
            QPushButton#datePopupPrimaryButton:hover {
                background: #1d4ed8;
            }
            QScrollArea, QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            """
        )

    def _camera_options(self) -> List[dict]:
        return [
            {"label": camera.name or f"Camera #{camera.id}", "value": camera.id}
            for camera in sorted(self.camera_store.cameras, key=lambda item: (item.name or "").lower())
            if int(getattr(camera, "id", 0) or 0) > 0
        ]

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
        department_id = None
        if current_user is not None and not getattr(current_user, "is_superadmin", False):
            department_id = current_user.department_id
        if department_id != self._loaded_department_id:
            self._loaded_department_id = department_id
            self.camera_store.get_camera_for_user(department_id, silent=True)

        previous_camera_ids = set(self.camera_select.value())
        camera_options = self._camera_options()
        self.camera_select.set_options(camera_options)
        self.camera_select.set_value(
            [item for item in previous_camera_ids if item in {opt["value"] for opt in camera_options}]
        )
        self.table.set_rows(self._rows())
        self.search_btn.setEnabled(not self.repeated_store.loading)
        self.reset_btn.setEnabled(not self.repeated_store.loading)
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

    def _on_rows_changed(self, value) -> None:
        if isinstance(value, int):
            self.rows_per_page = value
            self.table.set_page_size(value)

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

    def _sync_filter_toggle_ui(self, *_args) -> None:
        if self._filter_sections and all(not section.is_collapsible() for section in self._filter_sections):
            self.filter_panel_open = True
            if hasattr(self, "filter_toggle_btn"):
                self.filter_toggle_btn.setText("Hide Filters")
            return
        open_count = sum(1 for section in self._filter_sections if section.is_expanded())
        self.filter_panel_open = open_count > 0
        if open_count <= 0:
            if hasattr(self, "filter_toggle_btn"):
                self.filter_toggle_btn.setText("Show Filters")
        elif open_count >= len(self._filter_sections):
            if hasattr(self, "filter_toggle_btn"):
                self.filter_toggle_btn.setText("Hide Filters")
        else:
            if hasattr(self, "filter_toggle_btn"):
                self.filter_toggle_btn.setText("Hide Filters")

    def _sync_filters_window_ui(self) -> None:
        if hasattr(self, "filters_panel"):
            self._sync_filters_panel_width(animate=False)
        else:
            self.hero_scroll.setVisible(self.filters_window_visible)
        self._update_filters_scroll_height()
        if hasattr(self, "results_filter_btn"):
            self.results_filter_btn.sync_visibility(self.filters_window_visible)

    def _update_filters_scroll_height(self) -> None:
        if not hasattr(self, "hero_scroll"):
            return
        self.hero_scroll.setMaximumHeight(16777215)

    def _target_filters_panel_width(self) -> int:
        if not hasattr(self, "_root_layout"):
            return 0
        layout = self._root_layout
        margins = layout.contentsMargins()
        spacing = max(0, layout.spacing())
        available = self.width() - margins.left() - margins.right() - spacing
        if available <= 0:
            return 0
        return max(0, int(available * 0.2))

    def _set_filters_panel_width(self, width: int) -> None:
        if not hasattr(self, "filters_panel"):
            return
        self.filters_panel.setMaximumWidth(max(0, width))

    def _animate_filters_panel_width(self, target: int) -> None:
        if not hasattr(self, "filters_panel"):
            return
        target = max(0, int(target))
        if self._filters_slide_animation is not None:
            try:
                self._filters_slide_animation.stop()
            except Exception:
                pass
            self._filters_slide_animation.deleteLater()
            self._filters_slide_animation = None

        current = max(0, int(self.filters_panel.maximumWidth()))
        if target > 0:
            self.filters_panel.setVisible(True)
            if current == 0:
                self._set_filters_panel_width(1)
                current = 1
        if current == target:
            if target == 0:
                self.filters_panel.setVisible(False)
            return

        animation = QPropertyAnimation(self.filters_panel, b"maximumWidth", self)
        animation.setDuration(220)
        animation.setStartValue(current)
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        if target == 0:
            animation.finished.connect(lambda: self.filters_panel.setVisible(False))
        self._filters_slide_animation = animation
        animation.start()

    def _sync_filters_panel_width(self, animate: bool = False) -> None:
        if not hasattr(self, "filters_panel") or not hasattr(self, "_root_layout"):
            return
        target = self._target_filters_panel_width() if self.filters_window_visible else 0
        if animate:
            self._animate_filters_panel_width(target)
            return
        self._set_filters_panel_width(target)
        self.filters_panel.setVisible(target > 0)

    def _set_filters_window_visible(self, visible: bool) -> None:
        self.filters_window_visible = visible
        self._sync_filters_panel_width(animate=True)
        self._update_filters_scroll_height()
        if hasattr(self, "results_filter_btn"):
            self.results_filter_btn.sync_visibility(self.filters_window_visible)

    def _set_filter_panel_visible(self, visible: bool) -> None:
        for section in self._filter_sections:
            section.set_expanded(visible)
        self._sync_filter_toggle_ui()
        self._sync_filters_window_ui()

    def toggle_filter_panel(self) -> None:
        self._set_filter_panel_visible(not self.filter_panel_open)

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
        self._apply_default_date_range()
        self.camera_select.set_value([])
        self.repeated_input.setValue(2)
        self.repeated_store.clear()
        self._set_filter_panel_visible(False)
        self.refresh()

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
            repeated_number=int(self.repeated_input.value()),
        )
        self.has_searched = True
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
            "length": max(300, self.rows_per_page * 4),
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
        self._sync_filters_panel_width(animate=False)
        self._update_filters_scroll_height()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        p.fillPath(path, QColor(Constants.DARK_BG))
        super().paintEvent(event)
