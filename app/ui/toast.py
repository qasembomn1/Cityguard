from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class PrimeToast(QFrame):
    closed = Signal(QWidget)

    _TONE = {
        "success": {
            "accent": "#22c55e",
            "bg": "rgba(6, 18, 12, 0.96)",
            "border": "rgba(34, 197, 94, 0.38)",
            "title": "#dcfce7",
            "detail": "#86efac",
            "icon": "✓",
        },
        "info": {
            "accent": "#3b82f6",
            "bg": "rgba(8, 15, 28, 0.96)",
            "border": "rgba(59, 130, 246, 0.38)",
            "title": "#dbeafe",
            "detail": "#93c5fd",
            "icon": "i",
        },
        "warn": {
            "accent": "#f59e0b",
            "bg": "rgba(24, 16, 5, 0.96)",
            "border": "rgba(245, 158, 11, 0.38)",
            "title": "#fef3c7",
            "detail": "#fcd34d",
            "icon": "!",
        },
        "error": {
            "accent": "#ef4444",
            "bg": "rgba(28, 10, 10, 0.96)",
            "border": "rgba(239, 68, 68, 0.38)",
            "title": "#fee2e2",
            "detail": "#fca5a5",
            "icon": "!",
        },
    }

    def __init__(
        self,
        severity: str,
        summary: str,
        detail: str = "",
        life: int = 3200,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        tone = self._TONE.get(severity, self._TONE["info"])
        self.setObjectName("primeToast")
        self.setMinimumWidth(320)
        self.setMaximumWidth(420)
        self.setStyleSheet(
            f"""
            QFrame#primeToast {{
                background: {tone['bg']};
                border: 1px solid {tone['border']};
                border-left: 4px solid {tone['accent']};
                border-radius: 12px;
            }}
            QLabel#toastIcon {{
                color: {tone['title']};
                font-size: 15px;
                font-weight: 800;
                background: transparent;
            }}
            QLabel#toastSummary {{
                color: {tone['title']};
                font-size: 13px;
                font-weight: 700;
                background: transparent;
            }}
            QLabel#toastDetail {{
                color: {tone['detail']};
                font-size: 12px;
                background: transparent;
            }}
            QToolButton#toastClose {{
                background: transparent;
                border: none;
                color: {tone['detail']};
                font-size: 14px;
                font-weight: 700;
                padding: 0;
            }}
            QToolButton#toastClose:hover {{
                color: {tone['title']};
            }}
            """
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        icon = QLabel(tone["icon"])
        icon.setObjectName("toastIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        icon.setFixedWidth(14)
        root.addWidget(icon)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        summary_lbl = QLabel(summary)
        summary_lbl.setObjectName("toastSummary")
        summary_lbl.setWordWrap(True)
        text_col.addWidget(summary_lbl)

        if detail:
            detail_lbl = QLabel(detail)
            detail_lbl.setObjectName("toastDetail")
            detail_lbl.setWordWrap(True)
            text_col.addWidget(detail_lbl)

        root.addLayout(text_col, 1)

        close_btn = QToolButton()
        close_btn.setObjectName("toastClose")
        close_btn.setText("×")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.close_toast)
        root.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignTop)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.close_toast)
        self._timer.start(max(1000, life))

    def close_toast(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
        self.closed.emit(self)


class PrimeToastHost(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedWidth(420)
        self._owner = parent

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self._layout = layout

        if parent is not None:
            parent.installEventFilter(self)
        self.hide()

    def show_message(
        self,
        severity: str,
        summary: str,
        detail: str = "",
        life: int = 3200,
    ) -> None:
        toast = PrimeToast(severity=severity, summary=summary, detail=detail, life=life, parent=self)
        toast.closed.connect(self._remove_toast)
        self._layout.addWidget(toast)
        self._sync_position()
        self.show()
        self.raise_()

    def success(self, summary: str, detail: str = "", life: int = 3200) -> None:
        self.show_message("success", summary, detail, life)

    def info(self, summary: str, detail: str = "", life: int = 3200) -> None:
        self.show_message("info", summary, detail, life)

    def warn(self, summary: str, detail: str = "", life: int = 3200) -> None:
        self.show_message("warn", summary, detail, life)

    def error(self, summary: str, detail: str = "", life: int = 4200) -> None:
        self.show_message("error", summary, detail, life)

    def eventFilter(self, watched: QObject, event: QEvent):  # type: ignore[name-defined]
        if watched is self.parent() and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.Show,
            QEvent.Type.Hide,
        ):
            if self.parentWidget() is not None and self.parentWidget().isVisible():
                self._sync_position()
                if self._layout.count() > 0:
                    self.show()
                    self.raise_()
            else:
                self.hide()
        return super().eventFilter(watched, event)

    def _remove_toast(self, toast: QWidget) -> None:
        self._layout.removeWidget(toast)
        toast.deleteLater()
        if self._layout.count() == 0:
            self.hide()
        else:
            self._sync_position()

    def _sync_position(self) -> None:
        owner = self._owner or self.parentWidget()
        if owner is None:
            return
        self.adjustSize()
        self.resize(self.width(), self.sizeHint().height())
        margin = 18
        top_left = owner.mapToGlobal(QPoint(0, 0))
        x = top_left.x() + max(0, owner.width() - self.width() - margin)
        y = top_left.y() + margin
        self.move(x, y)
        self.raise_()
