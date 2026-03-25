from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from app.ui.select import PrimeSelect


RowData = Dict[str, Any]


@dataclass
class PrimeTableColumn:
    key: str
    header: str
    sortable: bool = True
    searchable: bool = True
    width: Optional[int] = None
    stretch: bool = False
    alignment: Qt.AlignmentFlag = Qt.AlignLeft | Qt.AlignVCenter
    formatter: Optional[Callable[[Any, RowData], str]] = None
    widget_factory: Optional[Callable[[RowData], QWidget]] = None


class PrimeDataTable(QWidget):
    row_clicked = Signal(dict)
    page_changed = Signal(int, int, int)

    def __init__(
        self,
        page_size: int = 10,
        page_size_options: Optional[List[int]] = None,
        row_height: int = 46,
        show_footer: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._columns: List[PrimeTableColumn] = []
        self._rows: List[RowData] = []
        self._filter_text = ""
        self._sort_key: Optional[str] = None
        self._sort_desc = False
        self._page_index = 0
        self._page_size_options = page_size_options or [10, 20, 50, 100]
        self._page_size = page_size if page_size in self._page_size_options else self._page_size_options[0]
        self._row_height = max(32, row_height)
        self._show_footer = show_footer

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self.table = QTableWidget(0, 0)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(False)
        self.table.cellClicked.connect(self._emit_clicked_row)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.setStyleSheet(
            """
            QTableWidget {
                background: #1e1f22;
                alternate-background-color: #212327;
                border: 1px solid #2d3036;
                border-radius: 12px;
                color: #f1f5f9;
                gridline-color: transparent;
            }
            QTableWidget::item {
                padding: 10px 8px;
                border-bottom: 1px solid #3a3d43;
            }
            QHeaderView::section {
                background: #1e1f22;
                color: #f8fafc;
                font-weight: 700;
                border: none;
                border-bottom: 1px solid #d7dbe3;
                padding: 10px 8px;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 6px 0;
            }
            QScrollBar::handle:vertical {
                background: #585d68;
                min-height: 26px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 10px;
                margin: 0 6px 6px 6px;
            }
            QScrollBar::handle:horizontal {
                background: #585d68;
                min-width: 26px;
                border-radius: 5px;
            }
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0;
            }
            """
        )
        root.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(8)

        self._meta_label = QLabel("0-0 of 0")
        self._meta_label.setStyleSheet("color:#b8bec9;")

        footer.addWidget(self._meta_label)
        footer.addStretch(1)

        self._size_label = QLabel("Rows")
        self._size_label.setStyleSheet("color:#b8bec9;")
        footer.addWidget(self._size_label)

        self._page_size_combo = PrimeSelect(
            options=[{"label": str(size), "value": size} for size in self._page_size_options],
            placeholder=str(self._page_size),
        )
        self._page_size_combo.setFixedWidth(86)
        self._page_size_combo.set_value(self._page_size)
        self._page_size_combo.value_changed.connect(self._on_page_size_changed)
        footer.addWidget(self._page_size_combo)

        self._prev_btn = QPushButton("Prev")
        self._next_btn = QPushButton("Next")
        for btn in (self._prev_btn, self._next_btn):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                """
                QPushButton {
                    background: #2a2d33;
                    color: #f1f5f9;
                    border: 1px solid #3a3f47;
                    border-radius: 8px;
                    padding: 5px 12px;
                    font-weight: 600;
                }
                QPushButton:hover:!disabled {
                    background: #2e69da;
                }
                QPushButton:disabled {
                    background: #1f2126;
                    color: #7d8592;
                    border: 1px solid #2b2e35;
                }
                """
            )
        self._prev_btn.clicked.connect(self._go_prev)
        self._next_btn.clicked.connect(self._go_next)
        footer.addWidget(self._prev_btn)
        footer.addWidget(self._next_btn)

        if self._show_footer:
            root.addLayout(footer)
        else:
            self._meta_label.hide()
            self._size_label.hide()
            self._page_size_combo.hide()
            self._prev_btn.hide()
            self._next_btn.hide()

    def set_columns(self, columns: List[PrimeTableColumn]) -> None:
        self._columns = columns
        self.table.setColumnCount(len(columns))
        self._apply_headers()
        self._apply_column_sizes()
        self._refresh()

    def set_rows(self, rows: List[RowData]) -> None:
        self._rows = rows
        self._clamp_page()
        self._refresh()

    def set_filter_text(self, text: str) -> None:
        normalized = (text or "").strip().lower()
        if self._filter_text == normalized:
            return
        self._filter_text = normalized
        self._page_index = 0
        self._refresh()

    def page_size(self) -> int:
        return self._page_size

    def current_page(self) -> int:
        return self._page_index + 1

    def page_count(self) -> int:
        total = len(self._sorted_rows(self._filtered_rows()))
        if self._page_size <= 0:
            return 1 if total else 0
        return max(1, ceil(total / self._page_size)) if total else 0

    def total_rows(self) -> int:
        return len(self._sorted_rows(self._filtered_rows()))

    def set_page_size(self, size: int) -> None:
        if size <= 0:
            return
        if self._page_size == size:
            return
        self._page_size = size
        self._page_size_combo.set_value(size)
        self._page_index = 0
        self._refresh()

    def set_page_number(self, page_number: int) -> None:
        page_count = self.page_count()
        if page_count <= 0:
            self._page_index = 0
            self._refresh()
            return
        normalized = min(max(1, int(page_number)), page_count)
        next_index = normalized - 1
        if next_index == self._page_index:
            return
        self._page_index = next_index
        self._refresh()

    def set_cell_widget_factory(self, column_key: str, factory: Callable[[RowData], QWidget]) -> None:
        for col in self._columns:
            if col.key == column_key:
                col.widget_factory = factory
                break
        self._refresh()

    def _emit_clicked_row(self, row: int, _column: int) -> None:
        page_rows = self._page_rows(self._sorted_rows(self._filtered_rows()))
        if row < 0 or row >= len(page_rows):
            return
        self.row_clicked.emit(page_rows[row])

    def _apply_headers(self) -> None:
        labels = []
        for col in self._columns:
            label = col.header
            if self._sort_key == col.key:
                label += " ▼" if self._sort_desc else " ▲"
            labels.append(label)
        self.table.setHorizontalHeaderLabels(labels)

    def _apply_column_sizes(self) -> None:
        header = self.table.horizontalHeader()
        for idx, col in enumerate(self._columns):
            if col.width is not None:
                header.setSectionResizeMode(idx, QHeaderView.ResizeMode.Fixed)
                self.table.setColumnWidth(idx, col.width)
            elif col.stretch:
                header.setSectionResizeMode(idx, QHeaderView.ResizeMode.Stretch)
            else:
                header.setSectionResizeMode(idx, QHeaderView.ResizeMode.ResizeToContents)

    def _on_header_clicked(self, index: int) -> None:
        if index < 0 or index >= len(self._columns):
            return
        col = self._columns[index]
        if not col.sortable:
            return
        if self._sort_key == col.key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key = col.key
            self._sort_desc = False
        self._page_index = 0
        self._refresh()

    def _on_page_size_changed(self, value: object = None) -> None:
        size = value if value is not None else self._page_size_combo.value()
        if not isinstance(size, int):
            return
        self._page_size = size
        self._page_index = 0
        self._refresh()

    def _go_prev(self) -> None:
        if self._page_index > 0:
            self._page_index -= 1
            self._refresh()

    def _go_next(self) -> None:
        total = len(self._sorted_rows(self._filtered_rows()))
        pages = max(1, ceil(total / self._page_size)) if self._page_size else 1
        if self._page_index + 1 < pages:
            self._page_index += 1
            self._refresh()

    def _filtered_rows(self) -> List[RowData]:
        if not self._filter_text:
            return list(self._rows)

        filtered: List[RowData] = []
        for row in self._rows:
            for col in self._columns:
                if not col.searchable:
                    continue
                raw_value = row.get(col.key, "")
                value = str(raw_value).lower()
                if self._filter_text in value:
                    filtered.append(row)
                    break
        return filtered

    def _sort_token(self, value: Any) -> Any:
        if value is None:
            return (3, "")
        if isinstance(value, bool):
            return (0, int(value))
        if isinstance(value, (int, float)):
            return (0, value)
        as_text = str(value).strip().lower()
        if not as_text:
            return (3, "")
        try:
            return (1, float(as_text))
        except ValueError:
            return (2, as_text)

    def _sorted_rows(self, rows: List[RowData]) -> List[RowData]:
        if not self._sort_key:
            return rows
        return sorted(
            rows,
            key=lambda row: self._sort_token(row.get(self._sort_key)),
            reverse=self._sort_desc,
        )

    def _page_rows(self, rows: List[RowData]) -> List[RowData]:
        if self._page_size <= 0:
            return rows
        start = self._page_index * self._page_size
        end = start + self._page_size
        return rows[start:end]

    def _clamp_page(self) -> None:
        total = len(self._sorted_rows(self._filtered_rows()))
        if self._page_size <= 0:
            self._page_index = 0
            return
        max_page = max(0, ceil(total / self._page_size) - 1)
        self._page_index = min(self._page_index, max_page)

    def _refresh(self) -> None:
        self._apply_headers()
        self._apply_column_sizes()

        rows = self._sorted_rows(self._filtered_rows())
        self._clamp_page()
        page_rows = self._page_rows(rows)

        self.table.clearSpans()
        self._clear_cells()

        if not self._columns:
            self.table.setRowCount(0)
            self._update_pagination(total=0, shown=0)
            return

        if not page_rows:
            self.table.setRowCount(1)
            for col in range(len(self._columns)):
                self.table.setItem(0, col, QTableWidgetItem(""))
            empty = QTableWidgetItem("No data found")
            empty.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
            self.table.setItem(0, 0, empty)
            if len(self._columns) > 1:
                self.table.setSpan(0, 0, 1, len(self._columns))
            self.table.setRowHeight(0, max(self._row_height, 56))
            self._update_pagination(total=len(rows), shown=0)
            return

        self.table.setRowCount(len(page_rows))
        for r, row in enumerate(page_rows):
            for c, col in enumerate(self._columns):
                if col.widget_factory:
                    widget = col.widget_factory(row)
                    if col.width is not None:
                        widget.setMaximumWidth(max(20, col.width - 8))
                    self.table.setCellWidget(r, c, self._wrap_cell_widget(widget, col.alignment))
                    continue

                value = row.get(col.key, "")
                raw_text = col.formatter(value, row) if col.formatter else str(value)
                text = self._elide_text(raw_text, c)
                item = QTableWidgetItem(text)
                if text != raw_text:
                    item.setToolTip(raw_text)
                item.setTextAlignment(int(col.alignment))
                self.table.setItem(r, c, item)
            self.table.setRowHeight(r, self._row_height)

        self._update_pagination(total=len(rows), shown=len(page_rows))

    def _update_pagination(self, total: int, shown: int) -> None:
        if total == 0 or shown == 0:
            start = 0
            end = 0
        else:
            start = self._page_index * self._page_size + 1
            end = start + shown - 1
        self._meta_label.setText(f"{start}-{end} of {total}")

        if self._page_size <= 0:
            pages = 1
        else:
            pages = max(1, ceil(total / self._page_size))
        self._prev_btn.setEnabled(self._page_index > 0)
        self._next_btn.setEnabled((self._page_index + 1) < pages)
        self.page_changed.emit(self._page_index + 1, pages if total else 0, total)

    def _wrap_cell_widget(self, widget: QWidget, alignment: Qt.AlignmentFlag) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(0)
        layout.addWidget(widget)
        layout.setAlignment(widget, self._widget_alignment(alignment))
        return wrapper

    def _widget_alignment(self, alignment: Qt.AlignmentFlag) -> Qt.AlignmentFlag:
        horizontal = alignment & (
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignHCenter
            | Qt.AlignmentFlag.AlignJustify
        )
        vertical = alignment & (
            Qt.AlignmentFlag.AlignTop
            | Qt.AlignmentFlag.AlignBottom
            | Qt.AlignmentFlag.AlignVCenter
        )
        if not horizontal:
            horizontal = Qt.AlignmentFlag.AlignLeft
        if not vertical:
            vertical = Qt.AlignmentFlag.AlignVCenter
        return horizontal | vertical

    def _elide_text(self, text: str, column_index: int) -> str:
        width = self.table.columnWidth(column_index) - 20
        if width <= 0:
            return text
        return self.table.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, width)

    def _clear_cells(self) -> None:
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                widget = self.table.cellWidget(row, col)
                if widget is not None:
                    self.table.removeCellWidget(row, col)
                    widget.deleteLater()
                self.table.takeItem(row, col)
