from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QStyle,
)

from app.services.home.settings_service import SettingsService
from app.store.home.setting.settings_store import SettingsStore
from app.ui.button import PrimeButton
from app.ui.dialog import PrimeDialog
from app.ui.input import PrimeInput
from app.ui.toast import PrimeToastHost


_MEDIA_ROOTS = ("/media", "/mnt", "/run/media")
_DEVICE_IMAGE_DIR_NAMES = ("Desktop", "Pictures", "Downloads", "Documents", "DCIM")
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
_TEXT_PREVIEW_SUFFIXES = {
    ".csv",
    ".json",
    ".jng",
    ".jpeg",
    ".jpg",
    ".log",
    ".md",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
    ".ini",
    ".conf",
}


@dataclass(frozen=True)
class BrowserRoot:
    label: str
    path: str
    description: str
    exists: bool = True


@dataclass(frozen=True)
class BrowserEntry:
    name: str
    path: str
    is_dir: bool
    type_label: str
    size_text: str
    modified_text: str


def _normalize_dir(path: str) -> str:
    expanded = os.path.abspath(os.path.expanduser(str(path or "").strip()))
    return os.path.realpath(expanded)


def _path_within(root_path: str, candidate_path: str) -> bool:
    root_real = _normalize_dir(root_path)
    candidate_real = _normalize_dir(candidate_path)
    return candidate_real == root_real or candidate_real.startswith(root_real + os.sep)


def _is_media_path(path: str) -> bool:
    normalized = _normalize_dir(path)
    return any(normalized == base or normalized.startswith(base + os.sep) for base in _MEDIA_ROOTS)


def _directory_has_entries(path: str) -> bool:
    try:
        with os.scandir(path) as entries:
            return next(entries, None) is not None
    except OSError:
        return False


def _is_usable_media_root(path: str) -> bool:
    return os.path.isdir(path) and (os.path.ismount(path) or _directory_has_entries(path))


def _fallback_media_mount_candidates() -> list[str]:
    candidates: set[str] = set()
    for base in _MEDIA_ROOTS:
        if not os.path.isdir(base):
            continue
        try:
            first_level = [
                os.path.join(base, name)
                for name in os.listdir(base)
                if os.path.isdir(os.path.join(base, name))
            ]
        except OSError:
            first_level = []

        if not first_level and _is_usable_media_root(base):
            candidates.add(os.path.abspath(base))

        for path in first_level:
            try:
                second_level = [
                    os.path.join(path, name)
                    for name in os.listdir(path)
                    if os.path.isdir(os.path.join(path, name))
                ]
            except OSError:
                second_level = []

            if second_level:
                for nested in second_level:
                    if _is_usable_media_root(nested):
                        candidates.add(os.path.abspath(nested))
                continue

            if _is_usable_media_root(path):
                candidates.add(os.path.abspath(path))

    return sorted(candidates)


def _load_record_roots() -> list[BrowserRoot]:
    store = SettingsStore(SettingsService())
    record_setting = store.load_record_setting() or store.record_setting

    roots: list[BrowserRoot] = []
    save_path = str(getattr(record_setting, "save_path", "") or "").strip()
    if save_path:
        normalized = os.path.abspath(os.path.expanduser(save_path))
        roots.append(
            BrowserRoot(
                label="Recorder Save Path",
                path=normalized,
                description="Configured in Settings > Record.",
                exists=os.path.isdir(normalized),
            )
        )
    return roots


def _discover_media_roots() -> list[BrowserRoot]:
    discovered: set[str] = set()
    try:
        with open("/proc/mounts", "r", encoding="utf-8") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) < 2:
                    continue
                mount_path = parts[1].replace("\\040", " ")
                if any(
                    mount_path == base or mount_path.startswith(base + os.sep)
                    for base in _MEDIA_ROOTS
                ) and _is_usable_media_root(mount_path):
                    discovered.add(os.path.abspath(mount_path))
    except OSError:
        pass

    if not discovered:
        for candidate in _fallback_media_mount_candidates():
            if _is_usable_media_root(candidate):
                discovered.add(candidate)

    roots: list[BrowserRoot] = []
    for path in sorted(discovered):
        normalized = os.path.abspath(path)
        label = f"Media Storage ({os.path.basename(normalized) or normalized})"
        roots.append(
            BrowserRoot(
                label=label,
                path=normalized,
                description="Mounted media storage.",
                exists=os.path.isdir(normalized),
            )
        )
    return roots


def _device_home_roots() -> list[BrowserRoot]:
    home_dir = os.path.abspath(os.path.expanduser("~"))
    if not os.path.isdir(home_dir):
        return []

    roots: list[BrowserRoot] = [
        BrowserRoot(
            label="Device Storage",
            path=home_dir,
            description="Local files on this device.",
            exists=True,
        )
    ]

    for name in _DEVICE_IMAGE_DIR_NAMES:
        candidate = os.path.join(home_dir, name)
        if not os.path.isdir(candidate):
            continue
        roots.append(
            BrowserRoot(
                label=f"Device {name}",
                path=candidate,
                description=f"{name} folder on this device.",
                exists=True,
            )
        )
    return roots


def device_image_browser_roots() -> list[BrowserRoot]:
    return _device_home_roots()


def load_allowed_browser_roots(extra_roots: Optional[Iterable[BrowserRoot]] = None) -> list[BrowserRoot]:
    deduped: dict[str, BrowserRoot] = {}
    combined_roots = list(extra_roots or []) + _load_record_roots() + _discover_media_roots()
    for root in combined_roots:
        key = _normalize_dir(root.path) if root.exists else os.path.abspath(root.path)
        if key in deduped:
            continue
        deduped[key] = root
    return list(deduped.values())


def _parse_patterns(filters: str) -> tuple[str, ...]:
    for chunk in str(filters or "").split(";;"):
        text = chunk.strip()
        if not text:
            continue
        start = text.find("(")
        end = text.rfind(")")
        if start < 0 or end <= start:
            continue
        patterns = tuple(part.strip() for part in text[start + 1 : end].split() if part.strip())
        if not patterns:
            continue
        if any(pattern in {"*", "*.*"} for pattern in patterns):
            return ()
        return patterns
    return ()


def _matches_patterns(filename: str, patterns: tuple[str, ...]) -> bool:
    if not patterns:
        return True
    lowered = filename.lower()
    return any(fnmatch.fnmatch(lowered, pattern.lower()) for pattern in patterns)


def _default_extension(patterns: tuple[str, ...]) -> str:
    for pattern in patterns:
        if pattern.startswith("*.") and "*" not in pattern[2:] and "?" not in pattern[2:]:
            return pattern[1:]
    return ""


def _format_bytes(size_bytes: int) -> str:
    size = float(max(0, int(size_bytes or 0)))
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return "0 B"


def _format_modified(timestamp: float) -> str:
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "-"


def _entry_type_label(path: str, is_dir: bool) -> str:
    if is_dir:
        return "Folder"
    suffix = os.path.splitext(path)[1].lower()
    mapping = {
        ".csv": "CSV",
        ".dat": "DAT",
        ".jpg": "IMG",
        ".jpeg": "IMG",
        ".png": "IMG",
        ".bmp": "IMG",
        ".webp": "IMG",
        ".json": "JSON",
        ".log": "LOG",
        ".mp4": "VID",
        ".avi": "VID",
        ".mkv": "VID",
        ".txt": "TXT",
    }
    if suffix in mapping:
        return mapping[suffix]
    if suffix:
        return suffix[1:5].upper()
    return "FILE"


def _first_existing_directory(path: str) -> str:
    candidate = os.path.abspath(os.path.expanduser(str(path or "").strip()))
    if not candidate:
        return ""
    while candidate and not os.path.exists(candidate):
        parent = os.path.dirname(candidate)
        if parent == candidate:
            break
        candidate = parent
    if os.path.isdir(candidate):
        return os.path.realpath(candidate)
    if os.path.isfile(candidate):
        return os.path.realpath(os.path.dirname(candidate))
    return ""


class RestrictedBrowserWidget(QWidget):
    selection_changed = Signal()
    accepted = Signal(str)

    def __init__(
        self,
        mode: str = "browse",
        filters: str = "All Files (*)",
        suggested_path: str = "",
        extra_roots: Optional[Iterable[BrowserRoot]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode
        self.filters = filters
        self._allowed_patterns = _parse_patterns(filters)
        self._default_suffix = _default_extension(self._allowed_patterns)
        self._suggested_path = str(suggested_path or "").strip()
        self._extra_roots = list(extra_roots or [])
        self._roots: list[BrowserRoot] = []
        self._roots_signature: tuple[tuple[str, bool], ...] = tuple()
        self._entries: list[BrowserEntry] = []
        self._visible_entries: list[BrowserEntry] = []
        self._root_buttons: list[tuple[BrowserRoot, QToolButton]] = []
        self._current_path = ""
        self.toast = PrimeToastHost(self)

        self._build_ui()
        self._apply_style()
        self._storage_poll_timer = QTimer(self)
        self._storage_poll_timer.setInterval(2000)
        self._storage_poll_timer.timeout.connect(self._poll_storage_changes)
        self._storage_poll_timer.start()
        self.reload_allowed_roots()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        sidebar = QFrame(self)
        sidebar.setObjectName("browserSidebar")
        sidebar.setFixedWidth(250)
        root.addWidget(sidebar)

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(18, 18, 18, 18)
        sidebar_layout.setSpacing(12)

        sidebar_title = QLabel("Allowed Storage")
        sidebar_title.setObjectName("browserSidebarTitle")
        sidebar_layout.addWidget(sidebar_title)

        sidebar_subtitle = QLabel(
            "This browser only shows the approved folders listed below."
        )
        sidebar_subtitle.setObjectName("browserSidebarSubtitle")
        sidebar_subtitle.setWordWrap(True)
        sidebar_layout.addWidget(sidebar_subtitle)

        self.root_buttons_frame = QFrame(sidebar)
        self.root_buttons_frame.setObjectName("browserRootsFrame")
        self.root_buttons_layout = QVBoxLayout(self.root_buttons_frame)
        self.root_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.root_buttons_layout.setSpacing(8)
        sidebar_layout.addWidget(self.root_buttons_frame)

        self.rule_label = QLabel()
        self.rule_label.setObjectName("browserRuleLabel")
        self.rule_label.setWordWrap(True)
        sidebar_layout.addWidget(self.rule_label)
        sidebar_layout.addStretch(1)

        self.reload_roots_button = PrimeButton("Reload Roots", variant="info", mode="outline", size="sm", width=140)
        self.reload_roots_button.clicked.connect(self.reload_allowed_roots)
        sidebar_layout.addWidget(self.reload_roots_button)

        main = QFrame(self)
        main.setObjectName("browserMain")
        root.addWidget(main, 1)

        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(12)

        path_card = QFrame(main)
        path_card.setObjectName("browserPathCard")
        path_layout = QVBoxLayout(path_card)
        path_layout.setContentsMargins(16, 14, 16, 14)
        path_layout.setSpacing(4)

        path_title = QLabel("Current Location")
        path_title.setObjectName("browserPathTitle")
        path_layout.addWidget(path_title)

        self.path_value_label = QLabel("No storage available")
        self.path_value_label.setObjectName("browserPathValue")
        self.path_value_label.setWordWrap(True)
        path_layout.addWidget(self.path_value_label)
        main_layout.addWidget(path_card)

        tools_row = QHBoxLayout()
        tools_row.setContentsMargins(0, 0, 0, 0)
        tools_row.setSpacing(10)

        self.search_input = PrimeInput(placeholder_text="Filter current folder")
        self.search_input.textChanged.connect(self._rebuild_table)
        tools_row.addWidget(self.search_input, 1)

        self.up_button = PrimeButton("Up", variant="light", mode="outline", size="sm", width=92)
        self.up_button.clicked.connect(self._go_up)
        tools_row.addWidget(self.up_button)

        self.refresh_button = PrimeButton("Refresh", variant="info", mode="ghost", size="sm", width=110)
        self.refresh_button.clicked.connect(self.reload_allowed_roots)
        self.refresh_button.setToolTip("Rescan storage devices and refresh the current folder.")
        tools_row.addWidget(self.refresh_button)

        self.details_button = PrimeButton("Details", variant="secondary", mode="ghost", size="sm", width=110)
        self.details_button.clicked.connect(self._show_selected_details)
        tools_row.addWidget(self.details_button)

        main_layout.addLayout(tools_row)

        self.table_frame = QFrame(main)
        self.table_frame.setObjectName("browserTableFrame")
        table_layout = QVBoxLayout(self.table_frame)
        table_layout.setContentsMargins(2, 2, 2, 2)
        table_layout.setSpacing(0)

        self.table = QTableWidget(0, 4, self.table_frame)
        self.table.setHorizontalHeaderLabels(["Name", "Type", "Size", "Modified"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.cellDoubleClicked.connect(self._on_cell_activated)
        table_layout.addWidget(self.table)
        main_layout.addWidget(self.table_frame, 1)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(10)

        self.status_label = QLabel()
        self.status_label.setObjectName("browserStatusLabel")
        self.status_label.setWordWrap(True)
        bottom_row.addWidget(self.status_label, 1)
        main_layout.addLayout(bottom_row)

        self.filename_row = QFrame(main)
        self.filename_row.setObjectName("browserFilenameRow")
        filename_layout = QHBoxLayout(self.filename_row)
        filename_layout.setContentsMargins(0, 0, 0, 0)
        filename_layout.setSpacing(10)

        filename_label = QLabel("File Name")
        filename_label.setObjectName("browserFilenameLabel")
        filename_layout.addWidget(filename_label)

        self.filename_input = PrimeInput(placeholder_text="Enter file name")
        self.filename_input.textChanged.connect(self._on_selection_changed)
        filename_layout.addWidget(self.filename_input, 1)
        main_layout.addWidget(self.filename_row)
        self.filename_row.setVisible(self.mode == "save_file")

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: transparent;
                color: #e5edf8;
            }
            QFrame#browserSidebar,
            QFrame#browserMain {
                background: #111722;
                border: 1px solid #243042;
                border-radius: 16px;
            }
            QLabel#browserSidebarTitle,
            QLabel#browserPathTitle {
                color: #f8fbff;
                font-size: 17px;
                font-weight: 700;
            }
            QLabel#browserSidebarSubtitle,
            QLabel#browserRuleLabel,
            QLabel#browserStatusLabel {
                color: #9fb0c6;
                font-size: 12px;
                line-height: 1.45em;
            }
            QFrame#browserRootsFrame {
                background: transparent;
                border: none;
            }
            QToolButton#browserRootButton {
                background: #141d29;
                border: 1px solid #263446;
                border-radius: 12px;
                color: #d7e3f4;
                font-size: 12px;
                font-weight: 600;
                padding: 12px 14px;
                text-align: left;
            }
            QToolButton#browserRootButton:hover {
                border-color: #3b82f6;
                background: #182335;
            }
            QToolButton#browserRootButton:checked {
                background: #172949;
                border-color: #4f8cff;
                color: #ffffff;
            }
            QToolButton#browserRootButton:disabled {
                color: #6f8198;
                background: #121922;
                border-color: #202b3c;
            }
            QFrame#browserPathCard,
            QFrame#browserFilenameRow {
                background: #141d29;
                border: 1px solid #263446;
                border-radius: 14px;
            }
            QFrame#browserTableFrame {
                background: #0f1620;
                border: 1px solid #243042;
                border-radius: 14px;
            }
            QLabel#browserPathValue {
                color: #dbe8f7;
                font-size: 14px;
                font-weight: 600;
            }
            QLabel#browserFilenameLabel {
                color: #dbe8f7;
                font-size: 13px;
                font-weight: 600;
                min-width: 76px;
            }
            QTableWidget {
                background: #0f1620;
                border: none;
                border-radius: 10px;
                gridline-color: transparent;
                selection-background-color: #1e3a67;
                selection-color: #ffffff;
                alternate-background-color: #101925;
            }
            QTableWidget QTableCornerButton::section {
                background: #131c28;
                border: none;
                border-bottom: 1px solid #243042;
            }
            QHeaderView::section {
                background: #131c28;
                border: none;
                border-bottom: 1px solid #243042;
                color: #94a8c2;
                font-size: 12px;
                font-weight: 700;
                padding: 10px 12px;
            }
            QTableWidget::item {
                padding: 6px 10px;
                border-bottom: 1px solid rgba(48, 65, 90, 0.45);
            }
            QTableWidget::item:selected {
                background: #1e3a67;
                color: #ffffff;
            }
            """
        )

    def _build_roots_signature(self, roots: Iterable[BrowserRoot]) -> tuple[tuple[str, bool], ...]:
        signature: list[tuple[str, bool]] = []
        for root in roots:
            key = _normalize_dir(root.path) if root.exists and os.path.isdir(root.path) else os.path.abspath(root.path)
            signature.append((key, root.exists))
        return tuple(signature)

    def _folder_icon(self):
        return self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)

    def _display_location(self, path: str) -> str:
        normalized = _normalize_dir(path)
        root = self._root_for_path(normalized)
        if root is None:
            return os.path.basename(normalized) or "Unknown Folder"
        root_path = _normalize_dir(root.path)
        relative = os.path.relpath(normalized, root_path)
        if relative in {"", "."}:
            return root.label
        parts = [part for part in relative.split(os.sep) if part and part != "."]
        return " / ".join([root.label, *parts])

    def _apply_allowed_roots(self, roots: list[BrowserRoot]) -> None:
        previous_path = self._current_path
        self._roots = roots
        self._roots_signature = self._build_roots_signature(roots)
        self._rebuild_root_buttons()

        preferred_path = self._resolve_start_path(previous_path or self._suggested_path)
        if preferred_path:
            self._set_current_path(preferred_path)
        else:
            self._current_path = ""
            self._entries = []
            self._visible_entries = []
            self.path_value_label.setText("No allowed storage is currently available.")
            self.status_label.setText("Configure a recorder save path or mount external media to use the browser.")
            self.table.setRowCount(0)
            self._update_rule_text()
            self._on_selection_changed()

    def reload_allowed_roots(self) -> None:
        self._apply_allowed_roots(load_allowed_browser_roots(self._extra_roots))

    def _poll_storage_changes(self) -> None:
        if not self.isVisible():
            return
        latest_roots = load_allowed_browser_roots(self._extra_roots)
        latest_signature = self._build_roots_signature(latest_roots)
        if latest_signature != self._roots_signature:
            self._apply_allowed_roots(latest_roots)
            return
        if self._current_path and _is_media_path(self._current_path) and not os.path.isdir(self._current_path):
            self._apply_allowed_roots(latest_roots)

    def _resolve_start_path(self, requested_path: str) -> str:
        existing_dir = _first_existing_directory(requested_path)
        if existing_dir and self._root_for_path(existing_dir) is not None:
            return existing_dir
        if requested_path and _is_media_path(requested_path):
            for root in self._roots:
                if root.exists and _is_media_path(root.path):
                    return _normalize_dir(root.path)
        for root in self._roots:
            if root.exists:
                return _normalize_dir(root.path)
        return ""

    def _rebuild_root_buttons(self) -> None:
        while self.root_buttons_layout.count():
            item = self.root_buttons_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._root_buttons = []

        for root in self._roots:
            button = QToolButton(self.root_buttons_frame)
            button.setObjectName("browserRootButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            text = root.label
            if not root.exists:
                text += "\nUnavailable"
            button.setText(text)
            button.setIcon(self._folder_icon())
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setToolTip(root.description)
            button.setEnabled(root.exists)
            button.clicked.connect(lambda checked=False, target=root.path: self._set_current_path(target))
            self.root_buttons_layout.addWidget(button)
            self._root_buttons.append((root, button))

        self.root_buttons_layout.addStretch(1)

    def _root_for_path(self, path: str) -> Optional[BrowserRoot]:
        path = _normalize_dir(path)
        matches = [root for root in self._roots if root.exists and _path_within(root.path, path)]
        if not matches:
            return None
        return max(matches, key=lambda item: len(_normalize_dir(item.path)))

    def _set_current_path(self, path: str) -> None:
        if not path:
            return
        normalized = _normalize_dir(path)
        root = self._root_for_path(normalized)
        if root is None or not os.path.isdir(normalized):
            self.toast.warn("Browser", "Access is restricted to the configured save path and mounted media storage.")
            return

        self._current_path = normalized
        self.path_value_label.setText(self._display_location(normalized))
        for root_item, button in self._root_buttons:
            button.blockSignals(True)
            button.setChecked(_normalize_dir(root_item.path) == _normalize_dir(root.path))
            button.blockSignals(False)
        if self.mode == "save_file" and not self.filename_input.text().strip():
            basename = os.path.basename(self._suggested_path)
            if basename:
                self.filename_input.setText(basename)
        self._update_rule_text()
        self.refresh_entries()

    def _update_rule_text(self) -> None:
        if self.mode == "open_file" and self._allowed_patterns:
            patterns = ", ".join(self._allowed_patterns)
            self.rule_label.setText(f"Open mode is restricted to: {patterns}")
            return
        if self.mode == "save_file" and self._default_suffix:
            self.rule_label.setText(f"Save mode will use {self._default_suffix} when no matching extension is entered.")
            return
        self.rule_label.setText("You can navigate only inside the allowed locations listed above.")

    def refresh_entries(self) -> None:
        self._entries = []
        if not self._current_path or not os.path.isdir(self._current_path):
            if self._current_path:
                self.reload_allowed_roots()
                return
            self._rebuild_table()
            return

        try:
            with os.scandir(self._current_path) as iterator:
                for item in iterator:
                    if item.name in {".", ".."}:
                        continue
                    resolved_path = os.path.realpath(item.path)
                    if self._root_for_path(resolved_path) is None:
                        continue
                    is_dir = os.path.isdir(resolved_path)
                    if not is_dir and self.mode in {"open_file", "save_file"}:
                        if not _matches_patterns(item.name, self._allowed_patterns):
                            continue
                    try:
                        stat_result = os.stat(resolved_path)
                    except OSError:
                        continue
                    self._entries.append(
                        BrowserEntry(
                            name=item.name,
                            path=resolved_path,
                            is_dir=is_dir,
                            type_label=_entry_type_label(resolved_path, is_dir),
                            size_text="-" if is_dir else _format_bytes(stat_result.st_size),
                            modified_text=_format_modified(stat_result.st_mtime),
                        )
                    )
        except OSError as exc:
            self.toast.error("Browser", str(exc))

        self._entries.sort(key=lambda entry: (not entry.is_dir, entry.name.lower()))
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        filter_text = self.search_input.text().strip().lower()
        if filter_text:
            self._visible_entries = [
                entry for entry in self._entries if filter_text in entry.name.lower()
            ]
        else:
            self._visible_entries = list(self._entries)

        self.table.setRowCount(len(self._visible_entries))
        for row, entry in enumerate(self._visible_entries):
            name_item = QTableWidgetItem(entry.name)
            if entry.is_dir:
                name_item.setIcon(self._folder_icon())
            name_item.setToolTip(entry.name)
            type_item = QTableWidgetItem(entry.type_label)
            size_item = QTableWidgetItem(entry.size_text)
            modified_item = QTableWidgetItem(entry.modified_text)
            for item in (name_item, type_item, size_item, modified_item):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, type_item)
            self.table.setItem(row, 2, size_item)
            self.table.setItem(row, 3, modified_item)
        if self.table.rowCount() > 0:
            self.table.selectRow(0)
        location_text = self._display_location(self._current_path) if self._current_path else "No folder selected"
        self.status_label.setText(f"{len(self._visible_entries)} item(s) in {location_text}")
        self._on_selection_changed()

    def _selected_entry(self) -> Optional[BrowserEntry]:
        row = self.table.currentRow()
        if 0 <= row < len(self._visible_entries):
            return self._visible_entries[row]
        return None

    def _go_up(self) -> None:
        if not self._current_path:
            return
        parent = os.path.dirname(self._current_path)
        if not parent or parent == self._current_path:
            return
        if self._root_for_path(parent) is None:
            return
        self._set_current_path(parent)

    def _on_cell_activated(self, row: int, _column: int) -> None:
        if not (0 <= row < len(self._visible_entries)):
            return
        entry = self._visible_entries[row]
        if entry.is_dir:
            self._set_current_path(entry.path)
            return
        if self.mode == "browse":
            self._show_entry_details(entry)
            return
        if self.mode == "save_file":
            self.filename_input.setText(entry.name)
        resolved = self.resolve_selection()
        if resolved:
            self.accepted.emit(resolved)

    def _on_selection_changed(self) -> None:
        entry = self._selected_entry()
        self.details_button.setEnabled(entry is not None and not entry.is_dir)
        self.up_button.setEnabled(bool(self._current_path and self._root_for_path(self._current_path) is not None))
        self.selection_changed.emit()

    def _show_selected_details(self) -> None:
        entry = self._selected_entry()
        if entry is None or entry.is_dir:
            return
        self._show_entry_details(entry)

    def _show_entry_details(self, entry: BrowserEntry) -> None:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        summary = QLabel(
            "\n".join(
                (
                    f"Name: {entry.name}",
                    f"Path: {entry.path}",
                    f"Type: {entry.type_label}",
                    f"Size: {entry.size_text}",
                    f"Modified: {entry.modified_text}",
                )
            )
        )
        summary.setWordWrap(True)
        summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(summary)

        suffix = os.path.splitext(entry.path)[1].lower()
        if suffix in _IMAGE_SUFFIXES:
            pixmap = QPixmap(entry.path)
            if not pixmap.isNull():
                preview = QLabel()
                preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
                preview.setPixmap(
                    pixmap.scaled(
                        720,
                        420,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                preview.setStyleSheet("background: #0c1119; border: 1px solid #243042; border-radius: 12px;")
                layout.addWidget(preview)
        elif suffix in _TEXT_PREVIEW_SUFFIXES:
            preview_text = ""
            try:
                with open(entry.path, "r", encoding="utf-8", errors="replace") as handle:
                    preview_text = handle.read(24000)
            except OSError as exc:
                preview_text = str(exc)
            preview = QTextEdit()
            preview.setReadOnly(True)
            preview.setPlainText(preview_text)
            preview.setMinimumHeight(260)
            preview.setStyleSheet(
                "background: #0c1119; border: 1px solid #243042; border-radius: 12px; color: #e5edf8; padding: 10px;"
            )
            layout.addWidget(preview)

        dialog = PrimeDialog(
            title=entry.name,
            parent=self.window(),
            width=880,
            height=640,
            show_footer=False,
        )
        dialog.set_content(content, fill_height=True)
        dialog.exec()

    def resolve_selection(self) -> str:
        entry = self._selected_entry()
        if self.mode == "open_file":
            if entry is None or entry.is_dir:
                return ""
            return entry.path

        if self.mode == "save_file":
            filename = self.filename_input.text().strip()
            target_dir = self._current_path
            if entry is not None and entry.is_dir:
                target_dir = entry.path
            elif entry is not None and not filename:
                target_dir = os.path.dirname(entry.path)
                filename = os.path.basename(entry.path)
            filename = os.path.basename(filename)
            if not filename or not target_dir:
                return ""
            if self._default_suffix and not filename.lower().endswith(self._default_suffix.lower()):
                filename += self._default_suffix
            target_dir = _normalize_dir(target_dir)
            if self._root_for_path(target_dir) is None or not os.path.isdir(target_dir):
                return ""
            return os.path.join(target_dir, filename)

        if entry is not None:
            return entry.path
        return self._current_path

    def can_accept(self) -> bool:
        return bool(self.resolve_selection())


class RestrictedBrowserDialog(PrimeDialog):
    def __init__(
        self,
        title: str,
        mode: str,
        suggested_path: str = "",
        filters: str = "All Files (*)",
        extra_roots: Optional[Iterable[BrowserRoot]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        ok_text = "Choose" if mode == "open_file" else "Save" if mode == "save_file" else "Open"
        super().__init__(
            title=title,
            parent=parent,
            width=1140,
            height=760,
            ok_text=ok_text,
            cancel_text="Cancel",
        )
        self.selected_path = ""
        self.browser = RestrictedBrowserWidget(
            mode=mode,
            filters=filters,
            suggested_path=suggested_path,
            extra_roots=extra_roots,
            parent=self,
        )
        self.set_content(self.browser, fill_height=True)
        self.browser.selection_changed.connect(self._sync_actions)
        self.browser.accepted.connect(self._accept_from_browser)
        self._sync_actions()

    def _sync_actions(self) -> None:
        self.set_ok_enabled(self.browser.can_accept())

    def _accept_from_browser(self, path: str) -> None:
        self.selected_path = path
        super().accept()

    def accept(self) -> None:
        path = self.browser.resolve_selection()
        if not path:
            self.browser.toast.warn("Browser", "Select a valid file or folder first.")
            return
        self.selected_path = path
        super().accept()


def choose_restricted_open_file_path(
    parent: Optional[QWidget],
    title: str,
    start_path: str = "",
    filters: str = "All Files (*)",
    extra_roots: Optional[Iterable[BrowserRoot]] = None,
) -> str:
    dialog = RestrictedBrowserDialog(
        title=title,
        mode="open_file",
        suggested_path=start_path,
        filters=filters,
        extra_roots=extra_roots,
        parent=parent,
    )
    return dialog.selected_path if dialog.exec() else ""


def choose_restricted_save_file_path(
    parent: Optional[QWidget],
    title: str,
    suggested_path: str = "",
    filters: str = "All Files (*)",
) -> str:
    dialog = RestrictedBrowserDialog(
        title=title,
        mode="save_file",
        suggested_path=suggested_path,
        filters=filters,
        parent=parent,
    )
    return dialog.selected_path if dialog.exec() else ""
