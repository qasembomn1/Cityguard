from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import Dict, List, Optional

from PySide6.QtCore import QDateTime, QSize, Qt, Signal
from PySide6.QtGui import QIcon
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

from app.models.face.report import FaceReportPayload, FaceReportResult, FaceReportRow
from app.services.auth.auth_service import AuthService
from app.services.home.devices.camera_service import CameraService
from app.services.home.face_report_service import FaceReportService
from app.store.auth.auth_store import AuthStore
from app.store.home.face.face_report_store import FaceReportStore
from app.store.home.user.department_store import DepartmentStore as CameraDepartmentStore
from app.ui.button import PrimeButton
from app.ui.multiselect import PrimeMultiSelect
from app.ui.table import PrimeDataTable, PrimeTableColumn
from app.ui.toast import PrimeToastHost


_ICONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../resources/icons"))


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


def _humanize_key(key: str) -> str:
    custom = {
        "camera_name": "Camera Name",
        "created_at": "Date & Time",
        "face_count": "Face Count",
        "total_count": "Total Count",
        "person_count": "Person Count",
    }
    if key in custom:
        return custom[key]
    return key.replace("_", " ").strip().title() or "Value"


def _column_priority(key: str) -> tuple[int, str]:
    order = {
        "camera_name": 0,
        "created_at": 1,
        "date": 2,
        "month": 3,
        "period": 4,
        "count": 5,
        "total": 6,
        "total_count": 7,
        "face_count": 8,
        "person_count": 9,
    }
    return (order.get(key, 100), key)


def _is_numeric_value(value: object) -> bool:
    if isinstance(value, (int, float)):
        return True
    text = str(value or "").strip()
    if not text:
        return False
    try:
        float(text)
        return True
    except ValueError:
        return False


class ReportDateTimeField(QFrame):
    def __init__(self, placeholder: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("faceReportDateField")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        self.edit = QDateTimeEdit()
        self.edit.setCalendarPopup(True)
        self.edit.setDisplayFormat("yyyy-MM-dd hh:mm AP")
        self.edit.setSpecialValueText(placeholder)
        self.edit.setDateTime(QDateTime.currentDateTime())
        self.edit.setMinimumDateTime(QDateTime.fromSecsSinceEpoch(0))
        self.edit.setObjectName("faceReportDateEdit")
        self.edit.dateTimeChanged.connect(self._mark_has_value)
        layout.addWidget(self.edit, 1)

        clear_btn = QToolButton()
        clear_btn.setObjectName("faceReportDateClear")
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


class BaseFaceReportPage(QWidget):
    navigate = Signal(str)

    def __init__(
        self,
        endpoint: str,
        title: str,
        hint: str,
        export_prefix: str,
        toast_title: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.endpoint = endpoint
        self.title_text = title
        self.hint_text = hint
        self.export_prefix = export_prefix
        self.toast_title = toast_title
        self.toast = PrimeToastHost(self)

        self.auth_store = AuthStore(AuthService())
        self.camera_store = CameraDepartmentStore(CameraService())
        self.report_store = FaceReportStore(FaceReportService(endpoint))

        self._loaded_department_id: Optional[int] = None
        self.has_searched = False
        self._column_keys: List[str] = []

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
        self.content_panel.setObjectName("faceReportContentPanel")
        root.addWidget(self.content_panel, 1)

        content = QVBoxLayout(self.content_panel)
        content.setContentsMargins(18, 18, 18, 18)
        content.setSpacing(12)

        hero_scroll = QScrollArea()
        hero_scroll.setObjectName("faceReportFiltersScroll")
        hero_scroll.setWidgetResizable(True)
        hero_scroll.setFrameShape(QFrame.Shape.NoFrame)
        hero_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        hero_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        hero_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        hero_scroll.setMaximumHeight(320)
        content.addWidget(hero_scroll)

        hero_frame = QFrame()
        hero_frame.setObjectName("faceReportHero")
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

        hero_title = QLabel(self.title_text)
        hero_title.setObjectName("heroTitle")
        hero_text.addWidget(hero_title)

        hero_hint = QLabel(self.hint_text)
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

        self.date_from_field = ReportDateTimeField("Start Time")
        fields_grid.addWidget(
            self._hero_field_block(
                "Start Date & Time",
                self.date_from_field,
                "Required field for the report request.",
            ),
            0,
            0,
        )

        self.date_to_field = ReportDateTimeField("End Time")
        fields_grid.addWidget(
            self._hero_field_block(
                "End Date & Time",
                self.date_to_field,
                "Required field for the report request.",
            ),
            0,
            1,
        )

        self.camera_select = PrimeMultiSelect(options=[], placeholder="Select Camera")
        self.camera_select.setMinimumWidth(0)
        self.camera_select.setMaximumWidth(16777215)
        self.camera_select.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        fields_grid.addWidget(
            self._hero_field_block(
                "Camera",
                self.camera_select,
                "Leave empty to query all available cameras for the current department.",
            ),
            1,
            0,
            1,
            2,
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

        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("faceReportToolbar")
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
        self._set_table_columns([])
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
            QFrame#faceReportContentPanel {
                background: #171b21;
                border: 1px solid #2b3340;
                border-radius: 16px;
            }
            QFrame#faceReportHero,
            QFrame#faceReportToolbar {
                background: #151920;
                border: 1px solid #2a3140;
                border-radius: 16px;
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
                background: rgba(16, 185, 129, 0.16);
                border: 1px solid rgba(52, 211, 153, 0.35);
                color: #d1fae5;
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
            QFrame#faceReportDateField {
                background: #242a33;
                border: 1px solid #364150;
                border-radius: 10px;
            }
            QDateTimeEdit#faceReportDateEdit {
                background: #242a33;
                border: 1px solid #364150;
                border-radius: 10px;
                color: #eef2f8;
                padding: 8px 10px;
                min-height: 24px;
            }
            QToolButton#faceReportDateClear {
                background: transparent;
                border: none;
                padding: 0 8px;
            }
            """
        )

    def _camera_options(self) -> List[dict]:
        return [
            {"label": camera.name or f"Camera #{camera.id}", "value": camera.id}
            for camera in self.camera_store.cameras
            if int(camera.id or 0) > 0
        ]

    def _collect_column_keys(self) -> List[str]:
        ordered: List[str] = []
        seen: set[str] = set()
        for row in self.report_store.rows:
            for key in row.values.keys():
                if key not in seen:
                    seen.add(key)
                    ordered.append(key)
        ordered.sort(key=_column_priority)
        return ordered

    def _set_table_columns(self, keys: List[str]) -> None:
        self._column_keys = list(keys)
        columns: List[PrimeTableColumn] = []
        for key in self._column_keys:
            sample_value = next((row.values.get(key) for row in self.report_store.rows if key in row.values), "")
            alignment = Qt.AlignCenter | Qt.AlignVCenter if _is_numeric_value(sample_value) else Qt.AlignLeft | Qt.AlignVCenter
            columns.append(
                PrimeTableColumn(
                    key,
                    _humanize_key(key),
                    stretch=True,
                    alignment=alignment,
                )
            )
        if not columns:
            columns = [PrimeTableColumn("message", "Result", stretch=True, sortable=False)]
        self.table.set_columns(columns)

    def _table_rows(self) -> List[Dict[str, object]]:
        if not self.report_store.rows:
            if self.report_store.message:
                return [{"message": self.report_store.message}]
            return []
        rows: List[Dict[str, object]] = []
        for item in self.report_store.rows:
            row = {key: item.values.get(key, "") for key in self._column_keys}
            row["_entry"] = item
            rows.append(row)
        return rows

    def refresh(self) -> None:
        current_user = self.auth_store.current_user
        department_id = current_user.department_id if current_user is not None else None
        if department_id != self._loaded_department_id:
            self._loaded_department_id = department_id
            self.camera_store.get_camera_for_user(department_id, silent=True)

        self.camera_select.set_options(self._camera_options())
        self._set_table_columns(self._collect_column_keys())
        self.table.set_rows(self._table_rows())

        busy = self.report_store.loading
        self.search_btn.setEnabled(not busy)
        self.reset_btn.setEnabled(not busy)
        self.export_btn.setEnabled(not busy and bool(self.report_store.rows))
        self.filter_state_chip.setText(f"Rows: {len(self.report_store.rows)}")

        if busy:
            self.status_label.setText("Loading report results...")
        elif self.report_store.rows:
            self.status_label.setText(f"Loaded {len(self.report_store.rows)} report rows.")
        elif self.has_searched and self.report_store.message:
            self.status_label.setText(self.report_store.message)
        elif self.has_searched:
            self.status_label.setText("No report rows returned for the current filters.")
        else:
            self.status_label.setText("Choose filters and run the report.")

    def _validate_payload(self) -> Optional[FaceReportPayload]:
        date_from = self.date_from_field.value()
        date_to = self.date_to_field.value()
        if date_from is None or date_to is None:
            self._show_error("Please select both start and end dates.")
            return None
        if date_from > date_to:
            self._show_error("Start date must be before end date.")
            return None
        return FaceReportPayload(
            date_from=date_from,
            date_to=date_to,
            camera_ids=self.camera_select.value(),
        )

    def reset_filters(self) -> None:
        self.has_searched = False
        self.date_from_field.clear()
        self.date_to_field.clear()
        self.camera_select.set_value([])
        self.report_store.clear()

    def perform_report(self) -> None:
        payload = self._validate_payload()
        if payload is None:
            return
        self.has_searched = True
        result = self.report_store.search(payload)
        if result.rows:
            self.toast.success(self.toast_title, f"Loaded {len(result.rows)} report rows.")
        elif result.message:
            self.toast.success(self.toast_title, result.message)

    def export_csv(self) -> None:
        if not self.report_store.rows:
            self._show_error("No report data available to export.")
            return

        default_name = f"{self.export_prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
        suggested = os.path.join(os.path.expanduser("~"), default_name)
        path, _ = QFileDialog.getSaveFileName(self, f"Export {self.title_text}", suggested, "CSV Files (*.csv)")
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow([_humanize_key(key) for key in self._column_keys])
                for item in self.report_store.rows:
                    writer.writerow([item.values.get(key, "") for key in self._column_keys])
            self.toast.success(self.toast_title, f"Exported report to {path}.")
        except Exception as exc:
            self._show_error(str(exc))

    def _show_error(self, text: str) -> None:
        self.toast.error(self.toast_title, text)


class FaceReportPage(BaseFaceReportPage):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            endpoint="/api/v1/face_report/report",
            title="Face Report",
            hint=(
                "Run the face report using a top filter panel, not a sidebar. "
                "This posts `date_from`, `date_to`, and `camera_ids` to `/api/v1/face_report/report`."
            ),
            export_prefix="face-report",
            toast_title="Face Report",
            parent=parent,
        )
