"""
AppHeader — PySide6 implementation of the Vue header component.

Left  : Logo · "City Guard" · scrollable tab-bar · ⊕ (tiered QMenu)
Right : Monitor · Live View · Faces · 🔔(badge) · Search · Profile
"""

import os

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QScrollArea,
    QSizePolicy, QApplication, QDialog, QMenu, QToolButton, QFrame,
)
from PySide6.QtCore import Qt, Signal, QRectF, QRect, QTimer
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QCursor, QFont, QPen,
)
from app.constants._init_ import Constants
from app.widgets.svg_widget import SvgWidget

BASE_DIR  = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOGO_PATH = os.path.join(BASE_DIR, "resources", "Logo.svg")
HOME_ICON = os.path.join(BASE_DIR, "resources", "icons", "home.svg")
ICONS_DIR = os.path.join(BASE_DIR, "resources", "icons")


def _resolve_svg_path(svg_path: str) -> str:
    if not svg_path:
        return ""
    candidates = [svg_path]
    if not os.path.isabs(svg_path):
        candidates.append(os.path.abspath(svg_path))
        candidates.append(os.path.abspath(os.path.join(BASE_DIR, svg_path)))
        candidates.append(os.path.abspath(os.path.join(BASE_DIR, svg_path.lstrip("/"))))
    basename = os.path.basename(svg_path)
    if basename:
        candidates.append(os.path.join(ICONS_DIR, basename))
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return ""

# ── Palette ───────────────────────────────────────────────────────────────────
_BG     = Constants.SIDEBAR_BG   # "#13161b"
_DARK   = Constants.DARK_BG      # "#0d0f12"
_TEXT   = Constants.TEXT_MAIN    # "#c8cdd8"
_DIM    = Constants.TEXT_DIM     # "#5a6070"
_ACCENT = Constants.ACCENT       # "#e53935"
_BORDER = Constants.BORDER       # "#1e2229"
_H      = 52                     # header height px

_MENU_QSS = f"""
    QMenu {{
        background: {_BG};
        border: 1px solid {_BORDER};
        color: {_TEXT};
        border-radius: 8px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 20px 6px 12px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{ background: {_BORDER}; color: white; }}
    QMenu::separator {{ height: 1px; background: {_BORDER}; margin: 4px 0; }}
    QMenu::icon {{ padding-left: 6px; }}
"""


# ── Close × label ─────────────────────────────────────────────────────────────
class _CloseLabel(QLabel):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__("✕", parent)
        self.setFixedSize(20, 20)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._style(False)

    def _style(self, hov: bool):
        self.setStyleSheet(
            f"color:{'#ef4444' if hov else _DIM};"
            
            "font-size:16px;background:transparent;border:none;"
        )

    def enterEvent(self, e):  self._style(True);  super().enterEvent(e)
    def leaveEvent(self, e):  self._style(False); super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            e.accept()
            return
        super().mousePressEvent(e)


# ── Single tab button ─────────────────────────────────────────────────────────
class TabButton(QWidget):
    """
    Rounded-top tab.  Active → 2 px accent border at bottom.
    Vue: .rounded-t-xl .bg-black .border-b-2 .dark:border-primary
    """
    clicked   = Signal(str)
    close_req = Signal(str)

    _R = 12   # corner radius (rounded-t-xl ≈ 12 px)

    def __init__(
        self,
        name: str,
        path: str,
        icon: str = "",
        svg_icon: str = "",
        home: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.path    = path
        self._active = False
        self._hover  = False

        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(_H - 6)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._name_text = name
        self._min_width = 148 if home else 132
        self._preferred_width = self._min_width

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 8, 0)
        row.setSpacing(6)
        required_width = row.contentsMargins().left() + row.contentsMargins().right()
        widget_count = 0

        svg_path = _resolve_svg_path(svg_icon)

        if svg_path and os.path.exists(svg_path):
            i_svg = SvgWidget(svg_path)
            i_svg.setFixedSize(16, 16)
            i_svg.setStyleSheet("background:transparent;border:none;")
            i_svg.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row.addWidget(i_svg, alignment=Qt.AlignmentFlag.AlignVCenter)
            required_width += i_svg.width()
            widget_count += 1

        self._nl = QLabel(name)
        f = QFont()
        f.setPointSize(9)
        f.setWeight(QFont.Weight.Medium)
        self._nl.setFont(f)
        self._nl.setStyleSheet(f"color:{_TEXT};background:transparent;border:none;")
        self._nl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._nl.setMinimumWidth(self._nl.sizeHint().width())
        row.addWidget(self._nl)
        required_width += self._nl.sizeHint().width()
        widget_count += 1

        if not home:
            self._xbtn = _CloseLabel()
            self._xbtn.clicked.connect(lambda: self.close_req.emit(self.path))
            row.addWidget(self._xbtn)
            required_width += self._xbtn.width()
            widget_count += 1

        if widget_count > 1:
            required_width += row.spacing() * (widget_count - 1)

        # Leave a small buffer so Qt text metrics do not clip the final glyph.
        self._preferred_width = max(self._min_width, required_width + 6)
        self.set_tab_width(self._preferred_width)

    def preferred_width(self) -> int:
        return self._preferred_width

    def min_tab_width(self) -> int:
        return self._min_width

    def set_tab_width(self, width: int):
        width = max(self._min_width, int(width))
        self.setFixedWidth(width)
        self._nl.setText(self._name_text)
        self._nl.setToolTip("")

    def set_active(self, v: bool):
        self._active = v
        self._nl.setStyleSheet(
            f"color:{'#ffffff' if v else _TEXT};background:transparent;border:none;"
        )
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        r = self._R

        # Rounded-top path (no bottom rounding)
        path = QPainterPath()
        path.moveTo(0, h)
        path.lineTo(0, r)
        path.arcTo(QRectF(0, 0, r * 2, r * 2), 180, -90)
        path.lineTo(w - r, 0)
        path.arcTo(QRectF(w - r * 2, 0, r * 2, r * 2), 90, -90)
        path.lineTo(w, h)
        path.closeSubpath()

        fill = QColor(_DARK).lighter(115) if self._hover else QColor(_DARK)
        p.setPen(Qt.PenStyle.NoPen)
        p.fillPath(path, fill)

        # Active bottom border (2 px accent)
        if self._active:
            p.setPen(QPen(QColor(_ACCENT), 2))
            p.drawLine(1, h - 1, w - 1, h - 1)

        super().paintEvent(e)

    def enterEvent(self, e):  self._hover = True;  self.update(); super().enterEvent(e)
    def leaveEvent(self, e):  self._hover = False; self.update(); super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.path)
        super().mousePressEvent(e)


# ── Scrollable tab bar ────────────────────────────────────────────────────────
class TabBar(QWidget):
    navigate = Signal(str)

    _GROUPED_PATHS = {
        "/user/profile": {
            "/user/profile",
            "/user/users",
            "/user/roles",
            "/user/department",
        },
        "/device/clients": {
            "/device/clients",
            "/device/cameras",
            "/device/gps",
            "/device/access-control",
            "/device/body-cam",
        },
        "/log/user": {
            "/log/user",
            "/log/client",
            "/log/camera",
        },
        "/lpr/blacklist": {
            "/lpr/blacklist",
            "/lpr/whitelist",
            "/face/blacklist",
            "/face/whitelist",
        },
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._tabs: dict[str, TabButton] = {}
        self._current = "/"
        self._history: list[str] = []
        self._relayout_scheduled = False

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        # Scrollable tab container (thin scrollbar, hidden by default)
        self._scroll = QScrollArea()
        self._scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFixedHeight(_H - 2)
        self._scroll.setStyleSheet(f"""
            QScrollArea  {{ background:transparent; border:none; }}
            QScrollBar:horizontal {{
                background:transparent; height:3px; margin:0;
            }}
            QScrollBar::handle:horizontal {{
                background:rgba(255,255,255,40);
                border-radius:1px; min-width:20px;
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{ width:0; }}
        """)

        self._inner = QWidget()
        self._inner.setStyleSheet("background:transparent;")
        self._row = QHBoxLayout(self._inner)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(2)
        self._row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

        self._scroll.setWidget(self._inner)
        root.addWidget(self._scroll, 1)

        # Home tab — always first, not closeable
        self._make_tab("Control Panel", "/", "⊞", svg_icon=HOME_ICON, home=True)

        self._set_active("/")
        self._schedule_relayout()


    def add_tab(self, name: str, path: str, icon: str = "", svg_icon: str = ""):
        tab_path = self._normalize_path(path)
        if tab_path in self._tabs:
            self._set_active(path)
            self._schedule_relayout()
            return
        self._make_tab(name, tab_path, icon, svg_icon)
        self._set_active(path)
        self._schedule_relayout()

    def remove_tab(self, path: str):
        tab_path = self._normalize_path(path)
        if tab_path not in self._tabs or tab_path == "/":
            return
        was_active = self._normalize_path(self._current) == tab_path
        tab = self._tabs.pop(tab_path)
        self._row.removeWidget(tab)
        tab.setParent(None)
        tab.deleteLater()
        self._history = [p for p in self._history if p != tab_path and p != "/" and p in self._tabs]

        # If the closed tab was active, return to last active tab, else home
        if was_active:
            target = self._history[-1] if self._history else "/"
            if target not in self._tabs:
                target = "/"
            self._set_active(target)
            self.navigate.emit(target)
        self._schedule_relayout()

    def set_current(self, path: str):
        self._set_active(path)
        self._schedule_relayout()

    def has_tab(self, path: str) -> bool:
        return self._normalize_path(path) in self._tabs

    # ── Private ───────────────────────────────────────────────────────────────
    def _make_tab(self, name, path, icon="", svg_icon="", home=False):
        tab = TabButton(name, path, icon, svg_icon=svg_icon, home=home)
        tab.clicked.connect(self._on_tab_clicked)
        tab.close_req.connect(self.remove_tab)
        if home or path == "/":
            insert_index = 0
        else:
            # Dynamic tabs stay in opening order to the right of the static home tab.
            insert_index = self._row.count()
        self._row.insertWidget(min(insert_index, self._row.count()), tab)
        self._inner.adjustSize()
        self._tabs[path] = tab
        return tab

    def _set_active(self, path: str):
        self._current = path
        tab_path = self._normalize_path(path)
        if tab_path != "/" and tab_path in self._tabs:
            self._history = [p for p in self._history if p != tab_path]
            self._history.append(tab_path)
        for p, tab in self._tabs.items():
            tab.set_active(p == tab_path)

    def _normalize_path(self, path: str) -> str:
        for canonical_path, grouped_paths in self._GROUPED_PATHS.items():
            if path in grouped_paths:
                return canonical_path
        return path

    def _on_tab_clicked(self, path: str):
        self._set_active(path)
        self.navigate.emit(path)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_relayout()

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_relayout()

    def _schedule_relayout(self):
        if self._relayout_scheduled:
            return
        self._relayout_scheduled = True
        QTimer.singleShot(0, self._relayout_tabs)

    def _dynamic_tabs_in_row_order(self) -> list[TabButton]:
        tabs: list[TabButton] = []
        for i in range(self._row.count()):
            item = self._row.itemAt(i)
            widget = item.widget() if item is not None else None
            if isinstance(widget, TabButton) and widget.path != "/":
                tabs.append(widget)
        return tabs

    def _available_tab_width(self) -> int:
        viewport_w = self._scroll.viewport().width()
        if viewport_w > 0:
            return viewport_w
        return max(0, self.width() - self.layout().spacing())

    def _ensure_active_tab_visible(self):
        tab = self._tabs.get(self._normalize_path(self._current))
        if tab is None:
            return
        bar = self._scroll.horizontalScrollBar()
        viewport_w = self._scroll.viewport().width()
        if viewport_w <= 0:
            return
        left = tab.x()
        right = left + tab.width()
        view_left = bar.value()
        view_right = view_left + viewport_w
        if left < view_left:
            bar.setValue(left)
        elif right > view_right:
            bar.setValue(max(0, right - viewport_w))

    def _relayout_tabs(self):
        self._relayout_scheduled = False
        tabs = self._dynamic_tabs_in_row_order()
        home_tab = self._tabs.get("/")
        ordered_tabs = ([home_tab] if home_tab is not None else []) + tabs

        for tab in ordered_tabs:
            tab.set_tab_width(tab.preferred_width())

        margins = self._row.contentsMargins()
        total_width = margins.left() + margins.right()
        if ordered_tabs:
            total_width += sum(tab.width() for tab in ordered_tabs)
            total_width += self._row.spacing() * (len(ordered_tabs) - 1)
        total_height = max((tab.height() for tab in ordered_tabs), default=0)

        self._inner.setMinimumSize(total_width, total_height)
        self._inner.resize(total_width, total_height)
        self._ensure_active_tab_visible()


# ── Icon button (rounded-top, contrast style) ──────────────────────────────────
class IconBtn(QToolButton):
    """
    Header action button.
    """
    _R = 12

    def __init__(self, glyph: str = "", size: int = 40, svg_icon: str = "", parent=None):
        super().__init__(parent)
        self._glyph = glyph
        self._svg = None
        self._hover = False
        self.setFixedSize(size, size)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet("background:transparent;border:none;")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        svg_path = _resolve_svg_path(svg_icon)
        if svg_path and os.path.exists(svg_path):
            self._svg = SvgWidget(svg_path, self)
            self._svg.setFixedSize(16, 16)
            self._svg.setStyleSheet("background:transparent;border:none;")
            self._svg.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._position_icon()

    def _position_icon(self):
        if self._svg is None:
            return
        x = (self.width() - self._svg.width()) // 2
        y = (self.height() - self._svg.height()) // 2
        self._svg.move(x, y)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)
        fill = QColor(35, 40, 48) if self._hover else QColor(22, 26, 32)
        border = QColor(57, 66, 79) if self._hover else QColor(39, 45, 55)
        p.setPen(QPen(border, 1))
        p.setBrush(fill)
        p.drawRoundedRect(rect, self._R, self._R)

        if self._svg is None:
            p.setPen(QPen(QColor(_TEXT)))
            p.setFont(QFont("Segoe UI Emoji", 14))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._glyph)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._position_icon()

    def enterEvent(self, e):  self._hover = True;  self.update(); super().enterEvent(e)
    def leaveEvent(self, e):  self._hover = False; self.update(); super().leaveEvent(e)


# ── Badge button ──────────────────────────────────────────────────────────────
class BadgeBtn(IconBtn):
    def __init__(self, glyph: str = "", size: int = 40, svg_icon: str = "", parent=None):
        super().__init__(glyph, size, svg_icon=svg_icon, parent=parent)
        self._count = 0

    def set_count(self, n: int):
        self._count = n
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        if self._count > 0:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            br = 8
            bx = self.width() - br - 2
            by = br + 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#ef4444"))
            p.drawEllipse(QRectF(bx - br, by - br, br * 2, br * 2))
            p.setPen(QPen(QColor("white")))
            f = QFont()
            f.setPointSize(6)
            f.setBold(True)
            p.setFont(f)
            p.drawText(
                QRect(bx - br, by - br, br * 2, br * 2),
                Qt.AlignmentFlag.AlignCenter,
                str(min(self._count, 99)),
            )


# ── Notification card ─────────────────────────────────────────────────────────
class _NotifCard(QFrame):
    def __init__(self, notif: dict, kind: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame{{background:#1a1d23;border-radius:10px;"
            f"border:1px solid {_BORDER};}}"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)

        # Thumbnail placeholder
        thumb = QFrame()
        if kind == "lpr":
            thumb.setFixedSize(96, 58)
            thumb.setStyleSheet("background:#2a2a2a;border-radius:4px;border:none;")
            glyph = "🚗"
        else:
            thumb.setFixedSize(58, 58)
            thumb.setStyleSheet("background:#2a2a2a;border-radius:29px;border:none;")
            glyph = "👤"

        tl = QLabel(glyph)
        tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tl.setStyleSheet("font-size:22px;background:transparent;border:none;")
        tl_lay = QVBoxLayout(thumb)
        tl_lay.setContentsMargins(0, 0, 0, 0)
        tl_lay.addWidget(tl)
        row.addWidget(thumb)

        # Info
        info = QVBoxLayout()
        info.setSpacing(3)

        if kind == "lpr":
            t = QLabel(notif.get("plate_no", "Unknown"))
            t.setStyleSheet(
                "color:white;font-size:15px;font-weight:bold;"
                "background:transparent;border:none;"
            )
        else:
            t = QLabel(notif.get("name", "Blacklist Person"))
            t.setStyleSheet(
                f"color:{_TEXT};font-size:13px;font-weight:bold;"
                "background:transparent;border:none;"
            )

        cam = QLabel(f"📷  {notif.get('camera', '')}")
        cam.setStyleSheet(f"color:{_TEXT};font-size:11px;background:transparent;border:none;")
        ts  = QLabel(f"🕐  {notif.get('created', '')}")
        ts.setStyleSheet(f"color:{_TEXT};font-size:11px;background:transparent;border:none;")

        if kind == "lpr":
            col_lbl = QLabel(f"🎨  {notif.get('color', '')}")
            col_lbl.setStyleSheet(
                f"color:{_TEXT};font-size:11px;background:transparent;border:none;"
            )
            info.addWidget(t)
            info.addWidget(cam)
            info.addWidget(ts)
            info.addWidget(col_lbl)
        else:
            info.addWidget(t)
            info.addWidget(cam)
            info.addWidget(ts)

        row.addLayout(info)
        row.addStretch()

        # Alert badge
        alert = QLabel("⚠")
        alert.setStyleSheet(
            "color:white;font-size:11px;background:#ef4444;"
            "border-radius:10px;padding:2px 4px;border:none;"
        )
        row.addWidget(alert, alignment=Qt.AlignmentFlag.AlignTop)


# ── Notification dialog ───────────────────────────────────────────────────────
class NotificationDialog(QDialog):
    """
    Two-column modal: LPR Alerts | Face Recognition Alerts
    Mirrors Vue's <Dialog> notification panel.
    """

    def __init__(self, lpr_notifs: list, face_notifs: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Notifications Center")
        self.setMinimumSize(980, 620)
        self.setModal(True)
        self.setStyleSheet(f"QDialog{{background:{_BG};color:{_TEXT};}}")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # Header row
        hdr = QHBoxLayout()
        bell = QLabel("🔔")
        bell.setStyleSheet("font-size:22px;background:transparent;")
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        t = QLabel("Notifications Center")
        t.setStyleSheet(
            f"color:{_TEXT};font-size:18px;font-weight:bold;background:transparent;"
        )
        total = len(lpr_notifs) + len(face_notifs)
        sub = QLabel(f"{total} total alert{'s' if total != 1 else ''}")
        sub.setStyleSheet("color:#9ca3af;font-size:12px;background:transparent;")
        title_col.addWidget(t)
        title_col.addWidget(sub)
        hdr.addWidget(bell, alignment=Qt.AlignmentFlag.AlignTop)
        hdr.addSpacing(8)
        hdr.addLayout(title_col)
        hdr.addStretch()
        root.addLayout(hdr)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{_BORDER};background:{_BORDER};max-height:1px;")
        root.addWidget(sep)

        # Two columns
        cols = QHBoxLayout()
        cols.setSpacing(12)
        cols.addWidget(self._col("🚗  LPR Alerts", lpr_notifs, "lpr"))
        cols.addWidget(self._col("👤  Face Recognition Alerts", face_notifs, "face"))
        root.addLayout(cols)

    def _col(self, hdr_text: str, notifs: list, kind: str) -> QWidget:
        col = QWidget()
        col.setStyleSheet(f"background:{_DARK};border-radius:8px;")
        lay = QVBoxLayout(col)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        # Column header
        hr = QHBoxLayout()
        hl = QLabel(hdr_text)
        hl.setStyleSheet(
            f"color:{_TEXT};font-size:14px;font-weight:bold;background:transparent;"
        )
        hr.addWidget(hl)
        if notifs:
            badge = QLabel(str(len(notifs)))
            badge.setFixedSize(28, 18)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                "background:rgba(239,68,68,0.2);color:#f87171;"
                "border:1px solid rgba(239,68,68,0.3);border-radius:9px;"
                "font-size:11px;font-weight:bold;"
            )
            hr.addWidget(badge)
        hr.addStretch()
        lay.addLayout(hr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{_BORDER};background:{_BORDER};max-height:1px;")
        lay.addWidget(sep)

        # Scrollable card list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { background:transparent; border:none; }
            QScrollBar:vertical { background:transparent; width:6px; }
            QScrollBar::handle:vertical {
                background:rgba(255,255,255,40);
                border-radius:3px; min-height:20px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height:0; }
        """)

        content = QWidget()
        content.setStyleSheet("background:transparent;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)

        if notifs:
            for n in reversed(notifs[-50:]):
                cl.addWidget(_NotifCard(n, kind))
        else:
            empty = QLabel(
                f"📭\n\nNo {'LPR' if kind == 'lpr' else 'Face'} Alerts\nAll clear!"
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color:#6b7280;font-size:13px;background:transparent;")
            cl.addWidget(empty)

        cl.addStretch()
        scroll.setWidget(content)
        lay.addWidget(scroll)
        return col


# ── Main header widget ────────────────────────────────────────────────────────
class AppHeader(QWidget):
    """
    Full-width application header.

    Signals
    -------
    navigate(path: str)        – user navigated to a route
    quick_navigate(path: str)  – user used a right-side quick action without opening a tab
    logout_requested()         – user clicked Logout
    """
    navigate         = Signal(str)
    quick_navigate   = Signal(str)
    logout_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._lpr_notifs:  list[dict] = []
        self._face_notifs: list[dict] = []

        self._build_ui()
        self._build_menus()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 8, 0)
        root.setSpacing(0)

        # ── LEFT: Logo · Title · TabBar ───────────────────────────────────────
        left = QWidget()
        left.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lr = QHBoxLayout(left)
        lr.setContentsMargins(6, 4, 0, 0)
        lr.setSpacing(0)

        # Logo
        if os.path.exists(LOGO_PATH):
            logo = SvgWidget(LOGO_PATH)
            logo.setFixedSize(34, 34)
            lr.addWidget(logo, alignment=Qt.AlignmentFlag.AlignVCenter)

        # "City Guard" text
        app_title = QLabel("City Guard")
        f = QFont()
        f.setPointSize(10)
        f.setBold(True)
        app_title.setFont(f)
        app_title.setStyleSheet(
            f"color:{_TEXT};background:transparent;"
            "margin-left:6px;margin-right:14px;"
        )
        lr.addWidget(app_title, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Tab bar
        self._tabbar = TabBar()
        self._tabbar.navigate.connect(self._on_navigate)
        lr.addWidget(self._tabbar)

        root.addWidget(left)

        # ── RIGHT: icon buttons ───────────────────────────────────────────────
        right = QWidget()
        right.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        rr = QHBoxLayout(right)
        rr.setContentsMargins(0, 4, 0, 0)
        rr.setSpacing(4)

        # self._monitor_btn = IconBtn(svg_icon="monitor.svg")
        # self._monitor_btn.setToolTip("Monitor")
        # self._monitor_btn.clicked.connect(
        #     lambda: self._on_quick_action("/settings/monitor")
        # )

        self._live_btn = IconBtn(svg_icon="live_view.svg")
        self._live_btn.setToolTip("Live View")
        self._live_btn.clicked.connect(lambda: self._on_quick_action("/stream/live"))

        # self._faces_btn = IconBtn(svg_icon="faces.svg")
        # self._faces_btn.setToolTip("Faces View")
        # self._faces_btn.clicked.connect(lambda: self._on_quick_action("/face/view"))

        self._notif_btn = BadgeBtn(svg_icon="notification.svg")
        self._notif_btn.setToolTip("Notifications")
        self._notif_btn.clicked.connect(self._open_notifications)

        self._search_btn = IconBtn(svg_icon="search.svg")
        self._search_btn.setToolTip("Search")
        self._search_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        self._profile_btn = IconBtn(svg_icon="profile.svg")
        self._profile_btn.setToolTip("Profile")
        self._profile_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        for btn in [
            self._live_btn,
            self._notif_btn, self._search_btn, self._profile_btn,
        ]:
            rr.addWidget(btn)

        root.addWidget(right)

    # ── Menus ─────────────────────────────────────────────────────────────────
    def _build_menus(self):
        def nav(path):
            return lambda: self._on_navigate(path)

        # ── Main menu (tiered, attached to + button) ──────────────────────────
        mm = QMenu(self)
        mm.setStyleSheet(_MENU_QSS)

        lpr = mm.addMenu("🚗  LPR")
        lpr.setStyleSheet(_MENU_QSS)
        lpr.addAction("🔍  Search",         nav("/search/lpr"))
        lpr.addAction("🗺️   Map Search",     nav("/search/lprmap"))
        lpr.addAction("🔄  Repeated",        nav("/search/lpr/repeated"))
        lpr.addAction("📊  Report",           nav("/report/lpr"))

        face = mm.addMenu("👤  Face")
        face.setStyleSheet(_MENU_QSS)
        face.addAction("🔍  Search",          nav("/search/face"))
        face.addAction("🗺️   Map Search",      nav("/search/facemap"))
        face.addAction("📊  Report",           nav("/report/face"))
        face.addAction("📊  Face Count Report",nav("/report/face_count"))

        users = mm.addMenu("👥  User Management")
        users.setStyleSheet(_MENU_QSS)
        users.addAction("👤  Profile",         nav("/user/profile"))
        users.addAction("👥  Users",           nav("/user/users"))
        users.addAction("🛡️  Roles",           nav("/user/roles"))
        users.addAction("🏢  Department",      nav("/user/department"))

        mm.addAction("📍  GPS",               nav("/gps/dashboard"))
        mm.addAction("📱  Bodycam",           nav("/body-cam/dashboard"))
        mm.addAction("📷  Live View",         nav("/stream/live"))

        dev = mm.addMenu("🖥️  Devices Management")
        dev.setStyleSheet(_MENU_QSS)
        dev.addAction("👤  Clients",          nav("/device/clients"))
        dev.addAction("📷  Cameras",          nav("/device/cameras"))
        dev.addAction("📍  GPS Tracker",      nav("/device/gps"))
        dev.addAction("🔐  Access Control",   nav("/device/access-control"))
        dev.addAction("📱  Bodycam Devices",  nav("/device/body-cam"))

        lm = mm.addMenu("🗂️  List Management")
        lm.setStyleSheet(_MENU_QSS)
        lm.addAction("🚫  LPR Blacklist",     nav("/lpr/blacklist"))
        lm.addAction("✅  LPR Whitelist",     nav("/lpr/whitelist"))
        lm.addAction("🚫  Face Blacklist",    nav("/face/blacklist"))
        lm.addAction("✅  Face Whitelist",    nav("/face/whitelist"))

        mm.addAction("⏮️   Playback",          nav("/camera/playback"))
        mm.addSeparator()
        mm.addAction("⚙️  Settings",          nav("/system/settings"))
        mm.addAction("📊  Monitor",            nav("/settings/monitor"))


        # ── Search menu ───────────────────────────────────────────────────────
        sm = QMenu(self)
        sm.setStyleSheet(_MENU_QSS)
        sm.addSection("LPR")
        sm.addAction("🔍  LPR Search",        nav("/search/lpr"))
        sm.addAction("🗺️   LPR Map Search",    nav("/search/lprmap"))
        sm.addSection("Face")
        sm.addAction("🔍  Face Search",        nav("/search/face"))
        sm.addAction("🗺️   Face Map Search",   nav("/search/facemap"))
        sm.addSection("Playback")
        sm.addAction("⏮️   Camera Playback",    nav("/camera/playback"))
        sm.addAction("🔄  Repeated Search",    nav("/search/lpr/repeated"))
        self._search_btn.setMenu(sm)

        # ── Profile menu ──────────────────────────────────────────────────────
        pm = QMenu(self)
        pm.setStyleSheet(_MENU_QSS)
        pm.addAction("👤  Profile",            nav("/user/profile"))
        pm.addSeparator()
        pm.addAction("🚪  Logout",             self.logout_requested.emit)
        self._profile_btn.setMenu(pm)

    # ── Navigation ────────────────────────────────────────────────────────────
    def _on_navigate(self, path: str):
        self._tabbar.set_current(path)
        self.navigate.emit(path)

    def _on_quick_action(self, path: str):
        self._on_navigate(path)

    # ── Notifications ─────────────────────────────────────────────────────────
    def add_lpr_notification(self, data: dict):
        self._lpr_notifs.append(data)
        if len(self._lpr_notifs) > 100:
            self._lpr_notifs.pop(0)
        self._notif_btn.set_count(len(self._lpr_notifs) + len(self._face_notifs))

    def add_face_notification(self, data: dict):
        self._face_notifs.append(data)
        if len(self._face_notifs) > 100:
            self._face_notifs.pop(0)
        self._notif_btn.set_count(len(self._lpr_notifs) + len(self._face_notifs))

    def _open_notifications(self):
        dlg = NotificationDialog(self._lpr_notifs, self._face_notifs, self)
        dlg.exec()

    # ── Public API ────────────────────────────────────────────────────────────
    def add_tab(self, name: str, path: str, icon: str = "", svg_icon: str = ""):
        """Call this when the user navigates to a new section."""
        self._tabbar.add_tab(name, path, icon, svg_icon)

    def set_current(self, path: str):
        """Sync active tab with current route."""
        self._tabbar.set_current(path)

    # ── Background ────────────────────────────────────────────────────────────
    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(_BG))
        p.setPen(QPen(QColor(_BORDER), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
