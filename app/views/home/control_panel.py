import os

from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QGridLayout,
    QApplication,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import (
    Qt,
    QEasingCurve,
    QVariantAnimation,
    Signal,
    QRectF,
)
from PySide6.QtGui import (
    QColor,
    QPainter,
    QLinearGradient,
    QBrush,
    QPen,
    QPainterPath,
    QCursor,
    QFont,
)
from PySide6.QtSvg import QSvgRenderer
from app.constants._init_ import Constants

_THIS_DIR = os.path.dirname(__file__)
_APP_DIR = os.path.abspath(os.path.join(_THIS_DIR, "../.."))
_ICONS_DIR = os.path.join(_APP_DIR, "resources", "icons")
LOGO_PATH = os.path.join(_APP_DIR, "resources", "Logo.svg")
# ── Palette (from Constants) ──────────────────────────────────────────────────
_DARK_BG   = Constants.DARK_BG      # "#0d0f12"  – panel background
_SURFACE_A = Constants.SURFACE_A    # "#222222"  – card gradient start
_SURFACE_B = Constants.SURFACE_B    # "#2f3133"  – card gradient mid
_SURFACE_C = "#3a3d40"              # card gradient bottom-right
_TEXT      = Constants.TEXT_MAIN    # "#c8cdd8"




def _icon(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


def _resolve_svg_path(svg_path: str) -> str:
    if not svg_path:
        return ""
    candidates = [svg_path]
    if not os.path.isabs(svg_path):
        candidates.append(os.path.abspath(svg_path))
        candidates.append(os.path.abspath(os.path.join(_APP_DIR, svg_path)))
        candidates.append(os.path.abspath(os.path.join(_APP_DIR, svg_path.lstrip("/"))))
    basename = os.path.basename(svg_path)
    if basename:
        candidates.append(os.path.join(_ICONS_DIR, basename))

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return ""


CONTROL_PANEL_TABS = [
    {
        "name": "Live View",
        "svg_icon": _icon("live_view.svg"),
        "path": "/stream/live",
        "permission": "live_view",
    },
    {
        "name": "Playback",
        "svg_icon": _icon("playback.svg"),
        "path": "/camera/playback",
        "permission": "playback",
    },
    # {
    #     "name": "GPS",
    #     "svg_icon": _icon("gps.svg"),
    #     "path": "/gps/dashboard",
    #     "permission": "manage_gps",
    # },
    # {
    #     "name": "Bodycam",
    #     "svg_icon": _icon("bodycam.svg"),
    #     "path": "/body-cam/dashboard",
    #     "permission": "manage_bodycam",
    # },
    {
        "name": "Search",
        "svg_icon": _icon("search.svg"),
        "permission": ["lpr_search", "face_search"],
        "children": [
            {"name": "LPR Search",    "path": "/search/lpr",          "permission": "lpr_search"},
            {"name": "Face Search",   "path": "/search/face",         "permission": "face_search"},
            {"name": "LPR Repeated",  "path": "/search/lpr/repeated", "permission": "face_search"},
        ],
    },
    # {
    #     "name": "Map Search",
    #     "svg_icon": _icon("map_search.svg"),
    #     "permission": ["lpr_search_map", "face_search_map"],
    #     "children": [
    #         {"name": "LPR Map Search",  "path": "/search/lprmap",  "permission": "lpr_search_map"},
    #         {"name": "Face Map Search", "path": "/search/facemap", "permission": "face_search_map"},
    #     ],
    # },
    {
        "name": "User Management",
        "svg_icon": _icon("user_managment.svg"),
        "permission": ["*", "user", "role", "department"],
        "children": [
            {"name": "Profile",    "path": "/user/profile",    "permission": "*"},
            {"name": "Users",      "path": "/user/users",      "permission": "user"},
            {"name": "Roles",      "path": "/user/roles",      "permission": "role"},
            {"name": "Department", "path": "/user/department", "permission": "department"},
        ],
    },
    {
        "name": "List Management",
        "svg_icon": _icon("list_management.svg"),
        "permission": ["view_lpr_blacklist", "view_lpr_whitelist",
                       "view_face_blacklist", "view_face_whitelist"],
        "children": [
            {"name": "LPR Blacklist",  "path": "/lpr/blacklist",  "permission": "view_lpr_blacklist"},
            {"name": "LPR Whitelist",  "path": "/lpr/whitelist",  "permission": "view_lpr_whitelist"},
            {"name": "Face Blacklist", "path": "/face/blacklist", "permission": "view_face_blacklist"},
            {"name": "Face Whitelist", "path": "/face/whitelist", "permission": "view_face_whitelist"},
        ],
    },
    {
        "name": "Device Management",
        "svg_icon": _icon("devices.svg"),
        "permission": ["view_client", "view_camera", "view_gps_device",
                       "view_access_control", "view_bodycam_device"],
        "children": [
            {"name": "Client",         "path": "/device/clients",         "permission": "view_client"},
            {"name": "Camera",         "path": "/device/cameras",         "permission": "view_camera"},
            # {"name": "GPS Tracker",    "path": "/device/gps",             "permission": "view_gps_device"},
            {"name": "Access Control", "path": "/device/access-control",  "permission": "view_access_control"},
        ],
    },
    {
        "name": "Activity Log",
        "svg_icon": _icon("activity_logs.svg"),
        "permission": "log",
        "children": [
            {"name": "User Logs",   "path": "/log/user",   "permission": "log"},
            {"name": "Client Logs", "path": "/log/client", "permission": "log"},
            {"name": "Camera Logs", "path": "/log/camera", "permission": "log"},
        ],
    },
    {
        "name": "Report",
        "svg_icon": _icon("report.svg"),
        "permission": ["lpr_report", "face_report"],
        "children": [
            {"name": "LPR Report",        "path": "/report/lpr",        "permission": "lpr_report"},
            {"name": "Face Report",       "path": "/report/face",       "permission": "face_report"},
            {"name": "Face Count Report", "path": "/report/face_count", "permission": "face_count_report"},
        ],
    },
    {
        "name": "Activation Management",
        "svg_icon": _icon("activation.svg"),
        "path": "/clients/activation",
        "permission": "activation",
    },
    # {
    #     "name": "Updates",
    #     "svg_icon": _icon("updates.svg"),
    #     "path": "/system/update",
    #     "permission": "*",
    # },
    # {
    #     "name": "Browser",
    #     "svg_icon": _icon("browser.svg"),
    #     "path": "/browser",
    #     "permission": "*",
    # },
    # {
    #     "name": "Terminal",
    #     "svg_icon": _icon("terminal.svg"),
    #     "path": "/system/terminal",
    #     "permission": "terminal",
    # },
    {
        "name": "Settings",
        "svg_icon": _icon("settings.svg"),
        "path": "/system/settings",
        "permission": "setting",
    },
]


CONTROL_PANEL_CARD_ACCENTS = {
    "Live View": ("#2563eb", "#38bdf8"),
    "Playback": ("#0f766e", "#22c55e"),
    "Search": ("#c2410c", "#f59e0b"),
    "User Management": ("#7c3aed", "#a855f7"),
    "List Management": ("#2563eb", "#818cf8"),
    "Device Management": ("#0f766e", "#2dd4bf"),
    "Activity Log": ("#be123c", "#fb7185"),
    "Report": ("#1d4ed8", "#60a5fa"),
    "Activation Management": ("#b45309", "#f59e0b"),
    "Settings": ("#475569", "#94a3b8"),
}
def _tab_accent(tab: dict) -> tuple[str, str]:
    return CONTROL_PANEL_CARD_ACCENTS.get(str(tab.get("name") or ""), ("#2563eb", "#60a5fa"))


# ── SVG icon widget ───────────────────────────────────────────────────────────
class _SvgIconWidget(QWidget):
    """Fixed-size widget that renders a QSvgRenderer centred inside itself."""

    def __init__(self, renderer: QSvgRenderer, size: int = 48, parent=None):
        super().__init__(parent)
        self._renderer = renderer
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self._renderer.render(p, QRectF(self.rect()))


# ── Child row item ─────────────────────────────────────────────────────────────
class ChildItemWidget(QWidget):
    navigate = Signal(str)

    def __init__(self, child: dict, parent=None):
        super().__init__(parent)
        self.path = child.get("path", "")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(38)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._bg  = QColor(_SURFACE_A)
        self._hov = QColor(_SURFACE_B)
        self._cur = QColor(_SURFACE_A)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)

        lbl = QLabel(child["name"])
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            f"color: {_TEXT}; font-size: 12px; background: transparent; border: none;"
        )
        lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(lbl)

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

    def _on_anim(self, color):
        self._cur = QColor(color)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 10, 10)
        p.setPen(Qt.PenStyle.NoPen)
        p.fillPath(path, self._cur)
        p.setPen(QPen(QColor(255, 255, 255, 14), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        super().paintEvent(event)

    def enterEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(QColor(self._cur))
        self._anim.setEndValue(QColor(self._hov))
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(QColor(self._cur))
        self._anim.setEndValue(QColor(self._bg))
        self._anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.navigate.emit(self.path)
        super().mousePressEvent(event)


# ── Card body ─────────────────────────────────────────────────────────────────
class CardBody(QWidget):
    clicked = Signal(str)

    _H = 200
    _RADIUS = 24

    def __init__(self, tab: dict, parent=None):
        super().__init__(parent)
        self.tab       = tab
        self._is_hov   = False
        self._shine_x  = 1.0    # 1 = off-right, -1 = off-left
        self._accent_start_hex, self._accent_end_hex = _tab_accent(tab)
        self._accent_start = QColor(self._accent_start_hex)
        self._accent_end = QColor(self._accent_end_hex)

        self.setFixedHeight(self._H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        # drop shadow
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(18)
        self._shadow.setOffset(0, 6)
        self._shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(self._shadow)

        # content
        inner = QVBoxLayout(self)
        inner.setContentsMargins(16, 16, 16, 16)
        inner.setSpacing(10)
        inner.setAlignment(Qt.AlignmentFlag.AlignCenter)

        svg_path = _resolve_svg_path(tab.get("svg_icon", ""))
        self._svg_renderer = QSvgRenderer(svg_path)
        self._icon_lbl = _SvgIconWidget(self._svg_renderer, size=44)
        self._icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._icon_shell = QFrame()
        self._icon_shell.setFixedSize(82, 82)
        self._icon_shell.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._icon_shell.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f" stop:0 {self._accent_start_hex}, stop:1 {self._accent_end_hex});"
            "border: 1px solid rgba(255, 255, 255, 0.18);"
            "border-radius: 24px;"
        )
        icon_shell_layout = QVBoxLayout(self._icon_shell)
        icon_shell_layout.setContentsMargins(18, 18, 18, 18)
        icon_shell_layout.setSpacing(0)
        icon_shell_layout.addWidget(self._icon_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        self._name_lbl = QLabel(tab["name"])
        self._name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_lbl.setWordWrap(True)
        f = QFont()
        f.setPointSize(12)
        f.setWeight(QFont.Weight.Medium)
        self._name_lbl.setFont(f)
        self._name_lbl.setStyleSheet(
            "color: #f8fafc; background: transparent; border: none;"
        )
        self._name_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        inner.addWidget(self._icon_shell, 0, Qt.AlignmentFlag.AlignHCenter)
        inner.addWidget(self._name_lbl)

        # shine animation
        self._shine_anim = QVariantAnimation(self)
        self._shine_anim.setDuration(700)
        self._shine_anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._shine_anim.valueChanged.connect(self._on_shine)

    def _on_shine(self, v: float):
        self._shine_x = v
        self.update()

    def set_hovered(self, hov: bool):
        self._is_hov = hov
        if hov:
            self._shine_anim.stop()
            self._shine_anim.setStartValue(1.0)
            self._shine_anim.setEndValue(-1.0)
            self._shine_anim.start()
            self._shadow.setBlurRadius(32)
            self._shadow.setOffset(0, 10)
            self._shadow.setColor(QColor(0, 0, 0, 160))
        else:
            self._shine_anim.stop()
            self._shine_x = 1.0
            self._shadow.setBlurRadius(18)
            self._shadow.setOffset(0, 6)
            self._shadow.setColor(QColor(0, 0, 0, 120))
        self._name_lbl.setStyleSheet(
            f"color: {'#ffffff' if hov else '#f8fafc'}; background: transparent; border: none;"
        )
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        rect = QRectF(0, 0, w, h)

        clip = QPainterPath()
        clip.addRoundedRect(rect, self._RADIUS, self._RADIUS)
        p.setClipPath(clip)

        # gradient: top-left → bottom-right
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0.0, QColor("#1a212b"))
        grad.setColorAt(0.52, QColor("#121924"))
        grad.setColorAt(1.0, QColor("#0d131b"))
        p.fillPath(clip, QBrush(grad))

        accent_glow = QLinearGradient(0, 0, w, h)
        accent_glow.setColorAt(0.0, QColor(self._accent_start.red(), self._accent_start.green(), self._accent_start.blue(), 46 if self._is_hov else 26))
        accent_glow.setColorAt(0.55, QColor(self._accent_end.red(), self._accent_end.green(), self._accent_end.blue(), 14 if self._is_hov else 8))
        accent_glow.setColorAt(1.0, QColor(10, 15, 21, 0))
        p.fillPath(clip, QBrush(accent_glow))

        # hover brightness overlay
        if self._is_hov:
            p.fillPath(clip, QColor(255, 255, 255, 14))

        # shine: white/10 band moves right → left
        band     = w * 0.5
        shine_cx = w * (1.0 + self._shine_x) / 2.0
        sg = QLinearGradient(shine_cx - band, 0, shine_cx + band, 0)
        sg.setColorAt(0.0, QColor(255, 255, 255, 0))
        sg.setColorAt(0.5, QColor(255, 255, 255, 25))
        sg.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(clip, QBrush(sg))

        # card border
        border_color = QColor(self._accent_end if self._is_hov else QColor(255, 255, 255, 26))
        if not self._is_hov:
            border_color = QColor(255, 255, 255, 18)
        p.setPen(QPen(border_color, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(clip)

        super().paintEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            children = self.tab.get("children", [])
            path = (
                children[0].get("path", self.tab.get("path", ""))
                if children else self.tab.get("path", "")
            )
            if path:
                self.clicked.emit(path)
        super().mousePressEvent(event)


# ── Full card column: body + expandable children ───────────────────────────────
class ControlPanelCard(QWidget):
    navigate = Signal(str)

    def __init__(self, tab: dict, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        vbox.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._body = CardBody(tab)
        self._body.clicked.connect(self.navigate)
        vbox.addWidget(self._body)

    def enterEvent(self, event):
        self._body.set_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._body.set_hovered(False)
        super().leaveEvent(event)


# ── Control Panel — scrollable, responsive grid ────────────────────────────────
class ControlPanel(QWidget):
    navigate = Signal(str)

    def __init__(self, tabs=None, parent=None):
        super().__init__(parent)
        self.tabs  = tabs if tabs is not None else CONTROL_PANEL_TABS
        self._cols = 4
        self._cards: list[ControlPanelCard] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        title = QLabel("Control Panel")
        title.setStyleSheet(
            "color: #f8fafc; font-size: 20px; font-weight: 700; padding: 2px 4px;"
        )
        outer.addWidget(title)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet("""
            QScrollArea            { background: transparent; border: none; }
            QScrollBar:vertical    { background: transparent; width: 6px; margin: 0; }
            QScrollBar::handle:vertical {
                background: rgba(148,163,184,70);
                min-height: 24px;
                border-radius: 3px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical { background: transparent; }
        """)

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._content)
        self._grid.setSpacing(18)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll)

        self._build_grid()

    def _build_grid(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._cards.clear()

        for i, tab in enumerate(self.tabs):
            card = ControlPanelCard(tab)
            card.navigate.connect(self.navigate)
            self._grid.addWidget(card, i // self._cols, i % self._cols)
            self._cards.append(card)

    def _recalc_cols(self):
        w = self.width()
        if   w < 480:  cols = 1
        elif w < 640:  cols = 2
        elif w < 900:  cols = 2
        elif w < 1200: cols = 3
        else:          cols = 4
        if cols != self._cols:
            self._cols = cols
            self._build_grid()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        p.fillPath(path, QColor(_DARK_BG))   # dark bg — cards float above it
        super().paintEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recalc_cols()
