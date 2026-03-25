from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import Dict, List, Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal, QRectF
from PySide6.QtGui import QColor,QPainter,QPainterPath
from app.constants._init_ import Constants
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.models.lpr.report import LprReportPayload, LprReportRow
from app.services.auth.auth_service import AuthService
from app.services.home.devices.camera_service import CameraService
from app.services.home.lpr.report_service import LprReportService
from app.store.auth.auth_store import AuthStore
from app.store.home.lpr.report_store import LprReportStore
from app.store.home.user.department_store import DepartmentStore as CameraDepartmentStore
from app.ui.button import PrimeButton
from app.ui.multiselect import PrimeMultiSelect
from app.ui.select import PrimeSelect
from app.ui.sidebar_toggle import SidebarToggleButton
from app.ui.table import PrimeDataTable, PrimeTableColumn
from app.ui.toast import PrimeToastHost
from app.views.report_shared import REPORT_SIDEBAR_STYLES, ReportSidebar
from app.views.lpr.search import ClearableDateTimeField, FilterAccordionSection


class LprReportPage(QWidget):
    navigate = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.toast = PrimeToastHost(self)

        self.auth_store = AuthStore(AuthService())
        self.camera_store = CameraDepartmentStore(CameraService())
        self.report_store = LprReportStore(LprReportService())

        self._loaded_department_id: Optional[int] = None
        self.filters_window_visible = False
        self._filters_slide_animation: Optional[QPropertyAnimation] = None
        self.has_searched = False

        self.auth_store.changed.connect(self.refresh)
        self.auth_store.error.connect(self._show_error)
        self.camera_store.changed.connect(self.refresh)
        self.camera_store.error.connect(self._show_error)
        self.report_store.changed.connect(self.refresh)
        self.report_store.error.connect(self._show_error)

        self._build_ui()
        self._apply_style()

        self.auth_store.load()
        self.camera_store.get_camera_for_user(None, silent=True)
        self.refresh()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)
        self._root_layout = root

        self.sidebar = ReportSidebar("/report/lpr", self)
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
        self.content_panel.setObjectName("reportContentPanel")
        root.addWidget(self.content_panel, 1)
        root.setStretch(0, 0)
        root.setStretch(1, 1)
        root.setStretch(2, 4)

        content = QVBoxLayout(self.content_panel)
        content.setContentsMargins(14, 14, 14, 14)
        content.setSpacing(10)

        hero_scroll = QScrollArea()
        hero_scroll.setObjectName("reportFiltersScroll")
        hero_scroll.setWidgetResizable(True)
        hero_scroll.setFrameShape(QFrame.Shape.NoFrame)
        hero_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        hero_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        hero_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        filters_layout.addWidget(hero_scroll, 1)
        self.hero_scroll = hero_scroll

        hero_frame = QFrame()
        hero_frame.setObjectName("reportHero")
        hero_frame.setMinimumWidth(0)
        hero = QVBoxLayout(hero_frame)
        hero.setContentsMargins(14, 14, 14, 14)
        hero.setSpacing(10)
        self.hero_frame = hero_frame
        hero_scroll.setWidget(hero_frame)

        self.report_type_select = PrimeSelect(placeholder="Select report type")
        self.report_type_select.set_options(
            [
                {"label": "LPR Report", "value": "lpr"},
                {"label": "Monthly Report", "value": "monthly"},
            ]
        )
        self.report_type_select.set_value("lpr")
        self._allow_horizontal_shrink(self.report_type_select)

        self.camera_select = PrimeMultiSelect(options=[], placeholder="Select Camera")
        self._allow_horizontal_shrink(self.camera_select)

        self.date_from_field = ClearableDateTimeField("Start Time")
        self.date_to_field = ClearableDateTimeField("End Time")
        self._allow_horizontal_shrink(self.date_from_field)
        self._allow_horizontal_shrink(self.date_to_field)

        time_band = FilterAccordionSection(
            "Time Range",
            "",
            expanded=True,
            collapsible=False,
        )
        time_band.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        time_layout = QGridLayout()
        time_layout.setContentsMargins(0, 0, 0, 0)
        time_layout.setHorizontalSpacing(12)
        time_layout.setVerticalSpacing(10)
        time_layout.setColumnStretch(0, 1)
        time_band.body_layout.addLayout(time_layout)
        time_layout.addWidget(
            self._hero_field_block(
                "Start Date & Time",
                self.date_from_field,
                "",
            ),
            0,
            0,
        )
        time_layout.addWidget(
            self._hero_field_block(
                "End Date & Time",
                self.date_to_field,
                "",
            ),
            1,
            0,
        )
        hero.addWidget(time_band)

        setup_band = FilterAccordionSection(
            "Report Setup",
            "",
            expanded=True,
            collapsible=False,
        )
        setup_band.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        setup_band.body_layout.addWidget(self._field_block("Report Type", self.report_type_select))
        hero.addWidget(setup_band)

        source_band = FilterAccordionSection(
            "Source",
            "",
            expanded=True,
            collapsible=False,
        )
        source_band.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        source_band.body_layout.addWidget(self._field_block("Camera", self.camera_select))
        hero.addWidget(source_band)

        hero_actions = QVBoxLayout()
        hero_actions.setContentsMargins(0, 0, 0, 0)
        hero_actions.setSpacing(6)
        hero.addLayout(hero_actions)

        self.reset_btn = PrimeButton("Reset Filters", variant="secondary", mode="outline", size="sm", width=132)
        self.reset_btn.clicked.connect(self.reset_filters)
        hero_actions.addWidget(self.reset_btn)

        self.export_btn = PrimeButton("Export CSV", variant="secondary", mode="outline", size="sm", width=132)
        self.export_btn.clicked.connect(self.export_csv)
        hero_actions.addWidget(self.export_btn)

        self.search_btn = PrimeButton("Run Report", variant="primary", mode="filled", size="sm", width=132)
        self.search_btn.clicked.connect(self.perform_report)
        hero_actions.addWidget(self.search_btn)
        self._allow_horizontal_shrink(self.reset_btn)
        self._allow_horizontal_shrink(self.export_btn)
        self._allow_horizontal_shrink(self.search_btn)
        hero.addStretch(1)

        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("reportToolbar")
        toolbar = QHBoxLayout(toolbar_frame)
        toolbar.setContentsMargins(14, 14, 14, 14)
        toolbar.setSpacing(10)
        content.addWidget(toolbar_frame)

        self.results_filter_btn = SidebarToggleButton(self.filters_window_visible, self)
        self.results_filter_btn.clicked.connect(self.toggle_filters_window)
        toolbar.addWidget(self.results_filter_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(3)
        page_title = QLabel("Report Results")
        page_title.setObjectName("pageTitle")
        self.status_label = QLabel("Choose filters and run the report.")
        self.status_label.setObjectName("pageSummary")
        title_col.addWidget(page_title)
        title_col.addWidget(self.status_label)
        toolbar.addLayout(title_col, 1)

        self.table = PrimeDataTable(page_size=20, page_size_options=[10, 20, 50, 100], row_height=48, show_footer=True)
        self.table.set_columns(
            [
                PrimeTableColumn("camera_name", "Camera Name", stretch=True),
                PrimeTableColumn("total_records", "Total Number of Records", stretch=True),
                PrimeTableColumn("unique_vehicles", "Number of Unique Vehicles", stretch=True),
                PrimeTableColumn("english_plates", "English Plates", stretch=True),
                PrimeTableColumn("taxi_plates", "Taxi Plates", stretch=True),
                PrimeTableColumn("private_plates", "Private Plates", stretch=True),
                PrimeTableColumn("transport_plates", "Transport Plates", stretch=True),
            ]
        )
        content.addWidget(self.table, 1)
        self._sync_filters_window_ui()

    def _hero_field_block(self, label_text: str, field: QWidget, hint_text: str) -> QWidget:
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

    def _field_block(self, label_text: str, field: QWidget) -> QWidget:
        wrapper = QWidget()
        wrapper.setObjectName("fieldBlock")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(label_text)
        label.setObjectName("fieldLabel")
        layout.addWidget(label)
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

    def _apply_style(self) -> None:
        self.setStyleSheet(
            REPORT_SIDEBAR_STYLES
            + """
            QWidget {
                color: #e2e8f0;
                font-size: 13px;
            }
            QFrame#filtersPanel {
                background: transparent;
                border: none;
            }
            QFrame#reportContentPanel {
                background: #171b22;
                border: 1px solid #2b3240;
                border-radius: 18px;
            }
            QFrame#reportHero {
                background: #171b22;
                border: 1px solid #2b3240;
                border-radius: 18px;
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
            QFrame#reportToolbar,
            QFrame#reportSummaryWrap {
                background: #1f2630;
                border: 1px solid #2e3746;
                border-radius: 16px;
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
                border-radius: 12px;
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
            QLabel#fieldLabel {
                color: #cbd5e1;
                font-size: 12px;
                font-weight: 700;
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
            QWidget#fieldBlock,
            QWidget#heroFieldBlock {
                background: transparent;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QTimeEdit {
                background: #232a34;
                border: 1px solid #364152;
                border-radius: 10px;
                color: #f8fafc;
                min-height: 38px;
                padding: 0 12px;
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
            QLabel#datePopupPreview {
                color: #bfdbfe;
                font-size: 12px;
                padding: 6px 10px;
                background: rgba(59, 130, 246, 0.12);
                border: 1px solid rgba(147, 197, 253, 0.25);
                border-radius: 10px;
            }
            QLabel#datePopupLabel {
                color: #dbeafe;
                font-size: 12px;
                font-weight: 700;
            }
            QCalendarWidget#dateCalendar {
                background: transparent;
                border: none;
            }
            QCalendarWidget QWidget#qt_calendar_navigationbar {
                background: transparent;
                min-height: 34px;
            }
            QCalendarWidget QToolButton {
                color: #eff6ff;
                background: transparent;
                border: none;
                font-weight: 700;
                min-width: 28px;
            }
            QCalendarWidget QMenu {
                background: #111827;
                color: #e5e7eb;
                border: 1px solid #334155;
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
            for camera in self.camera_store.cameras
            if int(camera.id or 0) > 0
        ]

    def _rows(self) -> List[Dict[str, object]]:
        return [
            {
                "camera_name": item.camera_display,
                "total_records": item.total_records,
                "unique_vehicles": item.unique_vehicles,
                "english_plates": item.english_plates,
                "taxi_plates": item.taxi_plates,
                "private_plates": item.private_plates,
                "transport_plates": item.transport_plates,
                "_entry": item,
            }
            for item in self.report_store.rows
        ]

    def refresh(self) -> None:
        current_user = self.auth_store.current_user
        department_id = current_user.department_id if current_user is not None else None
        if department_id != self._loaded_department_id:
            self._loaded_department_id = department_id
            self.camera_store.get_camera_for_user(department_id, silent=True)

        self.camera_select.set_options(self._camera_options())
        self.table.set_rows(self._rows())

        busy = self.report_store.loading
        self.search_btn.setEnabled(not busy)
        self.reset_btn.setEnabled(not busy)
        self.export_btn.setEnabled(not busy and bool(self.report_store.rows))
        self.results_filter_btn.setEnabled(not busy)

        if busy:
            self.status_label.setText("Loading report results...")
        elif self.report_store.rows:
            self.status_label.setText(f"Loaded {len(self.report_store.rows)} report rows.")
        elif self.has_searched:
            self.status_label.setText("No report rows returned for the current filters.")
        else:
            self.status_label.setText("Choose filters and run the report.")

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
        if hasattr(self, "sidebar") and self.sidebar.isVisible():
            available -= self.sidebar.width() + spacing
        if available <= 0:
            return 0
        return max(0, min(300, max(200, int(available * 0.18))))

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

    def toggle_filters_window(self) -> None:
        self._set_filters_window_visible(not self.filters_window_visible)

    def _validate_payload(self) -> Optional[LprReportPayload]:
        date_from = self.date_from_field.value()
        date_to = self.date_to_field.value()
        if date_from is None or date_to is None:
            self._show_error("Please select both start and end dates.")
            return None
        if date_from > date_to:
            self._show_error("Start date must be before end date.")
            return None

        return LprReportPayload(
            date_from=date_from,
            date_to=date_to,
            camera_ids=self.camera_select.value(),
            report_type=self.report_type_select.value() or "lpr",
        )

    def reset_filters(self) -> None:
        self.has_searched = False
        self.report_type_select.set_value("lpr")
        self.date_from_field.clear()
        self.date_to_field.clear()
        self.camera_select.set_value([])
        self.report_store.clear()

    def perform_report(self) -> None:
        payload = self._validate_payload()
        if payload is None:
            return
        self.has_searched = True
        rows = self.report_store.search(payload)
        if rows:
            self.toast.success("LPR Report", f"Loaded {len(rows)} report rows.")

    def export_csv(self) -> None:
        if not self.report_store.rows:
            self._show_error("No report data available to export.")
            return

        default_name = f"lpr-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
        suggested = os.path.join(os.path.expanduser("~"), default_name)
        path, _ = QFileDialog.getSaveFileName(self, "Export LPR Report", suggested, "CSV Files (*.csv)")
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "Camera Name",
                        "Total Number of Records",
                        "Number of Unique Vehicles",
                        "English Plates",
                        "Taxi Plates",
                        "Private Plates",
                        "Transport Plates",
                    ]
                )
                for item in self.report_store.rows:
                    writer.writerow(
                        [
                            item.camera_display,
                            item.total_records,
                            item.unique_vehicles,
                            item.english_plates,
                            item.taxi_plates,
                            item.private_plates,
                            item.transport_plates,
                        ]
                    )
            self.toast.success("LPR Report", f"Exported report to {path}.")
        except Exception as exc:
            self._show_error(str(exc))

    def _show_error(self, text: str) -> None:
        self.toast.error("LPR Report", text)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._sync_filters_panel_width(animate=False)
        self._update_filters_scroll_height()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        p.fillPath(path, QColor(Constants.DARK_BG))   # dark bg — cards float above it
        super().paintEvent(event)
