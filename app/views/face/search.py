from __future__ import annotations

import csv
import os
import sys
import urllib.parse
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtNetwork import QNetworkAccessManager
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models.face.search import FaceEmbeddingResult, FaceSearchPayload, FaceSearchResult
from app.services.auth.auth_service import AuthService
from app.services.home.devices.camera_service import CameraService
from app.services.home.face_blacklist_service import FaceBlacklistService
from app.services.home.face_search_service import FaceSearchService
from app.services.home.face_whitelist_service import FaceWhitelistService
from app.store.auth.auth_store import AuthStore
from app.store.home.face.face_search_store import FaceSearchStore
from app.store.home.user.department_store import DepartmentStore as CameraDepartmentStore
from app.ui.multiselect import PrimeMultiSelect
from app.ui.table import PrimeDataTable, PrimeTableColumn
from app.ui.toast import PrimeToastHost
from app.views.face.whitelist import RemoteImageLabel
from app.views.lpr.search import ClearableDateTimeField, FilterAccordionSection, SEARCH_TIMEZONE


_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


def _base_http_url() -> str:
    raw = os.getenv("Base_URL", "http://192.168.100.120:8800").strip().rstrip("/")
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return f"http://{raw}"


def _absolute_image_url(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered.startswith(("http://", "https://", "data:image/")):
        return text
    if text.startswith("/"):
        return f"{_base_http_url()}{text}"
    if text.startswith("api/"):
        return f"{_base_http_url()}/{text}"
    return ""


def _media_base(record: FaceSearchResult) -> str:
    if record.ip and int(record.port or 0) > 0:
        return f"http://{record.ip}:{int(record.port)}"
    return _base_http_url()


def _quoted_filename(filename: str) -> str:
    return urllib.parse.quote(os.path.basename(str(filename or "").strip()))


def _face_full_url(record: FaceSearchResult) -> str:
    for candidate in (record.face_url, record.image_url):
        direct = _absolute_image_url(candidate)
        if direct:
            return direct

    filename = os.path.basename(str(record.filename or "").strip())
    if not filename or int(record.camera_id or 0) <= 0:
        return ""
    return f"{_media_base(record)}/image/{int(record.camera_id)}/{_quoted_filename(filename)}"


def _face_crop_url(record: FaceSearchResult) -> str:
    direct_crop = _absolute_image_url(record.crop_image_url)
    if direct_crop:
        return direct_crop

    filename = os.path.basename(str(record.filename or "").strip())
    special_face_file = record.record_type == "face_result" or filename.startswith("face_")

    direct_image = _absolute_image_url(record.image_url)
    if direct_image and special_face_file:
        return direct_image

    if not filename or int(record.camera_id or 0) <= 0:
        return direct_image or _face_full_url(record)

    crop_name = filename if special_face_file or filename.startswith("crop_") else f"crop_{filename}"
    return f"{_media_base(record)}/image/{int(record.camera_id)}/{urllib.parse.quote(crop_name)}"


COLOR_OPTIONS = [
    {"label": "White", "value": "White"},
    {"label": "Black", "value": "Black"},
    {"label": "Silver", "value": "Silver"},
    {"label": "Gray", "value": "Gray"},
    {"label": "Blue", "value": "Blue"},
    {"label": "Red", "value": "Red"},
    {"label": "Green", "value": "Green"},
    {"label": "Yellow", "value": "Yellow"},
    {"label": "Orange", "value": "Orange"},
    {"label": "Brown", "value": "Brown"},
]

GRID_OPTIONS = [2, 3, 4]
ROWS_PER_PAGE_OPTIONS = [10, 20, 50, 100]


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            _clear_layout(child_layout)


class FaceSearchWorker(QThread):
    finished_rows = Signal(list)
    failed_text = Signal(str)

    def __init__(self, payload: Dict[str, object], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._payload = dict(payload)

    def run(self) -> None:
        try:
            results = FaceSearchService().search_faces(FaceSearchPayload(**self._payload))
        except Exception as exc:
            self.failed_text.emit(str(exc))
            return
        self.finished_rows.emit(results)


class FaceWatchlistDialog(QDialog):
    def __init__(
        self,
        title_text: str,
        action_text: str,
        preview_url: str,
        embedding_result: FaceEmbeddingResult,
        record: FaceSearchResult,
        camera_options: List[dict],
        auth_token: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.toast = PrimeToastHost(self)
        self._embedding_result = embedding_result
        self._record = record
        self._camera_options = list(camera_options)
        self.setWindowTitle(title_text)
        self.resize(560, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel(title_text)
        title.setObjectName("watchlistDialogTitle")
        root.addWidget(title)

        hint = QLabel("Review the generated values, then save this face into the selected list.")
        hint.setObjectName("watchlistDialogHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.preview = RemoteImageLabel(QNetworkAccessManager(self), fallback_text="No Face", auth_token=auth_token)
        self.preview.setMinimumHeight(180)
        self.preview.setMaximumHeight(180)
        self.preview.setStyleSheet(
            "background:#0f141a;border:1px dashed #38506d;border-radius:16px;color:#93a1b6;"
        )
        self.preview.set_image_url(preview_url)
        root.addWidget(self.preview)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll, 1)

        body = QWidget()
        scroll.setWidget(body)
        form = QVBoxLayout(body)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(12)

        self.name_edit = QLineEdit(f"Face_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        form.addWidget(self._field_block("Name", self.name_edit))

        colors_grid = QGridLayout()
        colors_grid.setContentsMargins(0, 0, 0, 0)
        colors_grid.setHorizontalSpacing(10)
        colors_grid.setVerticalSpacing(12)
        form.addLayout(colors_grid)

        self.face_color_edit = QLineEdit(record.top_color_text if record.top_color_text != "-" else "")
        colors_grid.addWidget(self._field_block("Face Color", self.face_color_edit), 0, 0)

        self.hair_color_edit = QLineEdit(record.bottom_color_text if record.bottom_color_text != "-" else "")
        colors_grid.addWidget(self._field_block("Hair Color", self.hair_color_edit), 0, 1)

        self.age_spin = QSpinBox()
        self.age_spin.setRange(0, 150)
        self.age_spin.setSpecialValueText("Unset")
        self.age_spin.setValue(int(record.age or 0))
        colors_grid.addWidget(self._field_block("Age", self.age_spin), 1, 0)

        self.gender_combo = QComboBox()
        self.gender_combo.addItem("Unset", "")
        self.gender_combo.addItem("Male", "Male")
        self.gender_combo.addItem("Female", "Female")
        gender_index = self.gender_combo.findData(record.gender or "")
        self.gender_combo.setCurrentIndex(gender_index if gender_index >= 0 else 0)
        colors_grid.addWidget(self._field_block("Gender", self.gender_combo), 1, 1)

        self.match_spin = QDoubleSpinBox()
        self.match_spin.setRange(0.0, 100.0)
        self.match_spin.setDecimals(2)
        self.match_spin.setSuffix(" %")
        self.match_spin.setSingleStep(1.0)
        self.match_spin.setValue(70.0)
        form.addWidget(self._field_block("Match Threshold", self.match_spin))

        self.camera_list = QListWidget()
        self.camera_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.camera_list.setMinimumHeight(132)
        self.camera_list.setMaximumHeight(180)
        self._load_camera_items()
        self._set_selected_camera_ids([record.camera_id] if int(record.camera_id or 0) > 0 else [])
        form.addWidget(self._field_block("Cameras", self.camera_list))

        self.note_edit = QTextEdit()
        self.note_edit.setMinimumHeight(92)
        self.note_edit.setPlainText(
            f"Added from face search on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}."
        )
        form.addWidget(self._field_block("Note", self.note_edit))

        footer = QHBoxLayout()
        footer.setSpacing(8)
        root.addLayout(footer)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("watchlistGhostButton")
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        save_btn = QPushButton(action_text)
        save_btn.setObjectName("watchlistPrimaryButton")
        save_btn.clicked.connect(self._submit)
        footer.addWidget(save_btn)

        self.setStyleSheet(
            """
            QDialog {
                background: #171b21;
                color: #eef2f8;
            }
            QLabel#watchlistDialogTitle {
                color: #f8fafc;
                font-size: 22px;
                font-weight: 800;
            }
            QLabel#watchlistDialogHint {
                color: #93a1b6;
                font-size: 13px;
            }
            QLabel#watchlistFieldLabel {
                color: #d8e1ee;
                font-size: 12px;
                font-weight: 700;
            }
            QLineEdit, QTextEdit, QComboBox, QListWidget, QSpinBox, QDoubleSpinBox {
                background: #242a33;
                border: 1px solid #364150;
                border-radius: 10px;
                color: #eef2f8;
                padding: 8px 12px;
                min-height: 24px;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background: #35507f;
                color: #f8fafc;
            }
            QPushButton#watchlistPrimaryButton, QPushButton#watchlistGhostButton {
                min-height: 40px;
                border-radius: 11px;
                font-weight: 700;
                padding: 0 18px;
            }
            QPushButton#watchlistPrimaryButton {
                background: #2563eb;
                border: none;
                color: white;
            }
            QPushButton#watchlistPrimaryButton:hover {
                background: #1d4ed8;
            }
            QPushButton#watchlistGhostButton {
                background: #27303d;
                border: 1px solid #374151;
                color: #e5e7eb;
            }
            QPushButton#watchlistGhostButton:hover {
                background: #313b4a;
            }
            """
        )

    def _field_block(self, label_text: str, field: QWidget) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(label_text)
        label.setObjectName("watchlistFieldLabel")
        layout.addWidget(label)
        layout.addWidget(field)
        return wrapper

    def _load_camera_items(self) -> None:
        self.camera_list.clear()
        for option in self._camera_options:
            value = option.get("value")
            if value is None:
                continue
            try:
                camera_id = int(value)
            except (TypeError, ValueError):
                continue
            item = QListWidgetItem(str(option.get("label") or camera_id))
            item.setData(Qt.ItemDataRole.UserRole, camera_id)
            self.camera_list.addItem(item)

    def _set_selected_camera_ids(self, camera_ids: List[int]) -> None:
        selected = {int(item) for item in camera_ids if int(item) > 0}
        for row in range(self.camera_list.count()):
            item = self.camera_list.item(row)
            item.setSelected(int(item.data(Qt.ItemDataRole.UserRole) or 0) in selected)

    def _selected_camera_ids(self) -> List[int]:
        values: List[int] = []
        for item in self.camera_list.selectedItems():
            camera_id = int(item.data(Qt.ItemDataRole.UserRole) or 0)
            if camera_id > 0:
                values.append(camera_id)
        return values

    def payload(self) -> Dict[str, Any]:
        age_value = self.age_spin.value()
        return {
            "name": self.name_edit.text().strip(),
            "embedding": self._embedding_result.embedding,
            "face": self._embedding_result.image_url,
            "crop_face": self._embedding_result.crop_image_url,
            "hair_color": self.hair_color_edit.text().strip(),
            "face_color": self.face_color_edit.text().strip(),
            "age": age_value if age_value > 0 else None,
            "gender": str(self.gender_combo.currentData() or "").strip(),
            "match": float(self.match_spin.value()),
            "similarity": float(self.match_spin.value()),
            "camera_ids": self._selected_camera_ids(),
            "note": self.note_edit.toPlainText().strip(),
        }

    def _submit(self) -> None:
        if not self.name_edit.text().strip():
            self.toast.warn("Validation", "Name is required.")
            return
        self.accept()


class FaceResultCard(QFrame):
    opened = Signal(object)
    search_requested = Signal(object)

    def __init__(
        self,
        record: FaceSearchResult,
        net: QNetworkAccessManager,
        auth_token: str = "",
        compact: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.record = record
        self.setObjectName("faceCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        media_card = QFrame()
        media_card.setObjectName("faceCardMedia")
        media_layout = QHBoxLayout(media_card)
        media_layout.setContentsMargins(12, 12, 12, 12)
        media_layout.setSpacing(10)
        root.addWidget(media_card)

        self.full_image = RemoteImageLabel(net, fallback_text="No Frame", auth_token=auth_token)
        frame_height = 126 if compact else 172
        self.full_image.setMinimumHeight(frame_height)
        self.full_image.setMaximumHeight(frame_height)
        self.full_image.setStyleSheet(
            "background:#050a12;border:1px solid #243244;border-radius:14px;color:#64748b;"
        )
        media_layout.addWidget(self.full_image, 1)

        self.crop_image = RemoteImageLabel(net, fallback_text="No Face", auth_token=auth_token)
        self.crop_image.setMinimumSize(112, frame_height)
        self.crop_image.setMaximumWidth(120)
        self.crop_image.setStyleSheet(
            "background:#050a12;border:1px solid #243244;border-radius:14px;color:#64748b;"
        )
        media_layout.addWidget(self.crop_image, 0)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        root.addLayout(header)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        header.addLayout(text_col, 1)

        eyebrow = QLabel("FACE MATCH")
        eyebrow.setObjectName("faceCardEyebrow")
        text_col.addWidget(eyebrow)

        title = QLabel(record.gender or "Unknown")
        title.setObjectName("faceCardTitle")
        if compact:
            title.setStyleSheet("font-size:16px;")
        text_col.addWidget(title)

        chip = QLabel(record.similarity_text if record.similarity_text != "-" else "Face")
        chip.setObjectName("faceCardChip")
        header.addWidget(chip, 0, Qt.AlignmentFlag.AlignTop)

        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(6)
        if record.age is not None:
            badge_row.addWidget(self._badge(f"Age {record.age}", "neutral"))
        if record.top_color_text != "-":
            badge_row.addWidget(self._badge(f"Top {record.top_color_text}", "accent"))
        if record.bottom_color_text != "-":
            badge_row.addWidget(self._badge(f"Bottom {record.bottom_color_text}", "muted"))
        if record.is_blacklist:
            badge_row.addWidget(self._badge("Blacklist", "danger"))
        elif record.is_whitelist:
            badge_row.addWidget(self._badge("Whitelist", "success"))
        badge_row.addStretch(1)
        root.addLayout(badge_row)

        facts = QFrame()
        facts.setObjectName("faceCardFacts")
        facts_layout = QVBoxLayout(facts)
        facts_layout.setContentsMargins(12, 10, 12, 10)
        facts_layout.setSpacing(8)
        facts_layout.addLayout(self._info_row("Camera", record.camera_name or "Unknown Camera"))
        facts_layout.addLayout(self._info_row("Detected", record.created_text))
        root.addWidget(facts)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 2, 0, 0)
        actions.setSpacing(8)
        root.addLayout(actions)

        details_btn = QPushButton("Details")
        details_btn.setObjectName("faceCardAction")
        details_btn.clicked.connect(lambda: self.opened.emit(self.record))
        actions.addWidget(details_btn, 1)

        search_btn = QPushButton("Search Similar")
        search_btn.setObjectName("faceCardGhostAction")
        search_btn.clicked.connect(lambda: self.search_requested.emit(self.record))
        actions.addWidget(search_btn, 1)

        self.full_image.set_image_url(_face_full_url(record))
        self.crop_image.set_image_url(_face_crop_url(record))

    def _badge(self, text: str, tone: str) -> QLabel:
        badge = QLabel(text)
        badge.setObjectName(f"faceCardBadge{tone.capitalize()}")
        return badge

    def _info_row(self, label_text: str, value_text: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        label = QLabel(label_text)
        label.setObjectName("faceCardFactLabel")
        row.addWidget(label, 0)
        value = QLabel(value_text)
        value.setObjectName("faceCardFactValue")
        value.setWordWrap(True)
        row.addWidget(value, 1)
        return row

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.opened.emit(self.record)
            event.accept()
            return
        super().mousePressEvent(event)


class FaceDetailDialog(QDialog):
    search_requested = Signal(object)
    blacklist_requested = Signal(object)
    whitelist_requested = Signal(object)

    def __init__(
        self,
        record: FaceSearchResult,
        net: QNetworkAccessManager,
        auth_token: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.record = record
        self.setWindowTitle("Face Details")
        self.resize(1120, 780)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        root.addLayout(grid, 1)

        full_card = self._image_card("Full Camera Frame", net, _face_full_url(record), "No Frame", auth_token, 360)
        grid.addWidget(full_card, 0, 0, 2, 2)

        crop_card = self._image_card("Face Crop", net, _face_crop_url(record), "No Face", auth_token, 220)
        grid.addWidget(crop_card, 0, 2, 1, 1)

        gender_card = QFrame()
        gender_card.setObjectName("detailHighlightCard")
        gender_layout = QVBoxLayout(gender_card)
        gender_layout.setContentsMargins(18, 18, 18, 18)
        gender_layout.setSpacing(8)
        gender_title = QLabel("Gender")
        gender_title.setObjectName("detailMuted")
        gender_value = QLabel(record.gender or "Unknown")
        gender_value.setObjectName("detailHeroValue")
        gender_layout.addWidget(gender_title)
        gender_layout.addWidget(gender_value)
        gender_layout.addStretch(1)
        grid.addWidget(gender_card, 1, 2, 1, 1)

        info_card = QFrame()
        info_card.setObjectName("detailInfoCard")
        info_layout = QGridLayout(info_card)
        info_layout.setContentsMargins(18, 18, 18, 18)
        info_layout.setHorizontalSpacing(14)
        info_layout.setVerticalSpacing(14)

        info_items = [
            ("Camera", record.camera_name or "Unknown"),
            ("Age", str(record.age) if record.age is not None else "Unset"),
            ("Similarity", record.similarity_text),
            ("Detected At", record.created_text),
            ("Top Color", record.top_color_text),
            ("Bottom Color", record.bottom_color_text),
            ("Blacklist", "Yes" if record.is_blacklist else "No"),
            ("Whitelist", "Yes" if record.is_whitelist else "No"),
        ]
        for index, (label_text, value_text) in enumerate(info_items):
            card = QFrame()
            card.setObjectName("detailMetricCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)
            label = QLabel(label_text)
            label.setObjectName("detailMuted")
            value = QLabel(value_text)
            value.setObjectName("detailMetricValue")
            value.setWordWrap(True)
            card_layout.addWidget(label)
            card_layout.addWidget(value)
            info_layout.addWidget(card, index // 4, index % 4)
        root.addWidget(info_card)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        root.addLayout(buttons)

        search_btn = QPushButton("Search Similar")
        search_btn.setObjectName("detailPrimaryButton")
        search_btn.clicked.connect(lambda: self.search_requested.emit(self.record))
        buttons.addWidget(search_btn, 1)

        blacklist_btn = QPushButton("Blacklist")
        blacklist_btn.setObjectName("detailDangerButton")
        blacklist_btn.clicked.connect(lambda: self.blacklist_requested.emit(self.record))
        buttons.addWidget(blacklist_btn, 0)

        whitelist_btn = QPushButton("Whitelist")
        whitelist_btn.setObjectName("detailSuccessButton")
        whitelist_btn.clicked.connect(lambda: self.whitelist_requested.emit(self.record))
        buttons.addWidget(whitelist_btn, 0)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("detailGhostButton")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn, 0)

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
                color: #f8fafc;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#detailMuted {
                color: #94a3b8;
                font-size: 12px;
            }
            QLabel#detailHeroValue {
                color: #34d399;
                font-size: 28px;
                font-weight: 800;
            }
            QLabel#detailMetricValue {
                color: #f8fafc;
                font-size: 14px;
                font-weight: 700;
            }
            QPushButton#detailPrimaryButton, QPushButton#detailGhostButton,
            QPushButton#detailDangerButton, QPushButton#detailSuccessButton {
                border-radius: 12px;
                min-height: 42px;
                font-size: 13px;
                font-weight: 700;
                padding: 0 18px;
            }
            QPushButton#detailPrimaryButton {
                background: #2563eb;
                border: none;
                color: white;
            }
            QPushButton#detailPrimaryButton:hover {
                background: #1d4ed8;
            }
            QPushButton#detailDangerButton {
                background: #991b1b;
                border: 1px solid #ef4444;
                color: #fee2e2;
            }
            QPushButton#detailDangerButton:hover {
                background: #b91c1c;
            }
            QPushButton#detailSuccessButton {
                background: #14532d;
                border: 1px solid #22c55e;
                color: #dcfce7;
            }
            QPushButton#detailSuccessButton:hover {
                background: #166534;
            }
            QPushButton#detailGhostButton {
                background: #27303d;
                border: 1px solid #3a4555;
                color: #e2e8f0;
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
        auth_token: str,
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

        image = RemoteImageLabel(net, fallback_text=fallback_text, auth_token=auth_token)
        image.setMinimumHeight(minimum_height)
        image.setStyleSheet(
            "background:#090d12;border:1px solid #1f2937;border-radius:14px;color:#64748b;"
        )
        image.set_image_url(image_url)
        layout.addWidget(image, 1)
        return frame


class FaceSearchPage(QWidget):
    navigate = Signal(str)

    def __init__(
        self,
        auth_store: Optional[AuthStore] = None,
        camera_store: Optional[CameraDepartmentStore] = None,
        search_store: Optional[FaceSearchStore] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.toast = PrimeToastHost(self)
        self.auth_store = auth_store or AuthStore(AuthService())
        self.camera_store = camera_store or CameraDepartmentStore(CameraService())
        self.search_store = search_store or FaceSearchStore(FaceSearchService())
        self.net = QNetworkAccessManager(self)

        self.filter_panel_open = False
        self.filters_window_visible = True
        self.grid_view = True
        self.grid_columns = 3
        self.rows_per_page = 20
        self.current_page = 0
        self.has_searched = False
        self.search_in_progress = False
        self._search_thread: Optional[FaceSearchWorker] = None
        self._filter_sections: list[FilterAccordionSection] = []
        self._reference_embedding: Any = ""

        self.auth_store.changed.connect(self._on_auth_changed)
        self.auth_store.error.connect(self._show_error)
        self.camera_store.changed.connect(self._refresh_camera_options)
        self.camera_store.error.connect(self._show_error)
        self.search_store.changed.connect(self.refresh)
        self.search_store.error.connect(self._show_error)

        self._build_ui()
        self._apply_style()
        self._apply_default_date_range()
        self.set_view_mode(self.grid_view)

        self.auth_store.load()
        self.camera_store.get_camera_for_user(None, silent=True)

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(0)

        self.date_from_input = ClearableDateTimeField("Start Time")
        self.date_to_input = ClearableDateTimeField("End Time")

        self.reference_section = FilterAccordionSection(
            "Reference Face",
            "Upload a face image to get an embedding and search similar records.",
            expanded=False,
        )
        self._filter_sections.append(self.reference_section)
        ref_layout = self.reference_section.body_layout

        self.reference_preview = RemoteImageLabel(self.net, fallback_text="Upload a face image", auth_token=self._auth_token())
        self.reference_preview.setMinimumHeight(176)
        self.reference_preview.setMaximumHeight(176)
        self.reference_preview.setStyleSheet(
            "background:#0d1524;border:1px dashed #4a6288;border-radius:16px;color:#bfdbfe;"
        )
        ref_layout.addWidget(self.reference_preview)

        ref_actions = QHBoxLayout()
        ref_actions.setContentsMargins(0, 0, 0, 0)
        ref_actions.setSpacing(8)
        ref_layout.addLayout(ref_actions)

        self.upload_btn = QPushButton("Upload Face")
        self.upload_btn.setObjectName("secondarySidebarButton")
        self.upload_btn.clicked.connect(self._choose_reference_image)
        ref_actions.addWidget(self.upload_btn)

        self.clear_reference_btn = QPushButton("Clear")
        self.clear_reference_btn.setObjectName("secondarySidebarButton")
        self.clear_reference_btn.clicked.connect(self._clear_reference_face)
        ref_actions.addWidget(self.clear_reference_btn)

        ref_actions.addStretch(1)

        self.reference_status = QLabel("No face reference selected.")
        self.reference_status.setObjectName("referenceStatus")
        self.reference_status.setWordWrap(True)
        ref_layout.addWidget(self.reference_status)

        self.attributes_section = FilterAccordionSection(
            "Face Attributes",
            "Refine by gender, age range, colors, and match percentage.",
            expanded=False,
        )
        self._filter_sections.append(self.attributes_section)
        attr_layout = self.attributes_section.body_layout

        attr_grid = QGridLayout()
        attr_grid.setContentsMargins(0, 0, 0, 0)
        attr_grid.setHorizontalSpacing(10)
        attr_grid.setVerticalSpacing(12)
        attr_layout.addLayout(attr_grid)

        self.gender_combo = self._combo_box()
        self.gender_combo.addItem("Any Gender", "")
        self.gender_combo.addItem("Male", "Male")
        self.gender_combo.addItem("Female", "Female")
        attr_grid.addWidget(self._field_block("Gender", self.gender_combo), 0, 0)

        self.match_spin = QDoubleSpinBox()
        self.match_spin.setRange(1.0, 100.0)
        self.match_spin.setDecimals(0)
        self.match_spin.setSingleStep(1.0)
        self.match_spin.setSuffix("%")
        self.match_spin.setValue(70.0)
        attr_grid.addWidget(self._field_block("Match", self.match_spin), 0, 1)

        self.age_from_spin = QSpinBox()
        self.age_from_spin.setRange(0, 150)
        self.age_from_spin.setValue(1)
        attr_grid.addWidget(self._field_block("Age From", self.age_from_spin), 1, 0)

        self.age_to_spin = QSpinBox()
        self.age_to_spin.setRange(0, 150)
        self.age_to_spin.setValue(100)
        attr_grid.addWidget(self._field_block("Age To", self.age_to_spin), 1, 1)

        self.top_color_select = PrimeMultiSelect(COLOR_OPTIONS, placeholder="Select Top Colors")
        attr_layout.addWidget(self._field_block("Top Color", self.top_color_select))

        self.bottom_color_select = PrimeMultiSelect(COLOR_OPTIONS, placeholder="Select Bottom Colors")
        attr_layout.addWidget(self._field_block("Bottom Color", self.bottom_color_select))

        source_section = FilterAccordionSection(
            "Source And Status",
            "Limit the search to selected cameras or only blacklist or whitelist detections.",
            expanded=False,
        )
        self._filter_sections.append(source_section)
        source_layout = source_section.body_layout

        self.camera_select = PrimeMultiSelect([], placeholder="Select Cameras")
        source_layout.addWidget(self._field_block("Camera", self.camera_select))

        checks = QHBoxLayout()
        checks.setSpacing(12)
        self.blacklist_check = QCheckBox("In Blacklist")
        self.whitelist_check = QCheckBox("In Whitelist")
        checks.addWidget(self.blacklist_check, 1)
        checks.addWidget(self.whitelist_check, 1)
        source_layout.addLayout(checks)

        main_panel = QFrame()
        main_panel.setObjectName("resultsPanel")
        main_layout = QVBoxLayout(main_panel)
        main_layout.setContentsMargins(18, 16, 18, 18)
        main_layout.setSpacing(14)
        root.addWidget(main_panel, 1)

        self.hero_scroll = QScrollArea()
        self.hero_scroll.setObjectName("filtersScroll")
        self.hero_scroll.setWidgetResizable(True)
        self.hero_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.hero_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.hero_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.hero_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.hero_scroll.setMinimumHeight(0)
        main_layout.addWidget(self.hero_scroll)

        hero_frame = QFrame()
        hero_frame.setObjectName("searchHero")
        self.hero_frame = hero_frame
        hero_layout = QVBoxLayout(hero_frame)
        hero_layout.setContentsMargins(18, 18, 18, 18)
        hero_layout.setSpacing(14)
        self.hero_scroll.setWidget(hero_frame)

        hero_head = QHBoxLayout()
        hero_head.setContentsMargins(0, 0, 0, 0)
        hero_head.setSpacing(8)
        hero_layout.addLayout(hero_head)

        hero_text = QVBoxLayout()
        hero_text.setContentsMargins(0, 0, 0, 0)
        hero_text.setSpacing(4)
        hero_head.addLayout(hero_text, 1)

        hero_title = QLabel("Face Search Window")
        hero_title.setObjectName("heroTitle")
        hero_text.addWidget(hero_title)

        hero_hint = QLabel(
            "Search by time range and face reference. Open advanced filters only when you need to narrow the results."
        )
        hero_hint.setObjectName("heroHint")
        hero_hint.setWordWrap(True)
        hero_text.addWidget(hero_hint)

        self.filter_state_chip = QLabel("Quick search")
        self.filter_state_chip.setObjectName("heroChip")
        hero_head.addWidget(self.filter_state_chip, 0, Qt.AlignmentFlag.AlignTop)

        time_band = FilterAccordionSection(
            "Time Range",
            "These date pickers control which face records are searched.",
            expanded=False,
        )
        self._filter_sections.append(time_band)
        time_layout = QGridLayout()
        time_layout.setContentsMargins(0, 0, 0, 0)
        time_layout.setHorizontalSpacing(12)
        time_layout.setVerticalSpacing(10)
        time_band.body_layout.addLayout(time_layout)
        time_layout.addWidget(
            self._hero_field_block("Start Date & Time", self.date_from_input, "Search from this timestamp."),
            0,
            0,
        )
        time_layout.addWidget(
            self._hero_field_block("End Date & Time", self.date_to_input, "Search until this timestamp."),
            0,
            1,
        )
        hero_layout.addWidget(time_band)
        hero_layout.addWidget(self.reference_section)
        hero_layout.addWidget(self.attributes_section)
        hero_layout.addWidget(source_section)

        for section in self._filter_sections:
            section.toggled.connect(self._sync_filter_toggle_ui)

        self.reset_btn = QPushButton("Reset Filters")
        self.reset_btn.setObjectName("secondarySidebarButton")
        self.reset_btn.setMinimumWidth(154)
        self.reset_btn.clicked.connect(self.reset_filters)

        self.filter_toggle_btn = QPushButton("Hide Filters")
        self.filter_toggle_btn.setObjectName("filterToggleButton")
        self.filter_toggle_btn.setMinimumWidth(154)
        self.filter_toggle_btn.clicked.connect(self.toggle_filter_panel)

        self.search_btn = QPushButton("Search Records")
        self.search_btn.setObjectName("primarySidebarButton")
        self.search_btn.setMinimumWidth(170)
        self.search_btn.clicked.connect(self.perform_search)

        hero_actions = QHBoxLayout()
        hero_actions.setContentsMargins(0, 0, 0, 0)
        hero_actions.setSpacing(10)
        hero_actions.addWidget(self.filter_toggle_btn, 0)
        hero_actions.addWidget(self.reset_btn, 0)
        hero_actions.addWidget(self.search_btn, 0)
        hero_actions.addStretch(1)
        hero_layout.addLayout(hero_actions)
        self._sync_filter_toggle_ui()
        self._update_filters_scroll_height()

        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("resultsToolbar")
        toolbar = QHBoxLayout(toolbar_frame)
        toolbar.setContentsMargins(14, 14, 14, 14)
        toolbar.setSpacing(10)
        main_layout.addWidget(toolbar_frame)

        left_cluster = QVBoxLayout()
        left_cluster.setContentsMargins(0, 0, 0, 0)
        left_cluster.setSpacing(3)
        self.page_title = QLabel("Face Search Results")
        self.page_title.setObjectName("pageTitle")
        self.page_summary = QLabel("No search has been run yet.")
        self.page_summary.setObjectName("pageSummary")
        left_cluster.addWidget(self.page_title)
        left_cluster.addWidget(self.page_summary)
        toolbar.addLayout(left_cluster, 1)

        self.results_filter_btn = QPushButton("Hide Filters")
        self.results_filter_btn.setObjectName("filterToggleButton")
        self.results_filter_btn.clicked.connect(self.toggle_filters_window)
        toolbar.addWidget(self.results_filter_btn)

        self.grid_cols_combo = self._combo_box()
        for count in GRID_OPTIONS:
            self.grid_cols_combo.addItem(f"{count} Col", count)
        self.grid_cols_combo.setCurrentText("3 Col")
        self.grid_cols_combo.currentIndexChanged.connect(self._on_grid_columns_changed)
        toolbar.addWidget(self.grid_cols_combo)

        self.rows_combo = self._combo_box()
        for count in ROWS_PER_PAGE_OPTIONS:
            self.rows_combo.addItem(f"{count} Rows", count)
        self.rows_combo.setCurrentText("20 Rows")
        self.rows_combo.currentIndexChanged.connect(self._on_rows_changed)
        toolbar.addWidget(self.rows_combo)

        self.export_btn = QPushButton("Export")
        self.export_btn.setObjectName("toolbarButton")
        self.export_btn.clicked.connect(self.export_csv)
        toolbar.addWidget(self.export_btn)

        view_switch = QFrame()
        view_switch.setObjectName("viewSwitch")
        switch_layout = QHBoxLayout(view_switch)
        switch_layout.setContentsMargins(4, 4, 4, 4)
        switch_layout.setSpacing(4)

        self.table_btn = QToolButton()
        self.table_btn.setObjectName("viewToggle")
        self.table_btn.setText("List")
        self.table_btn.clicked.connect(lambda: self.set_view_mode(False))
        switch_layout.addWidget(self.table_btn)

        self.grid_btn = QToolButton()
        self.grid_btn.setObjectName("viewToggleActive")
        self.grid_btn.setText("Grid")
        self.grid_btn.clicked.connect(lambda: self.set_view_mode(True))
        switch_layout.addWidget(self.grid_btn)
        toolbar.addWidget(view_switch)

        self.results_stack = QStackedWidget()
        main_layout.addWidget(self.results_stack, 1)

        self.grid_page = QWidget()
        grid_page_layout = QVBoxLayout(self.grid_page)
        grid_page_layout.setContentsMargins(0, 0, 0, 0)
        grid_page_layout.setSpacing(10)

        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        grid_page_layout.addWidget(self.grid_scroll, 1)

        self.grid_content = QWidget()
        self.grid_layout = QGridLayout(self.grid_content)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setHorizontalSpacing(12)
        self.grid_layout.setVerticalSpacing(12)
        self.grid_scroll.setWidget(self.grid_content)

        pagination = QHBoxLayout()
        pagination.setSpacing(8)
        self.grid_meta = QLabel("0-0 of 0")
        self.grid_meta.setObjectName("pageSummary")
        pagination.addWidget(self.grid_meta)
        pagination.addStretch(1)

        self.prev_btn = QPushButton("Prev")
        self.prev_btn.setObjectName("pagerButton")
        self.prev_btn.clicked.connect(self._go_prev_page)
        pagination.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Next")
        self.next_btn.setObjectName("pagerButton")
        self.next_btn.clicked.connect(self._go_next_page)
        pagination.addWidget(self.next_btn)
        grid_page_layout.addLayout(pagination)
        self.results_stack.addWidget(self.grid_page)

        self.table_page = QWidget()
        table_layout = QVBoxLayout(self.table_page)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)

        self.table = PrimeDataTable(
            page_size=self.rows_per_page,
            page_size_options=ROWS_PER_PAGE_OPTIONS,
            row_height=74,
            show_footer=True,
        )
        self.table.set_columns(
            [
                PrimeTableColumn("photo", "Photo", width=86, sortable=False, searchable=False),
                PrimeTableColumn("gender", "Gender", width=100),
                PrimeTableColumn("age", "Age", width=70),
                PrimeTableColumn("similarity", "Similarity", width=100),
                PrimeTableColumn("colors", "Colors", stretch=True),
                PrimeTableColumn("camera", "Camera", stretch=True),
                PrimeTableColumn("created", "Date & Time", stretch=True),
                PrimeTableColumn("actions", "Actions", width=208, sortable=False, searchable=False),
            ]
        )
        self.table.set_cell_widget_factory("photo", self._photo_cell)
        self.table.set_cell_widget_factory("actions", self._table_action_widget)
        self.table.row_clicked.connect(self._on_table_row_clicked)
        table_layout.addWidget(self.table, 1)
        self.results_stack.addWidget(self.table_page)

        self.refresh()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                color: #e2e8f0;
                font-size: 13px;
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
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #182740,
                    stop: 0.55 #132238,
                    stop: 1 #0f1726
                );
                border: 1px solid #35588c;
                border-radius: 22px;
            }
            QFrame#filterAccordion {
                background: rgba(7, 13, 24, 0.52);
                border: 1px solid #38527b;
                border-radius: 18px;
            }
            QPushButton#filterAccordionHeader {
                background: transparent;
                border: none;
                color: #eff6ff;
                font-size: 14px;
                font-weight: 800;
                padding: 14px 16px;
                text-align: left;
            }
            QPushButton#filterAccordionHeader:hover {
                background: rgba(96, 165, 250, 0.08);
            }
            QPushButton#filterAccordionHeader:disabled {
                color: #64748b;
            }
            QFrame#filterAccordionBody {
                background: transparent;
                border-top: 1px solid rgba(74, 98, 136, 0.55);
            }
            QLabel#filterAccordionHint {
                color: #a9bfdc;
                font-size: 11px;
            }
            QLabel#pageTitle {
                color: #f8fafc;
                font-size: 22px;
                font-weight: 800;
            }
            QLabel#heroTitle {
                color: #f8fbff;
                font-size: 28px;
                font-weight: 900;
            }
            QLabel#heroHint {
                color: #ccddf8;
                font-size: 13px;
            }
            QLabel#heroChip {
                background: rgba(96, 165, 250, 0.16);
                border: 1px solid rgba(147, 197, 253, 0.38);
                border-radius: 12px;
                color: #dbeafe;
                font-size: 11px;
                font-weight: 800;
                padding: 6px 10px;
            }
            QLabel#pageSummary, QLabel#referenceStatus {
                color: #94a3b8;
                font-size: 12px;
            }
            QLabel#fieldLabel {
                color: #cbd5e1;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#heroFieldLabel {
                color: #dbeafe;
                font-size: 12px;
                font-weight: 800;
            }
            QLabel#heroFieldHint {
                color: #9eb8d9;
                font-size: 11px;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {
                background: #232a34;
                border: 1px solid #364152;
                border-radius: 10px;
                color: #f8fafc;
                min-height: 38px;
                padding: 0 12px;
            }
            QWidget#fieldBlock, QWidget#heroFieldBlock {
                background: transparent;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QFrame#dateField {
                background: #0d1524;
                border: 1px solid #4a6288;
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
            QFrame#searchHero QTextEdit {
                background: #0d1524;
                border: 1px solid #4a6288;
                border-radius: 12px;
                color: #f8fafc;
                min-height: 44px;
                padding: 0 12px;
            }
            QFrame#searchHero QLineEdit:focus,
            QFrame#searchHero QComboBox:focus,
            QFrame#searchHero QSpinBox:focus,
            QFrame#searchHero QDoubleSpinBox:focus,
            QFrame#searchHero QTextEdit:focus {
                border: 1px solid #93c5fd;
            }
            QCheckBox {
                color: #dbe4f0;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #445067;
                background: #11161d;
            }
            QCheckBox::indicator:checked {
                background: #2563eb;
                border: 1px solid #3b82f6;
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
            QPushButton#primarySidebarButton, QPushButton#secondarySidebarButton,
            QPushButton#toolbarButton, QPushButton#pagerButton, QPushButton#filterToggleButton {
                min-height: 40px;
                border-radius: 11px;
                font-weight: 700;
                padding: 0 16px;
            }
            QFrame#searchHero QPushButton#primarySidebarButton,
            QFrame#searchHero QPushButton#secondarySidebarButton,
            QFrame#searchHero QPushButton#filterToggleButton {
                min-height: 44px;
                padding: 0 20px;
            }
            QPushButton#primarySidebarButton {
                background: #2563eb;
                border: none;
                color: white;
            }
            QPushButton#primarySidebarButton:hover, QPushButton#toolbarButton:hover {
                background: #1d4ed8;
            }
            QPushButton#secondarySidebarButton, QPushButton#pagerButton {
                background: #27303d;
                border: 1px solid #374151;
                color: #e5e7eb;
            }
            QPushButton#secondarySidebarButton:hover, QPushButton#pagerButton:hover {
                background: #313b4a;
            }
            QPushButton#filterToggleButton {
                background: #152335;
                border: 1px solid #3a5f8b;
                color: #dbeafe;
            }
            QPushButton#filterToggleButton:hover {
                background: #1a2b41;
            }
            QPushButton#toolbarButton {
                background: #2563eb;
                border: none;
                color: white;
            }
            QPushButton#toolbarButton:disabled, QPushButton#pagerButton:disabled,
            QPushButton#primarySidebarButton:disabled, QPushButton#secondarySidebarButton:disabled,
            QPushButton#filterToggleButton:disabled {
                background: #1f252d;
                color: #64748b;
                border-color: #2a3340;
            }
            QFrame#viewSwitch {
                background: #222833;
                border: 1px solid #334155;
                border-radius: 12px;
            }
            QToolButton#viewToggle, QToolButton#viewToggleActive {
                min-width: 62px;
                min-height: 34px;
                border-radius: 9px;
                font-weight: 700;
            }
            QToolButton#viewToggle {
                background: transparent;
                border: none;
                color: #94a3b8;
            }
            QToolButton#viewToggleActive {
                background: #3b82f6;
                border: none;
                color: white;
            }
            QToolButton#tableActionButton {
                background: #27303d;
                border: 1px solid #3a4555;
                border-radius: 8px;
                color: #e2e8f0;
                min-width: 34px;
                max-width: 34px;
                min-height: 34px;
                max-height: 34px;
            }
            QToolButton#tableActionButton:hover {
                background: #313b4a;
                border-color: #4b5a6f;
            }
            QFrame#faceCard {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #172437,
                    stop: 0.58 #16202d,
                    stop: 1 #101720
                );
                border: 1px solid #31506f;
                border-radius: 20px;
            }
            QFrame#faceCard:hover {
                border: 1px solid #7dd3fc;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #1a2b41,
                    stop: 0.62 #1b2737,
                    stop: 1 #13202c
                );
            }
            QFrame#faceCardMedia, QFrame#faceCardFacts {
                background: rgba(10, 17, 28, 0.72);
                border: 1px solid #2c3b50;
                border-radius: 14px;
            }
            QLabel#faceCardEyebrow {
                color: #7dd3fc;
                font-size: 10px;
                font-weight: 900;
                letter-spacing: 1px;
            }
            QLabel#faceCardTitle {
                color: #f8fafc;
                font-size: 20px;
                font-weight: 900;
            }
            QLabel#faceCardChip {
                background: rgba(34, 197, 94, 0.14);
                color: #bbf7d0;
                border: 1px solid rgba(34, 197, 94, 0.3);
                border-radius: 10px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: 800;
            }
            QLabel#faceCardBadgeNeutral,
            QLabel#faceCardBadgeAccent,
            QLabel#faceCardBadgeMuted,
            QLabel#faceCardBadgeDanger,
            QLabel#faceCardBadgeSuccess {
                border-radius: 10px;
                padding: 4px 9px;
                font-size: 11px;
                font-weight: 800;
            }
            QLabel#faceCardBadgeNeutral {
                background: rgba(148, 163, 184, 0.14);
                color: #dbeafe;
                border: 1px solid rgba(148, 163, 184, 0.24);
            }
            QLabel#faceCardBadgeAccent {
                background: rgba(59, 130, 246, 0.16);
                color: #93c5fd;
                border: 1px solid rgba(59, 130, 246, 0.28);
            }
            QLabel#faceCardBadgeMuted {
                background: rgba(250, 204, 21, 0.12);
                color: #fde68a;
                border: 1px solid rgba(250, 204, 21, 0.22);
            }
            QLabel#faceCardBadgeDanger {
                background: rgba(248, 113, 113, 0.14);
                color: #fecaca;
                border: 1px solid rgba(248, 113, 113, 0.26);
            }
            QLabel#faceCardBadgeSuccess {
                background: rgba(74, 222, 128, 0.14);
                color: #bbf7d0;
                border: 1px solid rgba(74, 222, 128, 0.26);
            }
            QLabel#faceCardFactLabel {
                color: #8fa5bf;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#faceCardFactValue {
                color: #f8fafc;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton#faceCardAction, QPushButton#faceCardGhostAction {
                min-height: 36px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton#faceCardAction {
                background: #2563eb;
                border: none;
                color: white;
            }
            QPushButton#faceCardAction:hover {
                background: #1d4ed8;
            }
            QPushButton#faceCardGhostAction {
                background: #27303d;
                border: 1px solid #374151;
                color: #e2e8f0;
            }
            QPushButton#faceCardGhostAction:hover {
                background: #313b4a;
            }
            QLabel#emptyTitle {
                color: #f8fafc;
                font-size: 21px;
                font-weight: 800;
            }
            QLabel#emptyHint {
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

    def _combo_box(self) -> QComboBox:
        combo = QComboBox()
        combo.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        return combo

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

    def _hero_field_block(self, label_text: str, field: QWidget, hint_text: str) -> QWidget:
        wrapper = QWidget()
        wrapper.setObjectName("heroFieldBlock")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(label_text)
        label.setObjectName("heroFieldLabel")
        layout.addWidget(label)
        hint = QLabel(hint_text)
        hint.setObjectName("heroFieldHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(field)
        return wrapper

    def _auth_token(self) -> str:
        try:
            return self.search_store.service.api._auth_token()
        except Exception:
            return ""

    def _on_auth_changed(self) -> None:
        self.reference_preview.set_auth_token(self._auth_token())
        current_user = self.auth_store.current_user
        if current_user is None:
            self.camera_store.get_camera_for_user(None, silent=True)
            return
        department_id = None if current_user.is_superadmin else current_user.department_id
        self.camera_store.get_camera_for_user(department_id, silent=True)

    def _camera_options(self) -> List[dict]:
        return [
            {"label": camera.name or f"Camera #{camera.id}", "value": camera.id}
            for camera in sorted(self.camera_store.cameras, key=lambda item: (item.name or "").lower())
            if int(getattr(camera, "id", 0) or 0) > 0
        ]

    def _refresh_camera_options(self) -> None:
        options = self._camera_options()
        previous = set(self.camera_select.value())
        self.camera_select.set_options(options)
        self.camera_select.set_value([item for item in previous if item in {opt["value"] for opt in options}])

    def _apply_default_date_range(self) -> None:
        now = datetime.now(SEARCH_TIMEZONE).replace(second=0, microsecond=0)
        self.date_to_input.set_value(now)
        self.date_from_input.set_value(now - timedelta(hours=24))

    def _sync_filter_toggle_ui(self, *_args) -> None:
        open_count = sum(1 for section in self._filter_sections if section.is_expanded())
        self.filter_panel_open = open_count > 0
        if open_count <= 0:
            self.filter_toggle_btn.setText("Show Filters")
            self.filter_state_chip.setText("Filters collapsed")
        elif open_count >= len(self._filter_sections):
            self.filter_toggle_btn.setText("Hide Filters")
            self.filter_state_chip.setText("All filters open")
        else:
            self.filter_toggle_btn.setText("Hide Filters")
            self.filter_state_chip.setText(f"{open_count} sections open")

    def _sync_filters_window_ui(self) -> None:
        self.hero_scroll.setVisible(self.filters_window_visible)
        self._update_filters_scroll_height()
        self.results_filter_btn.setText("Hide Filters" if self.filters_window_visible else "Show Filters")

    def _update_filters_scroll_height(self) -> None:
        if not hasattr(self, "hero_scroll"):
            return
        max_height = max(240, min(520, int(self.height() * 0.52)))
        self.hero_scroll.setMaximumHeight(max_height)

    def _set_filters_window_visible(self, visible: bool) -> None:
        self.filters_window_visible = visible
        if not visible:
            self._set_filter_panel_visible(False)
            return
        self._sync_filters_window_ui()

    def _set_filter_panel_visible(self, visible: bool) -> None:
        for section in self._filter_sections:
            section.set_expanded(visible)
        self._sync_filter_toggle_ui()
        self._sync_filters_window_ui()

    def toggle_filter_panel(self) -> None:
        self._set_filter_panel_visible(not self.filter_panel_open)

    def toggle_filters_window(self) -> None:
        self._set_filters_window_visible(not self.filters_window_visible)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._update_filters_scroll_height()

    def set_view_mode(self, grid: bool) -> None:
        self.grid_view = grid
        self.results_stack.setCurrentIndex(0 if grid else 1)
        self.grid_btn.setObjectName("viewToggleActive" if grid else "viewToggle")
        self.table_btn.setObjectName("viewToggleActive" if not grid else "viewToggle")
        self.grid_btn.style().unpolish(self.grid_btn)
        self.grid_btn.style().polish(self.grid_btn)
        self.table_btn.style().unpolish(self.table_btn)
        self.table_btn.style().polish(self.table_btn)
        self.grid_cols_combo.setVisible(grid)
        self.refresh()

    def _choose_reference_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Face Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if path:
            self._load_embedding_from_file(path)

    def _load_embedding_from_file(self, image_path: str) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = self.search_store.service.get_embedding(image_path)
        except Exception as exc:
            self._clear_reference_face()
            self._show_error(str(exc))
            return
        finally:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
        self._apply_reference_embedding(result, f"Reference loaded from {os.path.basename(image_path)}.")

    def _load_embedding_from_url(self, image_url: str, status_text: str) -> bool:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = self.search_store.service.get_embedding_by_url(image_url)
        except Exception as exc:
            self._show_error(str(exc))
            return False
        finally:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
        self._apply_reference_embedding(result, status_text)
        return True

    def _apply_reference_embedding(self, result: FaceEmbeddingResult, status_text: str) -> None:
        self._reference_embedding = result.embedding
        preview_url = result.crop_image_url or result.image_url
        self.reference_preview.set_auth_token(self._auth_token())
        self.reference_preview.set_image_url(preview_url)
        self.reference_status.setText(status_text)

    def _clear_reference_face(self) -> None:
        self._reference_embedding = ""
        self.reference_preview.set_image_url("")
        self.reference_status.setText("No face reference selected.")

    def reset_filters(self) -> None:
        self.has_searched = False
        self._apply_default_date_range()
        self._clear_reference_face()
        self.gender_combo.setCurrentIndex(0)
        self.match_spin.setValue(70.0)
        self.age_from_spin.setValue(1)
        self.age_to_spin.setValue(100)
        self.top_color_select.set_value([])
        self.bottom_color_select.set_value([])
        self.camera_select.set_value([])
        self.blacklist_check.setChecked(False)
        self.whitelist_check.setChecked(False)
        self.search_store.clear()
        self.current_page = 0
        self._set_filter_panel_visible(False)
        self.refresh()

    def _current_payload(self) -> Dict[str, object]:
        return {
            "start": 0,
            "length": max(500, self.rows_per_page * 8),
            "date_from": self.date_from_input.value(),
            "date_to": self.date_to_input.value(),
            "embedding": self._reference_embedding,
            "age_from": int(self.age_from_spin.value()),
            "age_to": int(self.age_to_spin.value()),
            "gender": self.gender_combo.currentData(),
            "top_color": list(self.top_color_select.value()),
            "bottom_color": list(self.bottom_color_select.value()),
            "match": int(round(self.match_spin.value())),
            "camera_ids": list(self.camera_select.value()),
            "blacklist": self.blacklist_check.isChecked(),
            "whitelist": self.whitelist_check.isChecked(),
        }

    def perform_search(self) -> None:
        if self.search_in_progress:
            return
        payload = self._current_payload()
        date_from = payload.get("date_from")
        date_to = payload.get("date_to")
        if isinstance(date_from, datetime) and isinstance(date_to, datetime) and date_from > date_to:
            self._show_error("Start time must be earlier than end time.")
            return
        if int(self.age_from_spin.value()) > int(self.age_to_spin.value()):
            self._show_error("Age From must be less than or equal to Age To.")
            return

        self._set_filters_window_visible(False)
        self.has_searched = True
        self.search_in_progress = True
        self.search_store.loading = True
        self.search_btn.setEnabled(False)
        self.search_btn.setText("Searching...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        self._search_thread = FaceSearchWorker(payload, self)
        self._search_thread.finished_rows.connect(self._on_search_finished)
        self._search_thread.failed_text.connect(self._on_search_failed)
        self._search_thread.finished.connect(self._clear_search_thread)
        self._search_thread.start()
        self.refresh()

    def _on_search_finished(self, results: List[FaceSearchResult]) -> None:
        self.search_store.results = list(results)
        self.search_store.loading = False
        self.search_in_progress = False
        self.current_page = 0
        self._set_filters_window_visible(False)
        if QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Search Records")
        self.refresh()

    def _on_search_failed(self, text: str) -> None:
        self.search_store.results = []
        self.search_store.loading = False
        self.search_in_progress = False
        self.current_page = 0
        self._set_filters_window_visible(False)
        if QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Search Records")
        self.refresh()
        self._show_error(text)

    def _clear_search_thread(self) -> None:
        if self._search_thread is not None:
            self._search_thread.deleteLater()
        self._search_thread = None

    def _on_grid_columns_changed(self, _index: int) -> None:
        value = self.grid_cols_combo.currentData()
        if isinstance(value, int) and value > 0:
            self.grid_columns = value
        self.refresh()

    def _on_rows_changed(self, _index: int) -> None:
        value = self.rows_combo.currentData()
        if not isinstance(value, int) or value <= 0:
            return
        self.rows_per_page = value
        self.current_page = 0
        self.table.set_page_size(value)
        self.refresh()

    def _go_prev_page(self) -> None:
        if self.current_page <= 0:
            return
        self.current_page -= 1
        self.refresh()

    def _go_next_page(self) -> None:
        total = len(self.search_store.results)
        if total <= 0:
            return
        max_page = max(0, (total - 1) // self.rows_per_page)
        if self.current_page >= max_page:
            return
        self.current_page += 1
        self.refresh()

    def _paged_results(self) -> List[FaceSearchResult]:
        if self.rows_per_page <= 0:
            return list(self.search_store.results)
        start = self.current_page * self.rows_per_page
        end = start + self.rows_per_page
        return self.search_store.results[start:end]

    def refresh(self) -> None:
        results = list(self.search_store.results)
        total = len(results)
        busy = self.search_in_progress or self.search_store.loading
        self._clamp_current_page()
        if busy:
            self.page_summary.setText("Searching records...")
        elif not self.has_searched:
            self.page_summary.setText("Adjust filters and run a search.")
        elif total == 0:
            self.page_summary.setText("Search completed. No matching records were found.")
        else:
            self.page_summary.setText(f"{total} record{'s' if total != 1 else ''} loaded.")

        self.filter_toggle_btn.setEnabled(not busy)
        self.results_filter_btn.setEnabled(not busy)
        self.reset_btn.setEnabled(not busy)
        self.rows_combo.setEnabled(not busy)
        self.grid_cols_combo.setEnabled(not busy)
        self.table_btn.setEnabled(not busy)
        self.grid_btn.setEnabled(not busy)
        for section in self._filter_sections:
            section.header_btn.setEnabled(not busy)
        self.export_btn.setEnabled(total > 0 and not busy)
        self.prev_btn.setEnabled(self.current_page > 0 and not busy)
        max_page = max(0, (total - 1) // self.rows_per_page) if self.rows_per_page > 0 else 0
        self.next_btn.setEnabled(self.current_page < max_page and not busy)
        self.clear_reference_btn.setEnabled(not busy)
        self.upload_btn.setEnabled(not busy)

        if self.grid_view:
            self._refresh_grid()
        else:
            self._refresh_table()

    def _clamp_current_page(self) -> None:
        total = len(self.search_store.results)
        if self.rows_per_page <= 0 or total <= 0:
            self.current_page = 0
            return
        max_page = max(0, (total - 1) // self.rows_per_page)
        self.current_page = max(0, min(self.current_page, max_page))

    def _refresh_grid(self) -> None:
        _clear_layout(self.grid_layout)
        page_results = self._paged_results()
        total = len(self.search_store.results)

        if not page_results:
            empty = self._empty_state(
                title=(
                    "Search For Face Records"
                    if not self.has_searched
                    else ("No Results Found" if total == 0 else "No Results On This Page")
                ),
                hint=(
                    "Use the filter panel to search by face image, date, camera, colors, and attributes."
                    if not self.has_searched
                    else (
                        "We could not find face records matching the current filters."
                        if total == 0
                        else "Try another page or adjust the row count."
                    )
                ),
            )
            self.grid_layout.addWidget(empty, 0, 0)
            self.grid_meta.setText("0-0 of 0")
            return

        columns = max(1, self.grid_columns)
        compact = columns >= 4
        for index, record in enumerate(page_results):
            card = FaceResultCard(record, self.net, auth_token=self._auth_token(), compact=compact)
            card.opened.connect(self.open_detail_dialog)
            card.search_requested.connect(self.search_similar_face)
            self.grid_layout.addWidget(card, index // columns, index % columns)

        start = self.current_page * self.rows_per_page + 1
        end = start + len(page_results) - 1
        self.grid_meta.setText(f"{start}-{end} of {total}")

    def _refresh_table(self) -> None:
        rows = []
        for record in self.search_store.results:
            rows.append(
                {
                    "photo": "",
                    "gender": record.gender or "Unset",
                    "age": str(record.age) if record.age is not None else "Unset",
                    "similarity": record.similarity_text,
                    "colors": f"Top: {record.top_color_text} | Bottom: {record.bottom_color_text}",
                    "camera": record.camera_name,
                    "created": record.created_text,
                    "actions": "",
                    "_record": record,
                }
            )
        self.table.set_rows(rows)

    def _empty_state(self, title: str, hint: str) -> QWidget:
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(60, 80, 60, 80)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel("⌕")
        icon.setStyleSheet("font-size:48px;color:#475569;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("emptyTitle")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)
        hint_lbl = QLabel(hint)
        hint_lbl.setObjectName("emptyHint")
        hint_lbl.setWordWrap(True)
        hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint_lbl)
        return frame

    def _photo_cell(self, row: Dict[str, object]) -> QWidget:
        record = row.get("_record")
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        image = RemoteImageLabel(self.net, fallback_text="No Face", auth_token=self._auth_token())
        image.setFixedSize(62, 62)
        image.setStyleSheet("border-radius:12px;background:#0e141b;")
        if isinstance(record, FaceSearchResult):
            image.set_image_url(_face_crop_url(record))
        layout.addWidget(image)
        return wrapper

    def _table_action_widget(self, row: Dict[str, object]) -> QWidget:
        record = row.get("_record")
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        def _action_button(text: str, fallback: str) -> QToolButton:
            button = QToolButton()
            button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            button.setObjectName("tableActionButton")
            icon = QIcon(_icon_path(text))
            if not icon.isNull():
                button.setIcon(icon)
            else:
                button.setText(fallback)
            return button

        view_btn = _action_button("view.svg", "V")
        view_btn.setToolTip("Open details")
        view_btn.clicked.connect(lambda: self.open_detail_dialog(record))
        layout.addWidget(view_btn)

        search_btn = _action_button("search.svg", "S")
        search_btn.setToolTip("Search similar")
        search_btn.clicked.connect(lambda: self.search_similar_face(record))
        layout.addWidget(search_btn)

        blacklist_btn = _action_button("close.svg", "B")
        blacklist_btn.setToolTip("Add to blacklist")
        blacklist_btn.clicked.connect(lambda: self.open_blacklist_dialog(record))
        layout.addWidget(blacklist_btn)

        whitelist_btn = _action_button("play.svg", "W")
        whitelist_btn.setToolTip("Add to whitelist")
        whitelist_btn.clicked.connect(lambda: self.open_whitelist_dialog(record))
        layout.addWidget(whitelist_btn)
        return wrapper

    def _on_table_row_clicked(self, row: Dict[str, object]) -> None:
        record = row.get("_record")
        if isinstance(record, FaceSearchResult):
            self.open_detail_dialog(record)

    def open_detail_dialog(self, record: object) -> None:
        if not isinstance(record, FaceSearchResult):
            return
        dialog = FaceDetailDialog(record, self.net, auth_token=self._auth_token(), parent=self)
        dialog.search_requested.connect(self.search_similar_face)
        dialog.blacklist_requested.connect(self.open_blacklist_dialog)
        dialog.whitelist_requested.connect(self.open_whitelist_dialog)
        dialog.exec()

    def search_similar_face(self, record: object) -> None:
        if not isinstance(record, FaceSearchResult):
            return
        image_url = _face_crop_url(record) or _face_full_url(record)
        if not image_url:
            self._show_error("This record does not have an accessible face image.")
            return
        if not self._load_embedding_from_url(
            image_url,
            f"Reference loaded from selected record at {record.created_text}.",
        ):
            return
        self.perform_search()

    def _build_watchlist_dialog(
        self,
        record: FaceSearchResult,
        title_text: str,
        action_text: str,
    ) -> Optional[FaceWatchlistDialog]:
        image_url = _face_crop_url(record) or _face_full_url(record)
        if not image_url:
            self._show_error("This record does not have an accessible face image.")
            return None

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            embedding_result = self.search_store.service.get_embedding_by_url(image_url)
        except Exception as exc:
            self._show_error(str(exc))
            return None
        finally:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()

        preview_url = embedding_result.crop_image_url or embedding_result.image_url or image_url
        return FaceWatchlistDialog(
            title_text=title_text,
            action_text=action_text,
            preview_url=preview_url,
            embedding_result=embedding_result,
            record=record,
            camera_options=self._camera_options(),
            auth_token=self._auth_token(),
            parent=self,
        )

    def open_blacklist_dialog(self, record: object) -> None:
        if not isinstance(record, FaceSearchResult):
            return
        dialog = self._build_watchlist_dialog(record, "Add To Blacklist", "Save To Blacklist")
        if dialog is None or not dialog.exec():
            return
        try:
            message, _person_id = FaceBlacklistService().create_entry(dialog.payload())
        except Exception as exc:
            self._show_error(str(exc))
            return
        self._show_success("Blacklist", message)

    def open_whitelist_dialog(self, record: object) -> None:
        if not isinstance(record, FaceSearchResult):
            return
        dialog = self._build_watchlist_dialog(record, "Add To Whitelist", "Save To Whitelist")
        if dialog is None or not dialog.exec():
            return
        try:
            message, _person_id = FaceWhitelistService().create_entry(dialog.payload())
        except Exception as exc:
            self._show_error(str(exc))
            return
        self._show_success("Whitelist", message)

    def export_csv(self) -> None:
        if not self.search_store.results:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Face Search",
            os.path.expanduser("~/FaceSearch.csv"),
            "CSV Files (*.csv)",
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "Gender",
                        "Age",
                        "Similarity",
                        "Top Color",
                        "Bottom Color",
                        "Camera",
                        "Date & Time",
                        "Blacklist",
                        "Whitelist",
                    ]
                )
                for record in self.search_store.results:
                    writer.writerow(
                        [
                            record.gender,
                            record.age if record.age is not None else "",
                            record.similarity_text,
                            record.top_color_text,
                            record.bottom_color_text,
                            record.camera_name,
                            record.created_text,
                            "Yes" if record.is_blacklist else "No",
                            "Yes" if record.is_whitelist else "No",
                        ]
                    )
        except Exception as exc:
            self._show_error(f"Failed to export CSV: {exc}")
            return
        self._show_success("Face Search", f"Results exported to {path}.")

    def _show_error(self, text: str) -> None:
        self.toast.error("Face Search", text)

    def _show_success(self, summary: str, text: str) -> None:
        self.toast.success(summary, text)


class MainWindow(QMainWindow):
    navigate = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Face Search")
        self.resize(1520, 920)
        page = FaceSearchPage()
        page.navigate.connect(self.navigate.emit)
        self.setCentralWidget(page)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
