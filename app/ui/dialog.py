import os
import sys
from typing import Optional

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

if __package__ in (None, ""):
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from app.ui.button import PrimeButton

_ICONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../resources/icons"))


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


class _DialogHeader(QWidget):
    drag_started = Signal(QPoint)
    drag_moved = Signal(QPoint)
    drag_finished = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._dragging = False
        self.drag_enabled = True

    def mousePressEvent(self, event) -> None:
        if not self.drag_enabled:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self.setCursor(Qt.ClosedHandCursor)
            self.drag_started.emit(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not self.drag_enabled:
            super().mouseMoveEvent(event)
            return
        if self._dragging:
            self.drag_moved.emit(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if not self.drag_enabled:
            super().mouseReleaseEvent(event)
            return
        if self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            self.setCursor(Qt.OpenHandCursor)
            self.drag_finished.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class PrimeDialog(QDialog):
    def __init__(
        self,
        title: str = "Dialog",
        content: Optional[QWidget] = None,
        parent: Optional[QWidget] = None,
        modal: bool = True,
        width: int = 720,
        height: int = 380,
        show_footer: bool = True,
        ok_text: str = "OK",
        cancel_text: str = "Cancel",
        closable: bool = True,
        dismissable_mask: bool = True,
        draggable: bool = True,
    ) -> None:
        super().__init__(parent)

        self._preferred_width = max(360, width)
        self._preferred_height = max(220, height)
        self._side_margin = 28
        self._top_margin = 28
        self._mask_color = QColor(3, 7, 18, 172)
        self._dismissable_mask = dismissable_mask
        self._draggable = draggable
        self._custom_position = False
        self._drag_offset = QPoint()
        self._drag_handlers_connected = False

        self.setWindowTitle(title)
        self.setModal(modal)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setWindowModality(Qt.WindowModal if modal and parent else Qt.ApplicationModal if modal else Qt.NonModal)

        self._shell = QWidget(self)
        self._shell.setObjectName("dialogShell")
        self._shell.setAutoFillBackground(True)

        shadow = QGraphicsDropShadowEffect(self._shell)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 14)
        shadow.setColor(QColor(0, 0, 0, 150))
        self._shell.setGraphicsEffect(shadow)

        shell_layout = QVBoxLayout(self._shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        self.header_widget = _DialogHeader(self._shell)
        self.header_widget.setObjectName("dialogHeader")
        self.header_widget.setFixedHeight(68)

        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(24, 0, 18, 0)
        header_layout.setSpacing(12)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("dialogTitle")

        self.close_button = QToolButton(self.header_widget)
        self.close_button.setObjectName("dialogCloseButton")
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.setFixedSize(34, 34)
        self.close_button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        close_icon = _icon_path("close.svg")
        if os.path.exists(close_icon):
            self.close_button.setIcon(QIcon(close_icon))
            self.close_button.setIconSize(QSize(16, 16))
        else:
            self.close_button.setText("x")
        self.close_button.clicked.connect(self.reject)

        header_layout.addWidget(self.title_label, 1)
        header_layout.addWidget(self.close_button)
        shell_layout.addWidget(self.header_widget)

        self.body_widget = QWidget(self._shell)
        self.body_widget.setObjectName("dialogBody")
        body_layout = QVBoxLayout(self.body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.content_scroll = QScrollArea(self.body_widget)
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content_scroll.setStyleSheet("background: transparent; border: none;")

        self.content_container = QWidget()
        self.content_container.setObjectName("dialogContent")
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(24, 22, 24, 22)
        self.content_layout.setSpacing(14)
        self.content_layout.addStretch(1)

        self.content_scroll.setWidget(self.content_container)
        body_layout.addWidget(self.content_scroll)
        shell_layout.addWidget(self.body_widget, 1)

        self.footer_widget = QWidget(self._shell)
        self.footer_widget.setObjectName("dialogFooter")

        footer_layout = QHBoxLayout(self.footer_widget)
        footer_layout.setContentsMargins(24, 16, 24, 16)
        footer_layout.setSpacing(10)
        footer_layout.addStretch(1)

        self.cancel_button = PrimeButton(cancel_text, variant="light", mode="outline", size="sm",width=80)
        self.ok_button = PrimeButton(ok_text, variant="primary", mode="filled", size="sm",width=80)
        self.cancel_button.clicked.connect(self.reject)
        self.ok_button.clicked.connect(self.accept)

        footer_layout.addWidget(self.cancel_button)
        footer_layout.addWidget(self.ok_button)
        shell_layout.addWidget(self.footer_widget)

        self.setStyleSheet(
            """
            QDialog {
                background: transparent;
            }
            #dialogShell {
                background: #10131a;
                border: 1px solid #263041;
                border-radius: 18px;
            }
            #dialogHeader {
                background: transparent;
                border-bottom: 1px solid rgba(148, 163, 184, 0.18);
            }
            QLabel#dialogTitle {
                color: #f8fafc;
                font-size: 19px;
                font-weight: 700;
                letter-spacing: 0.2px;
            }
            #dialogBody {
                background: transparent;
            }
            #dialogContent {
                background: transparent;
            }
            #dialogContent QLabel {
                color: #dbe4f0;
            }
            #dialogFooter {
                background: rgba(15, 23, 42, 0.82);
                border-top: 1px solid rgba(148, 163, 184, 0.14);
                border-bottom-left-radius: 18px;
                border-bottom-right-radius: 18px;
            }
            #dialogCloseButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 17px;
                padding: 0;
            }
            #dialogCloseButton:hover {
                background: rgba(148, 163, 184, 0.12);
                border-color: rgba(148, 163, 184, 0.18);
            }
            #dialogCloseButton:pressed {
                background: rgba(148, 163, 184, 0.2);
            }
            QScrollArea {
                background: transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 8px 6px 8px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(148, 163, 184, 0.48);
                min-height: 32px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
            """
        )

        self.set_closable(closable)
        self.set_footer_visible(show_footer)
        self._set_draggable(draggable)

        if content is not None:
            self.set_content(content)

        self._resize_to_target()

    def set_content(self, widget: QWidget, fill_height: bool = False) -> None:
        self.clear_content()
        stretch = 1 if fill_height else 0
        self.content_layout.insertWidget(0, widget, stretch)
        # Collapse or restore the trailing spacer to match fill_height intent
        spacer_idx = self.content_layout.count() - 1
        self.content_layout.setStretch(spacer_idx, 0 if fill_height else 1)

    def clear_content(self) -> None:
        while self.content_layout.count() > 1:
            item = self.content_layout.takeAt(0)
            child = item.widget()
            if child is not None:
                child.setParent(None)

    def set_footer_visible(self, visible: bool) -> None:
        self.footer_widget.setVisible(visible)

    def set_header_visible(self, visible: bool) -> None:
        self.header_widget.setVisible(visible)

    def set_ok_text(self, text: str) -> None:
        self.ok_button.setText(text)

    def set_cancel_text(self, text: str) -> None:
        self.cancel_button.setText(text)

    def set_title(self, title: str) -> None:
        self.setWindowTitle(title)
        self.title_label.setText(title)

    def set_ok_enabled(self, enabled: bool) -> None:
        self.ok_button.setEnabled(enabled)

    def set_cancel_enabled(self, enabled: bool) -> None:
        self.cancel_button.setEnabled(enabled)

    def set_closable(self, closable: bool) -> None:
        self.close_button.setVisible(closable)
        self.close_button.setEnabled(closable)

    def set_dismissable_mask(self, enabled: bool) -> None:
        self._dismissable_mask = enabled

    def set_draggable(self, enabled: bool) -> None:
        self._set_draggable(enabled)

    def set_dialog_size(self, width: int, height: int) -> None:
        self._preferred_width = max(360, width)
        self._preferred_height = max(220, height)
        self._custom_position = False
        self._resize_to_target()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), self._mask_color)
        super().paintEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._resize_to_target()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_shell(center=not self._custom_position)

    def mousePressEvent(self, event) -> None:
        if not self._shell.geometry().contains(event.position().toPoint()) and self._dismissable_mask:
            self.reject()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape and self.close_button.isVisible():
            self.reject()
            event.accept()
            return
        super().keyPressEvent(event)

    def _set_draggable(self, enabled: bool) -> None:
        self._draggable = enabled
        self.header_widget.drag_enabled = enabled

        if not self._drag_handlers_connected:
            self.header_widget.drag_started.connect(self._begin_drag)
            self.header_widget.drag_moved.connect(self._move_shell)
            self.header_widget.drag_finished.connect(self._finish_drag)
            self._drag_handlers_connected = True

        if enabled:
            self.header_widget.setCursor(Qt.OpenHandCursor)
        else:
            self.header_widget.setCursor(Qt.ArrowCursor)

    def _begin_drag(self, global_pos: QPoint) -> None:
        if not self._draggable:
            return
        self._drag_offset = global_pos - self.mapToGlobal(self._shell.pos())

    def _move_shell(self, global_pos: QPoint) -> None:
        if not self._draggable:
            return
        next_top_left = self.mapFromGlobal(global_pos - self._drag_offset)
        bounded = self._bounded_shell_pos(next_top_left)
        self._shell.move(bounded)
        self._custom_position = True

    def _finish_drag(self) -> None:
        if self._draggable:
            self._custom_position = True

    def _resize_to_target(self) -> None:
        overlay = self._overlay_geometry()
        self.setGeometry(overlay)

        shell_width = min(self._preferred_width, max(320, self.width() - (self._side_margin * 2)))
        shell_height = min(self._preferred_height, max(220, self.height() - (self._top_margin * 2)))
        self._shell.resize(shell_width, shell_height)
        self._position_shell(center=not self._custom_position)

    def _position_shell(self, center: bool = True) -> None:
        if self._shell.width() <= 0 or self._shell.height() <= 0:
            return
        if center:
            x = (self.width() - self._shell.width()) // 2
            y = (self.height() - self._shell.height()) // 2
            self._shell.move(max(self._side_margin, x), max(self._top_margin, y))
            return
        self._shell.move(self._bounded_shell_pos(self._shell.pos()))

    def _bounded_shell_pos(self, pos: QPoint) -> QPoint:
        max_x = max(self._side_margin, self.width() - self._shell.width() - self._side_margin)
        max_y = max(self._top_margin, self.height() - self._shell.height() - self._top_margin)
        return QPoint(
            min(max(self._side_margin, pos.x()), max_x),
            min(max(self._top_margin, pos.y()), max_y),
        )

    def _overlay_geometry(self):
        parent_window = self.parentWidget().window() if self.parentWidget() is not None else None
        if parent_window is not None and parent_window.isVisible():
            top_left = parent_window.mapToGlobal(parent_window.rect().topLeft())
            return parent_window.rect().translated(top_left)

        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is not None:
            return screen.availableGeometry()
        return self.geometry()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    preview_content = QWidget()
    preview_layout = QVBoxLayout(preview_content)
    preview_layout.setContentsMargins(0, 0, 0, 0)
    preview_layout.setSpacing(12)

    title = QLabel("Prime Dialog Preview")
    title.setStyleSheet("color: #f8fafc; font-size: 15px; font-weight: 700;")
    preview_layout.addWidget(title)

    body = QLabel("This is a standalone preview for PrimeDialog.")
    body.setWordWrap(True)
    body.setStyleSheet("color: #cbd5e1; font-size: 13px;")
    preview_layout.addWidget(body)

    dialog = PrimeDialog(
        title="Add Camera",
        content=preview_content,
        width=1200,
        height=800,
        ok_text="Save",
        cancel_text="Close",
    )
    dialog.exec()


    
