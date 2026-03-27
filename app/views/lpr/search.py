from __future__ import annotations

import csv
import os
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from PySide6.QtCore import (
    QDate,
    QDateTime,
    QEasingCurve,
    QEvent,
    QLocale,
    QObject,
    QPropertyAnimation,
    QSize,
    QThread,
    QRectF,
    QTime,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import QCursor, QIcon, QPixmap,QColor,QPainter,QPainterPath
from app.constants._init_ import Constants
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models.lpr.search import LprSearchPayload, LprSearchResult
from app.models.lpr.region import region_options
from app.services.auth.auth_service import AuthService
from app.services.home.devices.camera_service import CameraService
from app.services.home.lpr.search_service import LprSearchService
from app.store.auth.auth_store import AuthStore
from app.store.home.lpr.search_store import LprSearchStore
from app.store.home.user.department_store import DepartmentStore as CameraDepartmentStore
from app.ui.button import PrimeButton
from app.ui.checkbox import PrimeCheckBox
from app.ui.date_picker import _CalendarPopup
from app.ui.dialog import PrimeDialog
from app.ui.file_browser_dialog import choose_restricted_save_file_path
from app.ui.input import PrimeInput
from app.ui.multiselect import PrimeMultiSelect
from app.ui.select import PrimeSelect
from app.ui.sidebar_toggle import SidebarToggleButton
from app.ui.table import PrimeDataTable, PrimeTableColumn
from app.ui.toast import show_toast_message
from app.utils.digits import normalize_ascii_digits
from app.utils.env import resolve_http_base_url
from app.views.search_shared import SEARCH_SIDEBAR_STYLES, SearchSidebar


_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


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


COMPARE_OPTIONS = [
    ("Equal", "equal"),
    ("Start With", "start_with"),
    ("Contains", "contain"),
]

TYPE_OPTIONS = ["Regular", "FAHS", "KATY"]

REGION_OPTIONS = region_options()

COLOR_OPTIONS = [
  {
    "label": "Government",
    "value": "Government",
  },
  {
    "label": "Private",
    "value": "Private",
  },
  {
    "label": "Transport",
    "value": "Transport",
  },
  {
    "label": "Taxi",
    "value": "Taxi",
  },
  {
    "label": "Fahs",
    "value": "Fahs",
  },
  {
    "label": "Other",
    "value": "Other",
  },
]

GRID_OPTIONS = [2, 3, 4]
ROWS_PER_PAGE_OPTIONS = [10, 20, 50, 100, 200]
DIGITS_OPTIONS = [{"label": "Any Digits", "value": None}] + [{"label": str(n), "value": n} for n in range(1, 21)]
CONFIDENCE_OPTIONS = [{"label": "Any Confidence", "value": 0}] + [{"label": f"{n}%", "value": n} for n in range(1, 101)]
SEARCH_TIMEZONE = timezone(timedelta(hours=3))
SEARCH_TIMEZONE_LABEL = "UTC+3"
SEARCH_DATE_LOCALE = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
_ACTIVE_SEARCH_THREADS: set[QThread] = set()


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            _clear_layout(child_layout)


def _normalize_line_edit_digits(field: QLineEdit, text: str) -> None:
    normalized = normalize_ascii_digits(text)
    if normalized == text:
        return
    cursor = field.cursorPosition()
    field.blockSignals(True)
    field.setText(normalized)
    field.blockSignals(False)
    field.setCursorPosition(min(cursor, len(normalized)))


def _bind_ascii_digit_input(field: QLineEdit) -> None:
    field.setInputMethodHints(field.inputMethodHints() | Qt.InputMethodHint.ImhPreferLatin)
    field.textEdited.connect(lambda text, edit=field: _normalize_line_edit_digits(edit, text))


def _as_search_datetime(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=SEARCH_TIMEZONE)


def _to_search_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=SEARCH_TIMEZONE)
    return value.astimezone(SEARCH_TIMEZONE)


def _format_search_datetime(value: datetime, with_timezone: bool = False, verbose: bool = False) -> str:
    localized = _to_search_timezone(value)
    qdt = QDateTime(
        QDate(localized.year, localized.month, localized.day),
        QTime(localized.hour, localized.minute, localized.second),
    )
    if verbose:
        text = SEARCH_DATE_LOCALE.toString(qdt, "dddd, dd MMM yyyy 'at' hh:mm AP")
    else:
        text = SEARCH_DATE_LOCALE.toString(qdt, "dd MMM yyyy, hh:mm AP")
    return f"{text} {SEARCH_TIMEZONE_LABEL}" if with_timezone else text


class ClearableDateTimeField(QFrame):
    def __init__(self, placeholder: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._placeholder = placeholder
        self._value: Optional[datetime] = None
        self.setObjectName("dateField")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        self.display = QLineEdit()
        self.display.setObjectName("datePickerDisplay")
        self.display.setReadOnly(True)
        self.display.setPlaceholderText(placeholder)
        self.display.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.display.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.display.installEventFilter(self)
        layout.addWidget(self.display, 1)

        self.open_btn = QToolButton()
        self.open_btn.setObjectName("datePickerButton")
        self.open_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.open_btn.setToolTip("Open date picker")
        self.open_btn.setIcon(QIcon(_icon_path("calendar.svg")))
        self.open_btn.setIconSize(QSize(18, 18))
        self.open_btn.clicked.connect(self._show_popup)
        layout.addWidget(self.open_btn)

        self.clear_btn = QToolButton()
        self.clear_btn.setObjectName("dateClearButton")
        self.clear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.clear_btn.setToolTip("Clear value")
        self.clear_btn.setIcon(QIcon(_icon_path("close.svg")))
        self.clear_btn.setIconSize(QSize(14, 14))
        self.clear_btn.clicked.connect(self.clear)
        layout.addWidget(self.clear_btn)
        self.clear_btn.hide()

        self._popup = _CalendarPopup(
            self,
            radius=16,
            include_time=True,
            time_display_format="hh:mm AP",
            weekday_header_text_color="#a9bfdc",
            weekday_header_weekend_text_color="#dbeafe",
            navigation_icon_color="#eff6ff",
            navigation_hover_background="#1a2b41",
        )
        self._popup.selection_applied.connect(self._apply_popup_selection)

    def clear(self) -> None:
        self._value = None
        self._popup.set_selected_date_time(QDateTime.currentDateTime())
        self._sync_display()

    def value(self) -> Optional[datetime]:
        return self._value

    def set_value(self, value: Optional[datetime]) -> None:
        self._value = _to_search_timezone(value) if value is not None else None
        self._sync_popup_from_value()
        self._sync_display()

    def eventFilter(self, watched: object, event: object) -> bool:
        if watched is self.display and isinstance(event, QEvent):
            if event.type() == QEvent.Type.MouseButtonPress:
                self._show_popup()
                return True
        return super().eventFilter(watched, event)

    def _show_popup(self) -> None:
        self._sync_popup_from_value()
        popup_width = max(self.width(), 336)
        self._popup.resize(popup_width, self._popup.sizeHint().height())
        pos = self.mapToGlobal(self.rect().bottomLeft())
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            if pos.x() + popup_width > available.x() + available.width():
                pos.setX(max(available.x() + 8, available.x() + available.width() - popup_width - 8))
            popup_height = self._popup.sizeHint().height()
            if pos.y() + popup_height > available.y() + available.height():
                top = self.mapToGlobal(self.rect().topLeft())
                pos.setY(max(available.y() + 8, top.y() - popup_height - 8))
        self._popup.move(pos)
        self._popup.show()
        self._popup.raise_()

    def _sync_popup_from_value(self) -> None:
        source = _to_search_timezone(self._value) if self._value is not None else datetime.now(SEARCH_TIMEZONE)
        self._popup.set_selected_date_time(
            QDateTime(
                QDate(source.year, source.month, source.day),
                QTime(source.hour, source.minute),
            )
        )

    def _apply_popup_selection(self, value: QDateTime) -> None:
        if not value.isValid():
            return
        self._value = _as_search_datetime(
            value.date().year(),
            value.date().month(),
            value.date().day(),
            value.time().hour(),
            value.time().minute(),
        )
        self._sync_display()

    def _sync_display(self) -> None:
        if self._value is None:
            self.display.clear()
            self.clear_btn.hide()
            return
        self.display.setText(_format_search_datetime(self._value, with_timezone=True))
        self.clear_btn.show()


class FilterAccordionSection(QFrame):
    toggled = Signal(bool)

    def __init__(
        self,
        title_text: str,
        hint_text: str = "",
        expanded: bool = True,
        collapsible: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._title_text = title_text
        self._expanded = expanded
        self._collapsible = collapsible
        self.setObjectName("filterAccordion")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header_btn = QPushButton()
        self.header_btn.setObjectName("filterAccordionHeader")
        self.header_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor if collapsible else Qt.CursorShape.ArrowCursor)
        )
        if collapsible:
            self.header_btn.clicked.connect(self.toggle)
        root.addWidget(self.header_btn)

        self.body = QFrame()
        self.body.setObjectName("filterAccordionBody")
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(16, 16, 16, 16)
        body_layout.setSpacing(12)
        root.addWidget(self.body)
        self.body_layout = body_layout

        if hint_text:
            hint = QLabel(hint_text)
            hint.setObjectName("filterAccordionHint")
            hint.setWordWrap(True)
            self.body_layout.addWidget(hint)

        self.set_expanded(expanded)

    def is_expanded(self) -> bool:
        return self._expanded

    def is_collapsible(self) -> bool:
        return self._collapsible

    def set_expanded(self, expanded: bool, emit_signal: bool = False) -> None:
        if not self._collapsible:
            expanded = True
        self._expanded = expanded
        self.body.setVisible(expanded)
        prefix = f"{'▾' if expanded else '▸'}  " if self._collapsible else ""
        self.header_btn.setText(f"{prefix}{self._title_text}")
        if emit_signal:
            self.toggled.emit(expanded)

    def toggle(self) -> None:
        if not self._collapsible:
            return
        self.set_expanded(not self._expanded, emit_signal=True)


class RemoteImageLabel(QLabel):
    def __init__(self, net: QNetworkAccessManager, fallback_text: str = "No Image", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._net = net
        self._reply = None
        self._original = QPixmap()
        self._image_url = ""
        self._fallback_text = fallback_text
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(fallback_text)
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

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._reply is None and self._original.isNull() and self._image_url:
            self._start_request()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if self._reply is not None:
            self._abort_reply()

    def _start_request(self) -> None:
        if not self._image_url:
            return
        reply = self._net.get(QNetworkRequest(QUrl(self._image_url)))
        self._reply = reply
        reply.finished.connect(lambda current=reply: self._on_done(current))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_scaled()

    def _abort_reply(self) -> None:
        reply = self._reply
        self._reply = None
        if reply is None:
            return
        try:
            reply.abort()
        except Exception:
            pass
        reply.deleteLater()

    def _on_done(self, reply: QNetworkReply) -> None:
        if reply is None:
            return
        if self._reply is reply:
            self._reply = None
        else:
            reply.deleteLater()
            return
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.setText("Image Error")
                return
            payload = bytes(reply.readAll())
            pix = QPixmap()
            if not pix.loadFromData(payload):
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
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)
        self.setText("")


class LprResultCard(QFrame):
    opened = Signal(object)
    search_requested = Signal(str)

    def __init__(
        self,
        record: LprSearchResult,
        net: QNetworkAccessManager,
        compact: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.record = record
        self.setObjectName("lprCard")
        self.setProperty("compact", compact)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        media_card = QFrame()
        media_card.setObjectName("lprCardMedia")
        media_layout = QVBoxLayout(media_card)
        media_layout.setContentsMargins(12, 12, 12, 12)
        media_layout.setSpacing(8)

        media_header = QHBoxLayout()
        media_header.setContentsMargins(0, 0, 0, 0)
        media_header.setSpacing(8)

        media_title = QLabel("Full Camera Frame")
        media_title.setObjectName("lprCardMediaTitle")
        media_header.addWidget(media_title, 1)

        media_hint = QLabel("No crop")
        media_hint.setObjectName("lprCardMediaHint")
        media_header.addWidget(media_hint, 0, Qt.AlignmentFlag.AlignTop)
        media_layout.addLayout(media_header)

        self.image = RemoteImageLabel(net, "No Frame")
        frame_height = 126 if compact else 172
        self.image.setMinimumHeight(frame_height)
        self.image.setMaximumHeight(frame_height)
        self.image.setStyleSheet("background:#050a12;border:1px solid #243244;border-radius:14px;color:#64748b;")
        media_layout.addWidget(self.image)
        root.addWidget(media_card)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)

        plate_block = QVBoxLayout()
        plate_block.setContentsMargins(0, 0, 0, 0)
        plate_block.setSpacing(2)

        label = QLabel("PLATE")
        label.setObjectName("lprCardEyebrow")
        plate_block.addWidget(label)

        title = QLabel(record.number or "Unknown Plate")
        title.setObjectName("lprCardTitle")
        if compact:
            title.setStyleSheet("font-size:16px;")
        plate_block.addWidget(title)
        header.addLayout(plate_block, 1)

        chip = QLabel(record.confidence_text if record.confidence_text != "-" else "LPR")
        chip.setObjectName("lprCardChip")
        header.addWidget(chip, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(6)
        badge_row.addWidget(self._badge(record.region or "Unknown Region", "neutral"))
        badge_row.addWidget(self._badge(record.plate_type or "Type -", "accent"))
        if record.color_text != "-":
            badge_row.addWidget(self._badge(record.color_text, "muted"))
        if record.is_blacklist:
            badge_row.addWidget(self._badge("Blacklist", "danger"))
        elif record.is_whitelist:
            badge_row.addWidget(self._badge("Whitelist", "success"))
        badge_row.addStretch(1)
        root.addLayout(badge_row)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(10)

        facts = QFrame()
        facts.setObjectName("lprCardFacts")
        facts_layout = QVBoxLayout(facts)
        facts_layout.setContentsMargins(12, 10, 12, 10)
        facts_layout.setSpacing(8)
        facts_layout.addLayout(self._info_row("Camera", record.camera_name or "Unknown Camera"))
        facts_layout.addLayout(self._info_row("Detected", record.created_text))
        meta_row.addWidget(facts, 1)

        if not compact:
            preview = QFrame()
            preview.setObjectName("lprCardPreview")
            preview_layout = QVBoxLayout(preview)
            preview_layout.setContentsMargins(10, 10, 10, 10)
            preview_layout.setSpacing(8)

            preview_title = QLabel("Plate Crop")
            preview_title.setObjectName("lprCardPreviewTitle")
            preview_layout.addWidget(preview_title)

            self.crop_image = RemoteImageLabel(net, "No Plate Crop")
            self.crop_image.setMinimumSize(106, 74)
            self.crop_image.setMaximumHeight(74)
            self.crop_image.setStyleSheet(
                "background:#050a12;border:1px solid #243244;border-radius:12px;color:#64748b;"
            )
            preview_layout.addWidget(self.crop_image)
            meta_row.addWidget(preview, 0)
        else:
            self.crop_image = None

        root.addLayout(meta_row)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 2, 0, 0)
        actions.setSpacing(8)

        self.details_btn = PrimeButton("Details", variant="primary", mode="filled", size="sm")
        self.details_btn.clicked.connect(lambda: self.opened.emit(self.record))
        actions.addWidget(self.details_btn, 1)

        self.search_btn = PrimeButton("Search Similar", variant="secondary", mode="outline", size="sm")
        self.search_btn.clicked.connect(lambda: self.search_requested.emit(self.record.number))
        actions.addWidget(self.search_btn, 1)
        root.addLayout(actions)

        self.image.set_image_url(_record_image_url(record, crop=False))
        if self.crop_image is not None:
            self.crop_image.set_image_url(_record_image_url(record, crop=True))

    def _badge(self, text: str, tone: str) -> QLabel:
        badge = QLabel(text)
        badge.setObjectName(f"lprCardBadge{tone.capitalize()}")
        return badge

    def _info_row(self, label_text: str, value_text: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        label = QLabel(label_text)
        label.setObjectName("lprCardFactLabel")
        row.addWidget(label, 0)

        value = QLabel(value_text)
        value.setObjectName("lprCardFactValue")
        value.setWordWrap(True)
        row.addWidget(value, 1)
        return row

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.opened.emit(self.record)
            event.accept()
            return
        super().mousePressEvent(event)


class LprSearchWorker(QObject):
    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, payload: Dict[str, object]) -> None:
        super().__init__()
        self._payload = dict(payload)

    def run(self) -> None:
        try:
            results = LprSearchService().search_lpr(LprSearchPayload(**self._payload))
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(results)


class LprDetailDialog(PrimeDialog):
    search_requested = Signal(str)

    _CONTENT_STYLE = """
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
        QLabel#detailPlateNumber {
            color: #34d399;
            font-size: 28px;
            font-weight: 800;
            letter-spacing: 1px;
        }
        QLabel#detailMetricValue {
            color: #f8fafc;
            font-size: 14px;
            font-weight: 700;
        }
    """

    def __init__(
        self,
        records: List[LprSearchResult],
        index: int,
        net: QNetworkAccessManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            title="Detection Details",
            parent=parent,
            width=1080,
            height=800,
            ok_text="Search Similar Plates",
            cancel_text="Close",
            draggable=False,
        )
        self._records = records
        self._index = index
        self._net = net

        # ── prev / next in footer (left side) ──
        self._prev_btn = PrimeButton("← Prev", variant="secondary", mode="outline", size="sm", width=90)
        self._next_btn = PrimeButton("Next →", variant="secondary", mode="outline", size="sm", width=90)
        self._prev_btn.clicked.connect(self._go_prev)
        self._next_btn.clicked.connect(self._go_next)
        footer = self.footer_widget.layout()
        footer.insertWidget(0, self._prev_btn)
        footer.insertWidget(1, self._next_btn)

        # ── footer: ok → search ──
        self.ok_button.clicked.disconnect()
        self.ok_button.clicked.connect(self._request_search)

        self._load()

    # ── navigation ──────────────────────────────────────────────────
    def _go_prev(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._load()

    def _go_next(self) -> None:
        if self._index < len(self._records) - 1:
            self._index += 1
            self._load()

    def _load(self) -> None:
        record = self._records[self._index]
        self.record = record
        total = len(self._records)
        self.set_title(f"Detection Details  ({self._index + 1} / {total})")
        self._prev_btn.setEnabled(self._index > 0)
        self._next_btn.setEnabled(self._index < total - 1)
        self.set_content(self._build_content(record), fill_height=True)

    # ── content builder ─────────────────────────────────────────────
    def _build_content(self, record: LprSearchResult) -> QWidget:
        content = QWidget()
        content.setFixedWidth(1032)
        content.setStyleSheet(self._CONTENT_STYLE)

        root = QVBoxLayout(content)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        root.addLayout(grid, 1)

        full_card = self._image_card("Full Camera Frame", _record_image_url(record, crop=False), "No Frame")
        grid.addWidget(full_card, 0, 0, 2, 2)

        crop_card = self._image_card("License Plate", _record_image_url(record, crop=True), "No Plate Crop")
        grid.addWidget(crop_card, 0, 2, 1, 1)

        plate_card = QFrame()
        plate_card.setObjectName("detailHighlightCard")
        plate_layout = QVBoxLayout(plate_card)
        plate_layout.setContentsMargins(18, 18, 18, 18)
        plate_layout.setSpacing(8)
        plate_title = QLabel("Plate Number")
        plate_title.setObjectName("detailMuted")
        plate_value = QLabel(record.number or "-")
        plate_value.setObjectName("detailPlateNumber")
        plate_layout.addWidget(plate_title)
        plate_layout.addWidget(plate_value)
        plate_layout.addStretch(1)
        grid.addWidget(plate_card, 1, 2, 1, 1)

        info_card = QFrame()
        info_card.setObjectName("detailInfoCard")
        info_layout = QGridLayout(info_card)
        info_layout.setContentsMargins(18, 18, 18, 18)
        info_layout.setHorizontalSpacing(14)
        info_layout.setVerticalSpacing(14)

        for idx, (label_text, value_text) in enumerate([
            ("Region", record.region or "Unknown"),
            ("Color", record.color_text),
            ("Type", record.plate_type or "-"),
            ("Camera", record.camera_name or "-"),
            ("Confidence", record.confidence_text),
            ("Detected At", record.created_text),
            ("Blacklist", "Yes" if record.is_blacklist else "No"),
            ("Whitelist", "Yes" if record.is_whitelist else "No"),
        ]):
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
            info_layout.addWidget(card, idx // 4, idx % 4)
        root.addWidget(info_card)

        return content

    def _image_card(self, title: str, image_url: str, fallback_text: str) -> QWidget:
        frame = QFrame()
        frame.setObjectName("detailImageCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        title_label = QLabel(title)
        title_label.setObjectName("detailCardTitle")
        layout.addWidget(title_label)

        image = RemoteImageLabel(self._net, fallback_text)
        image.setMinimumHeight(240 if fallback_text == "No Plate Crop" else 360)
        image.setStyleSheet("background:#090d12;border:1px solid #1f2937;border-radius:14px;color:#64748b;")
        layout.addWidget(image, 1)
        image.set_image_url(image_url)
        return frame

    def _request_search(self) -> None:
        self.search_requested.emit(self.record.number)
        self.accept()


class LprSearchPage(QWidget):
    navigate = Signal(str)

    def __init__(
        self,
        auth_store: Optional[AuthStore] = None,
        camera_store: Optional[CameraDepartmentStore] = None,
        search_store: Optional[LprSearchStore] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.auth_store = auth_store or AuthStore(AuthService())
        self.camera_store = camera_store or CameraDepartmentStore(CameraService())
        self.search_store = search_store or LprSearchStore(LprSearchService())
        self.net = QNetworkAccessManager(self)

        self.filter_panel_open = True
        self.filters_window_visible = True
        self.grid_view = False
        self.grid_columns = 3
        self.rows_per_page = 20
        self.current_page = 0
        self.current_record: Optional[LprSearchResult] = None
        self.has_searched = False
        self.search_in_progress = False
        self._search_thread: Optional[QThread] = None
        self._search_worker: Optional[LprSearchWorker] = None
        self._filter_sections: list[FilterAccordionSection] = []
        self._filters_slide_animation: Optional[QPropertyAnimation] = None

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
        root.setSpacing(12)
        self._root_layout = root

        self.sidebar = SearchSidebar("/search/lpr", self)
        self.sidebar.navigate.connect(self.navigate.emit)
        root.addWidget(self.sidebar, 0)

        self.date_from_input = ClearableDateTimeField("Start Time")
        self.date_to_input = ClearableDateTimeField("End Time")
        self._allow_horizontal_shrink(self.date_from_input)
        self._allow_horizontal_shrink(self.date_to_input)

        plate_section = FilterAccordionSection(
            "Plate Filters",
            "",
            expanded=True,
            collapsible=False,
        )
        self._filter_sections.append(plate_section)
        plate_section_layout = plate_section.body_layout
        self.compare_combo = PrimeSelect(
            options=[{"label": "Any Compare", "value": None}] + [{"label": l, "value": v} for l, v in COMPARE_OPTIONS],
            placeholder="Any Compare",
        )
        self._allow_horizontal_shrink(self.compare_combo)
        plate_section_layout.addWidget(self._field_block("Compare Rule", self.compare_combo))

        self.plate_input = PrimeInput(placeholder_text="Optional: enter plate number")
        _bind_ascii_digit_input(self.plate_input)
        self._allow_horizontal_shrink(self.plate_input)

        self.color_select = PrimeMultiSelect(COLOR_OPTIONS, placeholder="Select Colors")
        self._allow_horizontal_shrink(self.color_select)
        plate_section_layout.addWidget(self._field_block("Color", self.color_select))

        self.region_combo = PrimeSelect(
            options=[{"label": "All Regions", "value": None}] + [{"label": r, "value": r} for r in REGION_OPTIONS],
            placeholder="All Regions",
        )
        self._allow_horizontal_shrink(self.region_combo)
        plate_section_layout.addWidget(self._field_block("Region", self.region_combo))

        self.type_combo = PrimeSelect(
            options=[{"label": "Any Type", "value": None}] + [{"label": t, "value": t} for t in TYPE_OPTIONS],
            placeholder="Any Type",
        )
        self._allow_horizontal_shrink(self.type_combo)
        plate_section_layout.addWidget(self._field_block("Plate Type", self.type_combo))

        digits_conf_row = QGridLayout()
        digits_conf_row.setContentsMargins(0, 0, 0, 0)
        digits_conf_row.setHorizontalSpacing(10)
        digits_conf_row.setVerticalSpacing(10)

        self.number_digits_select = PrimeSelect(
            options=DIGITS_OPTIONS,
            placeholder="Any Digits",
        )
        self._allow_horizontal_shrink(self.number_digits_select)
        digits_conf_row.addWidget(self._field_block("Digits", self.number_digits_select), 0, 0)

        self.conf_select = PrimeSelect(
            options=CONFIDENCE_OPTIONS,
            placeholder="Any Confidence",
        )
        self._allow_horizontal_shrink(self.conf_select)
        self.conf_select.set_value(0)
        digits_conf_row.addWidget(self._field_block("Min Confidence", self.conf_select), 1, 0)
        plate_section_layout.addLayout(digits_conf_row)
        plate_section_layout.addStretch(1)
        source_section = FilterAccordionSection(
            "Source And Status",
            "",
            expanded=True,
            collapsible=False,
        )
        self._filter_sections.append(source_section)
        source_section_layout = source_section.body_layout
        self.camera_select = PrimeMultiSelect([], placeholder="Select Cameras")
        self._allow_horizontal_shrink(self.camera_select)
        source_section_layout.addWidget(self._field_block("Camera", self.camera_select))

        checks = QVBoxLayout()
        checks.setSpacing(12)
        self.blacklist_check = PrimeCheckBox("In Blacklist")
        self.whitelist_check = PrimeCheckBox("In Whitelist")
        checks.addWidget(self.blacklist_check)
        checks.addWidget(self.whitelist_check)
        source_section_layout.addLayout(checks)
        source_section_layout.addStretch(1)

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

        main_panel = QFrame()
        main_panel.setObjectName("resultsPanel")
        main_layout = QVBoxLayout(main_panel)
        main_layout.setContentsMargins(18, 16, 18, 18)
        main_layout.setSpacing(14)
        root.addWidget(main_panel, 1)
        root.setStretch(0, 0)
        root.setStretch(1, 1)
        root.setStretch(2, 4)

        self.hero_scroll = QScrollArea()
        self.hero_scroll.setObjectName("filtersScroll")
        self.hero_scroll.setWidgetResizable(True)
        self.hero_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.hero_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.hero_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.hero_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        filters_layout.addWidget(self.hero_scroll, 1)

        hero_frame = QFrame()
        hero_frame.setObjectName("searchHero")
        hero_frame.setMinimumWidth(0)
        self.hero_frame = hero_frame
        hero_layout = QVBoxLayout(hero_frame)
        hero_layout.setContentsMargins(18, 18, 18, 18)
        hero_layout.setSpacing(14)
        self.hero_scroll.setWidget(hero_frame)

        hero_head = QVBoxLayout()
        hero_head.setContentsMargins(0, 0, 0, 0)
        hero_head.setSpacing(6)
        hero_layout.addLayout(hero_head)

        hero_text = QVBoxLayout()
        hero_text.setContentsMargins(0, 0, 0, 0)
        hero_text.setSpacing(4)
        hero_head.addLayout(hero_text)

        hero_title = QLabel("LPR Search")
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
        time_layout = QGridLayout()
        time_layout.setContentsMargins(0, 0, 0, 0)
        time_layout.setHorizontalSpacing(12)
        time_layout.setVerticalSpacing(10)
        time_layout.setColumnStretch(0, 1)
        time_layout.setRowStretch(2, 1)
        hero_layout.addWidget(time_band)
        time_band.body_layout.addLayout(time_layout)
        time_band.body_layout.addStretch(1)
        time_layout.addWidget(
            self._hero_field_block(
                "Start Date & Time",
                self.date_from_input,
                "",
            ),
            0,
            0,
        )
        time_layout.addWidget(
            self._hero_field_block(
                "End Date & Time",
                self.date_to_input,
                "",
            ),
            1,
            0,
        )

        query_band = FilterAccordionSection(
            "Plate Lookup",
            "",
            expanded=True,
            collapsible=False,
        )
        self._filter_sections.append(query_band)
        query_layout = QVBoxLayout()
        query_layout.setContentsMargins(0, 0, 0, 0)
        query_layout.setSpacing(10)
        query_band.body_layout.addLayout(query_layout)
        query_layout.addWidget(
            self._hero_field_block(
                "Plate Number",
                self.plate_input,
                "",
            )
        )
        query_layout.addStretch(1)
        hero_layout.addWidget(query_band)
        hero_layout.addWidget(plate_section)
        hero_layout.addWidget(source_section)

        for section in self._filter_sections:
            section.toggled.connect(self._sync_filter_toggle_ui)

        self.reset_btn = PrimeButton("Reset Filters", variant="secondary", mode="outline", size="sm")
        self.reset_btn.clicked.connect(self.reset_filters)

        self.filter_toggle_btn = PrimeButton("Hide Filters", variant="secondary", mode="outline", size="sm")
        self.filter_toggle_btn.clicked.connect(self.toggle_filter_panel)
        self.filter_toggle_btn.hide()

        self.search_btn = PrimeButton("Search Records", variant="primary", mode="filled", size="sm")
        self.search_btn.clicked.connect(self.perform_search)

        hero_actions = QVBoxLayout()
        hero_actions.setContentsMargins(0, 0, 0, 0)
        hero_actions.setSpacing(8)
        self._allow_horizontal_shrink(self.filter_toggle_btn)
        self._allow_horizontal_shrink(self.reset_btn)
        self._allow_horizontal_shrink(self.search_btn)
        hero_actions.addWidget(self.reset_btn)
        hero_actions.addWidget(self.search_btn)
        hero_layout.addLayout(hero_actions)
        self._sync_filter_toggle_ui()
        self._sync_filters_window_ui()
        self._update_filters_scroll_height()

        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("resultsToolbar")
        toolbar = QHBoxLayout(toolbar_frame)
        toolbar.setContentsMargins(14, 14, 14, 14)
        toolbar.setSpacing(10)
        main_layout.addWidget(toolbar_frame)

        self.results_filter_btn = SidebarToggleButton(self.filters_window_visible, self)
        self.results_filter_btn.clicked.connect(self.toggle_filters_window)
        toolbar.addWidget(self.results_filter_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        left_cluster = QVBoxLayout()
        left_cluster.setContentsMargins(0, 0, 0, 0)
        left_cluster.setSpacing(3)
        self.page_title = QLabel("LPR Search Results")
        self.page_title.setObjectName("pageTitle")
        self.page_summary = QLabel("No search has been run yet.")
        self.page_summary.setObjectName("pageSummary")
        left_cluster.addWidget(self.page_title)
        left_cluster.addWidget(self.page_summary)
        toolbar.addLayout(left_cluster, 1)

        self.grid_cols_combo = PrimeSelect(
            options=[{"label": f"{c} Col", "value": c} for c in GRID_OPTIONS],
            placeholder="3 Col",
        )
        self.grid_cols_combo.set_value(3)
        self.grid_cols_combo.value_changed.connect(self._on_grid_columns_changed)
        toolbar.addWidget(self.grid_cols_combo)

        self.rows_combo = PrimeSelect(
            options=[{"label": f"{c} Rows", "value": c} for c in ROWS_PER_PAGE_OPTIONS],
            placeholder="20 Rows",
        )
        self.rows_combo.set_value(20)
        self.rows_combo.value_changed.connect(self._on_rows_changed)
        toolbar.addWidget(self.rows_combo)

        self.export_btn = PrimeButton("Export", variant="primary", mode="filled", size="sm")
        self.export_btn.clicked.connect(self.export_csv)
        toolbar.addWidget(self.export_btn)

        view_switch = QFrame()
        view_switch.setObjectName("viewSwitch")
        switch_layout = QHBoxLayout(view_switch)
        switch_layout.setContentsMargins(4, 4, 4, 4)
        switch_layout.setSpacing(4)

        self.table_btn = QToolButton()
        self.table_btn.setObjectName("viewToggleActive")
        self.table_btn.setText("List")
        self.table_btn.clicked.connect(lambda: self.set_view_mode(False))
        switch_layout.addWidget(self.table_btn)

        self.grid_btn = QToolButton()
        self.grid_btn.setObjectName("viewToggle")
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
        self.grid_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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

        self.prev_btn = PrimeButton("← Prev", variant="secondary", mode="outline", size="sm")
        self.prev_btn.clicked.connect(self._go_prev_page)
        pagination.addWidget(self.prev_btn)

        self.next_btn = PrimeButton("Next →", variant="secondary", mode="outline", size="sm")
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
            row_height=64,
            show_footer=True,
        )
        self.table.set_columns(
            [
                PrimeTableColumn("plate", "Plate Number", stretch=True),
                PrimeTableColumn("camera", "Camera", stretch=True),
                PrimeTableColumn("region", "Region", stretch=True),
                PrimeTableColumn("color", "Color", stretch=True),
                PrimeTableColumn("type", "Type", stretch=True),
                PrimeTableColumn("created", "Date & Time", stretch=True),
                PrimeTableColumn("actions", "Actions", width=160, sortable=False, searchable=False),
            ]
        )
        self.table.set_cell_widget_factory("actions", self._table_action_widget)
        self.table.row_clicked.connect(self._on_table_row_clicked)
        table_layout.addWidget(self.table, 1)
        self.results_stack.addWidget(self.table_page)

        self.refresh()

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
            QFrame#filterSection {
                background: #141922;
                border: 1px solid #2c3442;
                border-radius: 16px;
            }
            QLabel#pageTitle {
                color: #f8fafc;
                font-size: 22px;
                font-weight: 800;
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
            QLabel#heroSectionTitle {
                color: #eff6ff;
                font-size: 14px;
                font-weight: 800;
            }
            QLabel#heroSectionHint {
                color: #a9bfdc;
                font-size: 11px;
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
            QLabel#sectionTitle {
                color: #f8fafc;
                font-size: 14px;
                font-weight: 800;
            }
            QLabel#sectionHint {
                color: #94a3b8;
                font-size: 11px;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QTimeEdit {
                background: #232a34;
                border: 1px solid #364152;
                border-radius: 10px;
                color: #f8fafc;
                min-height: 38px;
                padding: 0 12px;
            }
            QWidget#fieldBlock {
                background: transparent;
            }
            QWidget#heroFieldBlock {
                background: transparent;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
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
            QFrame#lprCard {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #172437,
                    stop: 0.58 #16202d,
                    stop: 1 #101720
                );
                border: 1px solid #31506f;
                border-radius: 20px;
            }
            QFrame#lprCard:hover {
                border: 1px solid #7dd3fc;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #1a2b41,
                    stop: 0.62 #1b2737,
                    stop: 1 #13202c
                );
            }
            QFrame#lprCardMedia,
            QFrame#lprCardFacts {
                background: rgba(10, 17, 28, 0.72);
                border: 1px solid #2c3b50;
                border-radius: 14px;
            }
            QFrame#lprCardPreview {
                background: rgba(7, 12, 22, 0.88);
                border: 1px solid #31455f;
                border-radius: 14px;
                min-width: 128px;
                max-width: 128px;
            }
            QLabel#lprCardEyebrow {
                color: #7dd3fc;
                font-size: 10px;
                font-weight: 900;
                letter-spacing: 1px;
            }
            QLabel#lprCardMediaTitle, QLabel#lprCardPreviewTitle {
                color: #dbeafe;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0.6px;
            }
            QLabel#lprCardMediaHint {
                background: rgba(56, 189, 248, 0.12);
                color: #bae6fd;
                border: 1px solid rgba(56, 189, 248, 0.26);
                border-radius: 9px;
                padding: 4px 8px;
                font-size: 10px;
                font-weight: 800;
            }
            QLabel#lprCardTitle {
                color: #f8fafc;
                font-size: 20px;
                font-weight: 900;
                letter-spacing: 1px;
            }
            QLabel#lprCardChip {
                background: rgba(34, 197, 94, 0.14);
                color: #bbf7d0;
                border: 1px solid rgba(34, 197, 94, 0.3);
                border-radius: 10px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: 800;
            }
            QLabel#lprCardBadgeNeutral,
            QLabel#lprCardBadgeAccent,
            QLabel#lprCardBadgeMuted,
            QLabel#lprCardBadgeDanger,
            QLabel#lprCardBadgeSuccess {
                border-radius: 10px;
                padding: 4px 9px;
                font-size: 11px;
                font-weight: 800;
            }
            QLabel#lprCardBadgeNeutral {
                background: rgba(148, 163, 184, 0.14);
                color: #dbeafe;
                border: 1px solid rgba(148, 163, 184, 0.24);
            }
            QLabel#lprCardBadgeAccent {
                background: rgba(59, 130, 246, 0.16);
                color: #93c5fd;
                border: 1px solid rgba(59, 130, 246, 0.28);
            }
            QLabel#lprCardBadgeMuted {
                background: rgba(250, 204, 21, 0.12);
                color: #fde68a;
                border: 1px solid rgba(250, 204, 21, 0.22);
            }
            QLabel#lprCardBadgeDanger {
                background: rgba(248, 113, 113, 0.14);
                color: #fecaca;
                border: 1px solid rgba(248, 113, 113, 0.26);
            }
            QLabel#lprCardBadgeSuccess {
                background: rgba(74, 222, 128, 0.14);
                color: #bbf7d0;
                border: 1px solid rgba(74, 222, 128, 0.26);
            }
            QLabel#lprCardFactLabel {
                color: #8fa5bf;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#lprCardFactValue {
                color: #f8fafc;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton#lprCardAction, QPushButton#lprCardGhostAction {
                min-height: 36px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton#lprCardAction {
                background: #2563eb;
                border: none;
                color: white;
            }
            QPushButton#lprCardAction:hover {
                background: #1d4ed8;
            }
            QPushButton#lprCardGhostAction {
                background: #27303d;
                border: 1px solid #374151;
                color: #e2e8f0;
            }
            QPushButton#lprCardGhostAction:hover {
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

    def _section_card(self, title_text: str, hint_text: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("filterSection")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel(title_text)
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        hint = QLabel(hint_text)
        hint.setObjectName("sectionHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return frame, layout

    def _on_auth_changed(self) -> None:
        current_user = self.auth_store.current_user
        if current_user is None:
            self.camera_store.get_camera_for_user(None, silent=True)
            return
        department_id = None if current_user.is_superadmin else current_user.department_id
        self.camera_store.get_camera_for_user(department_id, silent=True)

    def _refresh_camera_options(self) -> None:
        options = [
            {"label": camera.name or f"Camera #{camera.id}", "value": camera.id}
            for camera in sorted(self.camera_store.cameras, key=lambda item: (item.name or "").lower())
            if int(getattr(camera, "id", 0) or 0) > 0
        ]
        previous = set(self.camera_select.value())
        self.camera_select.set_options(options)
        self.camera_select.set_value([item for item in previous if item in {opt["value"] for opt in options}])

    def _apply_default_date_range(self) -> None:
        now = datetime.now(SEARCH_TIMEZONE).replace(second=0, microsecond=0)
        self.date_to_input.set_value(now)
        self.date_from_input.set_value(now - timedelta(hours=24))

    def _sync_filter_toggle_ui(self, *_args) -> None:
        if self._filter_sections and all(not section.is_collapsible() for section in self._filter_sections):
            self.filter_panel_open = True
            self.filter_toggle_btn.setText("Hide Filters")
            return
        open_count = sum(1 for section in self._filter_sections if section.is_expanded())
        self.filter_panel_open = open_count > 0
        if open_count <= 0:
            self.filter_toggle_btn.setText("Show Filters")
        elif open_count >= len(self._filter_sections):
            self.filter_toggle_btn.setText("Hide Filters")
        else:
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

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_filters_panel_width(animate=False)
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

    def reset_filters(self) -> None:
        self.has_searched = False
        self._apply_default_date_range()
        self.compare_combo.set_value(None)
        self.plate_input.clear()
        self.color_select.set_value([])
        self.region_combo.set_value(None)
        self.type_combo.set_value(None)
        self.camera_select.set_value([])
        self.number_digits_select.set_value(None)
        self.conf_select.set_value(0)
        self.blacklist_check.setChecked(False)
        self.whitelist_check.setChecked(False)
        self.search_store.clear()
        self.current_page = 0
        self._set_filter_panel_visible(False)
        self.refresh()

    def _current_payload(self) -> Dict[str, object]:
        conf_value = self.conf_select.value()
        conf = int(conf_value) if isinstance(conf_value, int) else 0
        digits_value = self.number_digits_select.value()
        number_digits = int(digits_value) if isinstance(digits_value, int) else None
        return {
            "start": 0,
            "length": max(300, self.rows_per_page * 4),
            "order_col": 0,
            "order": "desc",
            "date_from": self.date_from_input.value(),
            "date_to": self.date_to_input.value(),
            "compare": self.compare_combo.value(),
            "plate_no": normalize_ascii_digits(self.plate_input.text()).strip(),
            "color_names": list(self.color_select.value()),
            "region": self.region_combo.value(),
            "type": self.type_combo.value(),
            "camera_ids": list(self.camera_select.value()),
            "conf": conf,
            "number_digits": number_digits,
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
        self.has_searched = True
        self.search_in_progress = True
        self.search_store.loading = True
        self.search_btn.setEnabled(False)
        self.search_btn.setText("Searching...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        thread = QThread()
        worker = LprSearchWorker(payload)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_search_finished)
        worker.failed.connect(self._on_search_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_search_thread)
        thread.finished.connect(lambda: _ACTIVE_SEARCH_THREADS.discard(thread))
        _ACTIVE_SEARCH_THREADS.add(thread)
        self._search_thread = thread
        self._search_worker = worker
        thread.start()
        self.refresh()

    def _on_search_finished(self, results: List[LprSearchResult]) -> None:
        self.search_store.results = list(results)
        self.search_store.loading = False
        self.search_in_progress = False
        self.current_page = 0
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
        if QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Search Records")
        self.refresh()
        self._show_error(text)

    def _clear_search_thread(self) -> None:
        self._search_thread = None
        self._search_worker = None

    def _on_grid_columns_changed(self, value=None) -> None:
        if value is None:
            value = self.grid_cols_combo.value()
        if isinstance(value, int) and value > 0:
            self.grid_columns = value
        self.refresh()

    def _on_rows_changed(self, value=None) -> None:
        if value is None:
            value = self.rows_combo.value()
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

    def _paged_results(self) -> List[LprSearchResult]:
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
        if self.search_in_progress or self.search_store.loading:
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
                    "Search for LPR Records"
                    if not self.has_searched
                    else ("No Results Found" if total == 0 else "No Results On This Page")
                ),
                hint=(
                    "Use the filter panel to search by plate, date, camera, and region."
                    if not self.has_searched
                    else (
                        "We could not find license plate records matching the current filters."
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
            card = LprResultCard(record, self.net, compact=compact)
            card.opened.connect(self.open_detail_dialog)
            card.search_requested.connect(self.search_similar_plate)
            self.grid_layout.addWidget(card, index // columns, index % columns)

        start = self.current_page * self.rows_per_page + 1
        end = start + len(page_results) - 1
        self.grid_meta.setText(f"{start}-{end} of {total}")

    def _refresh_table(self) -> None:
        rows = []
        for record in self.search_store.results:
            rows.append(
                {
                    "plate": record.number,
                    "camera": record.camera_name,
                    "region": record.region or "Unknown",
                    "color": record.color_text,
                    "type": record.plate_type or "-",
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

    def _table_action_widget(self, row: Dict[str, object]) -> QWidget:
        record = row.get("_record")
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        view_btn = QToolButton()
        view_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        view_btn.setToolTip("Open details")
        view_btn.setObjectName("tableActionButton")
        view_icon = QIcon(_icon_path("view.svg"))
        if not view_icon.isNull():
            view_btn.setIcon(view_icon)
        else:
            view_btn.setText("V")
        view_btn.clicked.connect(lambda: self.open_detail_dialog(record))
        layout.addWidget(view_btn)

        search_btn = QToolButton()
        search_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        search_btn.setToolTip("Search similar plates")
        search_btn.setObjectName("tableActionButton")
        search_icon = QIcon(_icon_path("search.svg"))
        if not search_icon.isNull():
            search_btn.setIcon(search_icon)
        else:
            search_btn.setText("S")
        search_btn.clicked.connect(lambda: self.search_similar_plate(record.number if isinstance(record, LprSearchResult) else ""))
        layout.addWidget(search_btn)
        return wrapper

    def _on_table_row_clicked(self, row: Dict[str, object]) -> None:
        record = row.get("_record")
        if isinstance(record, LprSearchResult):
            self.open_detail_dialog(record)

    def open_detail_dialog(self, record: object) -> None:
        if not isinstance(record, LprSearchResult):
            return
        records = list(self.search_store.results)
        try:
            index = next(i for i, r in enumerate(records) if r is record or r.id == record.id)
        except StopIteration:
            index = 0
        dialog = LprDetailDialog(records, index, self.net, self)
        dialog.search_requested.connect(self.search_similar_plate)
        dialog.exec()

    def search_similar_plate(self, plate_number: str) -> None:
        plate = normalize_ascii_digits(plate_number).strip()
        if not plate:
            return
        self.plate_input.setText(plate)
        self.perform_search()

    def export_csv(self) -> None:
        if not self.search_store.results:
            return
        path = choose_restricted_save_file_path(
            self,
            "Export LPR Search",
            os.path.expanduser("~/LPRSearch.csv"),
            "CSV Files (*.csv)",
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Plate Number", "Region", "Color", "Type", "Confidence", "Camera", "Note", "Date & Time"])
                for record in self.search_store.results:
                    writer.writerow(
                        [
                            record.number,
                            record.region,
                            record.color_text,
                            record.plate_type,
                            record.confidence_text,
                            record.camera_name,
                            record.note,
                            record.created_text,
                        ]
                    )
        except Exception as exc:
            self._show_error(f"Failed to export CSV: {exc}")
            return
        show_toast_message(self, "success", "Export Complete", f"Results exported to:\n{path}")

    def _show_error(self, text: str) -> None:
        show_toast_message(self, "error", "Error", text)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        p.fillPath(path, QColor(Constants.DARK_BG))   # dark bg — cards float above it
        super().paintEvent(event)
