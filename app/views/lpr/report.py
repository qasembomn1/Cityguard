from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import Dict, List, Optional

from PySide6.QtCore import QDateTime, QSize, Qt, Signal,QRectF
from PySide6.QtGui import QIcon,QColor,QPainter,QPainterPath
from app.constants._init_ import Constants
from PySide6.QtWidgets import (
    QFileDialog,
    QDateTimeEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
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
from app.ui.table import PrimeDataTable, PrimeTableColumn
from app.ui.toast import PrimeToastHost


_ICONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../resources/icons"))


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


class ReportDateTimeField(QFrame):
    def __init__(self, placeholder: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("reportDateField")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        self.edit = QDateTimeEdit()
        self.edit.setCalendarPopup(True)
        self.edit.setDisplayFormat("yyyy-MM-dd hh:mm AP")
        self.edit.setSpecialValueText(placeholder)
        self.edit.setDateTime(QDateTime.currentDateTime())
        self.edit.setMinimumDateTime(QDateTime.fromSecsSinceEpoch(0))
        self.edit.setObjectName("reportDateEdit")
        self.edit.dateTimeChanged.connect(self._mark_has_value)
        layout.addWidget(self.edit, 1)

        clear_btn = QToolButton()
        clear_btn.setObjectName("reportDateClear")
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

    def clear(self) -> None:
        self.edit.blockSignals(True)
        self._has_value = False
        self.edit.setDateTime(QDateTime.currentDateTime())
        self.edit.blockSignals(False)
        self.edit.setStyleSheet("color: #93a1b6;")

    def _mark_has_value(self, _value: QDateTime) -> None:
        self._has_value = True
        self.edit.setStyleSheet("")


class SummaryCard(QFrame):
    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("reportSummaryCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("reportSummaryTitle")
        layout.addWidget(self.title_label)

        self.value_label = QLabel("0")
        self.value_label.setObjectName("reportSummaryValue")
        layout.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class LprReportPage(QWidget):
    navigate = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.toast = PrimeToastHost(self)

        self.auth_store = AuthStore(AuthService())
        self.camera_store = CameraDepartmentStore(CameraService())
        self.report_store = LprReportStore(LprReportService())

        self._loaded_department_id: Optional[int] = None
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
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.content_panel = QFrame()
        self.content_panel.setObjectName("reportContentPanel")
        root.addWidget(self.content_panel, 1)

        content = QVBoxLayout(self.content_panel)
        content.setContentsMargins(18, 18, 18, 18)
        content.setSpacing(12)

        hero_scroll = QScrollArea()
        hero_scroll.setObjectName("reportFiltersScroll")
        hero_scroll.setWidgetResizable(True)
        hero_scroll.setFrameShape(QFrame.Shape.NoFrame)
        hero_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        hero_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        hero_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        hero_scroll.setMaximumHeight(360)
        content.addWidget(hero_scroll)

        hero_frame = QFrame()
        hero_frame.setObjectName("reportHero")
        hero = QVBoxLayout(hero_frame)
        hero.setContentsMargins(18, 18, 18, 18)
        hero.setSpacing(14)
        hero_scroll.setWidget(hero_frame)

        hero_head = QHBoxLayout()
        hero_head.setContentsMargins(0, 0, 0, 0)
        hero_head.setSpacing(8)
        hero.addLayout(hero_head)

        hero_text = QVBoxLayout()
        hero_text.setContentsMargins(0, 0, 0, 0)
        hero_text.setSpacing(4)
        hero_head.addLayout(hero_text, 1)

        hero_title = QLabel("LPR Report")
        hero_title.setObjectName("heroTitle")
        hero_text.addWidget(hero_title)

        hero_hint = QLabel(
            "Generate LPR or monthly reports by date range and selected cameras. "
            "The request matches `/api/v1/report/lpr` with `report_type` set to `lpr` or `monthly`."
        )
        hero_hint.setObjectName("heroHint")
        hero_hint.setWordWrap(True)
        hero_text.addWidget(hero_hint)

        self.filter_state_chip = QLabel("Ready")
        self.filter_state_chip.setObjectName("heroChip")
        hero_head.addWidget(self.filter_state_chip, 0, Qt.AlignmentFlag.AlignTop)

        fields_grid = QGridLayout()
        fields_grid.setContentsMargins(0, 0, 0, 0)
        fields_grid.setHorizontalSpacing(12)
        fields_grid.setVerticalSpacing(12)
        fields_grid.setColumnStretch(0, 1)
        fields_grid.setColumnStretch(1, 1)
        hero.addLayout(fields_grid)

        self.report_type_select = PrimeSelect(placeholder="Select report type")
        self.report_type_select.set_options(
            [
                {"label": "LPR Report", "value": "lpr"},
                {"label": "Monthly Report", "value": "monthly"},
            ]
        )
        self.report_type_select.set_value("lpr")
        fields_grid.addWidget(
            self._hero_field_block(
                "Report Type",
                self.report_type_select,
                "Choose either `lpr` or `monthly` for the API payload.",
            ),
            0,
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
                "Leave empty to report across all cameras available to the current department.",
            ),
            0,
            1,
        )

        self.date_from_field = ReportDateTimeField("Start Time")
        fields_grid.addWidget(
            self._hero_field_block(
                "Start Date & Time",
                self.date_from_field,
                "Required field for the report request.",
            ),
            1,
            0,
        )

        self.date_to_field = ReportDateTimeField("End Time")
        fields_grid.addWidget(
            self._hero_field_block(
                "End Date & Time",
                self.date_to_field,
                "Required field for the report request.",
            ),
            1,
            1,
        )

        hero_actions = QHBoxLayout()
        hero_actions.setContentsMargins(0, 0, 0, 0)
        hero_actions.setSpacing(10)
        hero.addLayout(hero_actions)

        self.reset_btn = PrimeButton("Reset", variant="secondary", size="sm")
        self.reset_btn.clicked.connect(self.reset_filters)
        hero_actions.addWidget(self.reset_btn)

        self.export_btn = PrimeButton("Export CSV", variant="info", size="sm")
        self.export_btn.clicked.connect(self.export_csv)
        hero_actions.addWidget(self.export_btn)

        self.search_btn = PrimeButton("Run Report", variant="primary", size="sm")
        self.search_btn.clicked.connect(self.perform_report)
        hero_actions.addWidget(self.search_btn)
        hero_actions.addStretch(1)

        summary_frame = QFrame()
        summary_frame.setObjectName("reportSummaryWrap")
        summary_layout = QGridLayout(summary_frame)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setHorizontalSpacing(10)
        summary_layout.setVerticalSpacing(10)
        content.addWidget(summary_frame)

        self.summary_rows = SummaryCard("Rows")
        self.summary_records = SummaryCard("Total Records")
        self.summary_unique = SummaryCard("Unique Vehicles")
        self.summary_english = SummaryCard("English Plates")
        self.summary_taxi = SummaryCard("Taxi Plates")
        self.summary_private = SummaryCard("Private Plates")
        self.summary_transport = SummaryCard("Transport Plates")

        cards = [
            self.summary_rows,
            self.summary_records,
            self.summary_unique,
            self.summary_english,
            self.summary_taxi,
            self.summary_private,
            self.summary_transport,
        ]
        for index, card in enumerate(cards):
            summary_layout.addWidget(card, index // 4, index % 4)

        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("reportToolbar")
        toolbar = QHBoxLayout(toolbar_frame)
        toolbar.setContentsMargins(14, 14, 14, 14)
        toolbar.setSpacing(10)
        content.addWidget(toolbar_frame)

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
            QFrame#reportContentPanel {
                background: #171b21;
                border: 1px solid #2b3340;
                border-radius: 16px;
            }
            QFrame#reportHero {
                background: #151920;
                border: 1px solid #2a3140;
                border-radius: 16px;
            }
            QFrame#reportToolbar,
            QFrame#reportSummaryWrap {
                background: #151920;
                border: 1px solid #2a3140;
                border-radius: 14px;
            }
            QLabel#heroTitle {
                color: #f8fafc;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#heroHint,
            QLabel#pageSummary {
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
            QLabel#heroFieldLabel {
                color: #dbe3ef;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#heroFieldHint {
                color: #93a1b6;
                font-size: 11px;
            }
            QWidget#heroFieldBlock {
                background: #11161d;
                border: 1px solid #293241;
                border-radius: 14px;
                padding: 2px;
            }
            QFrame#reportDateField {
                background: #242a33;
                border: 1px solid #364150;
                border-radius: 10px;
            }
            QDateTimeEdit#reportDateEdit {
                background: #242a33;
                border: 1px solid #364150;
                border-radius: 10px;
                color: #eef2f8;
                padding: 8px 10px;
                min-height: 24px;
            }
            QToolButton#reportDateClear {
                background: transparent;
                border: none;
                padding: 0 8px;
            }
            QFrame#reportSummaryCard {
                background: #11161d;
                border: 1px solid #293241;
                border-radius: 14px;
            }
            QLabel#reportSummaryTitle {
                color: #93a1b6;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#reportSummaryValue {
                color: #f8fafc;
                font-size: 20px;
                font-weight: 700;
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

    def _update_summary(self) -> None:
        rows = self.report_store.rows
        self.summary_rows.set_value(str(len(rows)))
        self.summary_records.set_value(str(sum(item.total_records for item in rows)))
        self.summary_unique.set_value(str(sum(item.unique_vehicles for item in rows)))
        self.summary_english.set_value(str(sum(item.english_plates for item in rows)))
        self.summary_taxi.set_value(str(sum(item.taxi_plates for item in rows)))
        self.summary_private.set_value(str(sum(item.private_plates for item in rows)))
        self.summary_transport.set_value(str(sum(item.transport_plates for item in rows)))

    def refresh(self) -> None:
        current_user = self.auth_store.current_user
        department_id = current_user.department_id if current_user is not None else None
        if department_id != self._loaded_department_id:
            self._loaded_department_id = department_id
            self.camera_store.get_camera_for_user(department_id, silent=True)

        self.camera_select.set_options(self._camera_options())
        self.table.set_rows(self._rows())
        self._update_summary()

        busy = self.report_store.loading
        self.search_btn.setEnabled(not busy)
        self.reset_btn.setEnabled(not busy)
        self.export_btn.setEnabled(not busy and bool(self.report_store.rows))

        report_type = self.report_type_select.value() or "lpr"
        self.filter_state_chip.setText(f"Type: {report_type}")
        if busy:
            self.status_label.setText("Loading report results...")
        elif self.report_store.rows:
            self.status_label.setText(f"Loaded {len(self.report_store.rows)} report rows.")
        elif self.has_searched:
            self.status_label.setText("No report rows returned for the current filters.")
        else:
            self.status_label.setText("Choose filters and run the report.")

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
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        p.fillPath(path, QColor(Constants.DARK_BG))   # dark bg — cards float above it
        super().paintEvent(event)


